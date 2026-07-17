#!/usr/bin/env python3
"""build-41 source patch: middle/right-button drag motion via GCMouse.

Evidence chain from the build-40 on-device log: middle-button DOWN/UP pairs
arrive with FAR-APART coordinates (e.g. DOWN 879,1532 -> UP 1722,1541), so
UIKit tracks the drag internally -- yet not one of build-40's three motion
feeders fired between them. For indirect-pointer touches holding a
NON-PRIMARY button, this UIKit version delivers touchesBegan and touchesEnded
but no touchesMoved, routes nothing into the pan recognizer, and pauses
pointer-region requests. There is no UIKit-level source for that motion.

Fix: go below UIKit. The GameController framework (already imported and used
for GCKeyboard since build-15) exposes GCMouse (iOS 14+): raw HID deltas via
mouseMovedHandler and per-button pressedChangedHandlers, delivered on the
main queue regardless of UIKit's gesture plumbing. build-41:

  * attaches to GCMouse.current and to later GCMouseDidConnectNotification;
  * tracks the pointer's last known VIEW-coordinate position (updated by
    every hover move, button press and raw touch) as the integration base;
  * while right/middle is held without left, integrates mouseMoved deltas
    (GC y-up -> UIKit y-down), clamps to the view, and feeds the deduped
    build-40 funnel -- so Blender finally receives MOUSEMOVE between
    MIDDLEMOUSE press and release: orbit, Shift+MMB pan, RMB drags;
  * mirrors right/middle press state from GCMouse's button handlers as a
    backup to the raw-touch path (both sides are no-ops when the per-button
    flag already matches, so they cannot double-fire).

Anchors target GHOST_WindowIOS.mm as it exists AFTER fix_input_v40.py.
Every edit asserts its occurrence count; non-zero exit on any mismatch.
"""
import sys

W = "blender/intern/ghost/intern/GHOST_WindowIOS.mm"

applied = []


def edit(path, tag, old, new, count=1):
    with open(path) as f:
        src = f.read()
    n = src.count(old)
    if n != count:
        sys.stderr.write(f"FATAL {tag}: anchor found {n}x (expected {count})\n")
        sys.exit(1)
    with open(path, "w") as f:
        f.write(src.replace(old, new, count))
    applied.append(tag)
    print(f"{path}: applied '{tag}'")


# Pointer position base (VIEW coords, unscaled) for delta integration.
edit(W, "b41-pos-global",
     """static bool g_ios_ptr_kind_down[3] = {false, false, false};
""",
     """static bool g_ios_ptr_kind_down[3] = {false, false, false};
/* build-41: last known pointer position in VIEW coordinates (points),
 * refreshed by hover moves, presses and raw touches; the integration base
 * for GCMouse deltas during right/middle-button drags. */
static CGPoint g_ios_ptr_view_pos = {0.0, 0.0};
""")

# Declarations for the GC handlers.
edit(W, "b41-decl",
     "- (void)emitScaledPointerMoveFromViewPoint:(CGPoint)p_in_view;\n",
     "- (void)emitScaledPointerMoveFromViewPoint:(CGPoint)p_in_view;\n"
     "- (void)gcButton:(int)kind pressed:(BOOL)pressed;\n"
     "- (void)gcMouseMovedDX:(float)dx dy:(float)dy;\n")

# Keep the position base fresh at the single scaled-funnel choke point...
edit(W, "b41-funnel-tracks-pos",
     """- (void)emitScaledPointerMoveFromViewPoint:(CGPoint)p_in_view
{
  [self emitPointerMoveAt:window->scalePointToWindow(p_in_view)];
}
""",
     """- (void)emitScaledPointerMoveFromViewPoint:(CGPoint)p_in_view
{
  g_ios_ptr_view_pos = p_in_view; /* build-41: delta-integration base */
  [self emitPointerMoveAt:window->scalePointToWindow(p_in_view)];
}
""")

# ...and wherever button events compute a view-space location: sync (4-space
# indent, inside @available) and release (2-space indent).
edit(W, "b41-sync-tracks-pos",
     """    CGPoint p = [touch locationInView:window->getView()];
    p = window->scalePointToWindow(p);
    UIEventButtonMask mask = event.buttonMask;
""",
     """    CGPoint p = [touch locationInView:window->getView()];
    g_ios_ptr_view_pos = p; /* build-41: delta-integration base */
    p = window->scalePointToWindow(p);
    UIEventButtonMask mask = event.buttonMask;
""")
edit(W, "b41-release-tracks-pos",
     """  CGPoint p = [touch locationInView:window->getView()];
  p = window->scalePointToWindow(p);
  for (int kind = 1; kind <= 2; kind++) {
""",
     """  CGPoint p = [touch locationInView:window->getView()];
  g_ios_ptr_view_pos = p; /* build-41: delta-integration base */
  p = window->scalePointToWindow(p);
  for (int kind = 1; kind <= 2; kind++) {
""")

# Route the mouse hover handler through the scaled funnel so hovering keeps
# the position base fresh right up to the click.
edit(W, "b41-hover-through-funnel",
     """    CGPoint p = [sender locationInView:window->getView()];
    p = window->scalePointToWindow(p);
    UserInputEvent event_info(&p, nullptr, nullptr, false);
    event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
    [self generateUserInputEvents:event_info];
  }
}

- (void)handleHover:(GHOSTUIHoverGestureRecognizer *)sender
""",
     """    [self emitScaledPointerMoveFromViewPoint:[sender locationInView:window->getView()]];
  }
}

- (void)handleHover:(GHOSTUIHoverGestureRecognizer *)sender
""")

# GC handler methods, inserted before the build-40 funnel.
edit(W, "b41-gc-methods",
     "/* build-40: single funnel for cursor moves during right/middle-only drags.",
     """/* build-41: GCMouse button mirror. The raw-touch path usually emits the
 * DOWN first (with an exact absolute position); this is the backup for
 * cases where no indirect touch is created at all. No-op when the
 * per-button flag already matches, so the two sources cannot double-fire. */
- (void)gcButton:(int)kind pressed:(BOOL)pressed
{
  if (g_ios_ptr_kind_down[kind] == (bool)pressed) {
    return;
  }
  [self emitPointerButton:kind
                     down:(pressed ? YES : NO)
                       at:window->scalePointToWindow(g_ios_ptr_view_pos)];
}

/* build-41: raw HID mouse deltas. UIKit delivers NO touchesMoved, pan
 * updates or pointer-region requests while a non-primary button is held
 * (build-40 proved all three silent while the DOWN/UP coordinates moved),
 * so during right/middle-only drags the motion is integrated from GCMouse
 * deltas on top of the last known pointer position. GC deltas are y-up;
 * UIKit view coordinates are y-down. */
- (void)gcMouseMovedDX:(float)dx dy:(float)dy
{
  if (!((g_ios_ptr_kind_down[1] || g_ios_ptr_kind_down[2]) && !g_ios_ptr_kind_down[0])) {
    return;
  }
  UIView *v = window->getView();
  CGPoint p = g_ios_ptr_view_pos;
  p.x = MIN(MAX(p.x + (CGFloat)dx, (CGFloat)0.0), v.bounds.size.width);
  p.y = MIN(MAX(p.y - (CGFloat)dy, (CGFloat)0.0), v.bounds.size.height);
  [self emitScaledPointerMoveFromViewPoint:p];
}

/* build-40: single funnel for cursor moves during right/middle-only drags.""")

# Hook up GCMouse next to the build-39 mouse hover recognizer registration.
edit(W, "b41-gc-attach",
     """    mouse_hover_recognizer.allowedTouchTypes = @[ @(UITouchTypeIndirectPointer) ];
    [window->getView() addGestureRecognizer:mouse_hover_recognizer];
  }
""",
     """    mouse_hover_recognizer.allowedTouchTypes = @[ @(UITouchTypeIndirectPointer) ];
    [window->getView() addGestureRecognizer:mouse_hover_recognizer];
  }

  /* build-41: GCMouse = raw HID mouse events below UIKit's gesture plumbing,
   * the only source that delivers motion while a non-primary button is held
   * (same framework the hardware-keyboard support already uses). */
  if (@available(iOS 14.0, *)) {
    /* This file compiles under MRC (manual retain/release), so no __weak:
     * capture self directly. The window outlives the app session, so the
     * resulting handler->window reference is not a leak in practice. */
    GHOSTUIWindow *handler_window = self;
    void (^attach_mouse)(GCMouse *) = ^(GCMouse *mouse) {
      GCMouseInput *mi = mouse.mouseInput;
      if (!mi) {
        return;
      }
      mi.rightButton.pressedChangedHandler =
          ^(GCControllerButtonInput *button, float value, BOOL pressed) {
            [handler_window gcButton:1 pressed:pressed];
          };
      mi.middleButton.pressedChangedHandler =
          ^(GCControllerButtonInput *button, float value, BOOL pressed) {
            [handler_window gcButton:2 pressed:pressed];
          };
      mi.mouseMovedHandler = ^(GCMouseInput *mouse_input, float delta_x, float delta_y) {
        [handler_window gcMouseMovedDX:delta_x dy:delta_y];
      };
      fprintf(stderr, "[b41-gcm] mouse attached\\n");
    };
    if (GCMouse.current) {
      attach_mouse(GCMouse.current);
    }
    [[NSNotificationCenter defaultCenter]
        addObserverForName:GCMouseDidConnectNotification
                    object:nil
                     queue:[NSOperationQueue mainQueue]
                usingBlock:^(NSNotification *note) {
                  if ([note.object isKindOfClass:[GCMouse class]]) {
                    attach_mouse((GCMouse *)note.object);
                  }
                }];
  }
""")

print(f"BUILD-41 (GCMouse raw deltas: MMB orbit, Shift+MMB pan, RMB drags) "
      f"APPLIED OK ({len(applied)} edits)")
