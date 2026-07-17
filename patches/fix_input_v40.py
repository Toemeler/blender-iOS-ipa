#!/usr/bin/env python3
"""build-40 source patch: deliver cursor MOTION during middle/right-button
drags, so MMB orbit and Shift+MMB pan actually move the viewport.

Evidence from build-39 on-device logs: the [b39-ptr] lines show 10 clean
kind=2 (middle) DOWN/UP pairs -- the button events now reach Blender -- yet
the user reports orbit/pan do nothing. Left drags work because their motion
comes from the long-press recognizer's Changed states; middle/right drags
have no recognizer, and the raw touchesMoved override evidently does not
deliver motion while a non-primary button is held. Blender starts the orbit
operator on MIDDLEMOUSE and then receives zero MOUSEMOVE until the release.

Fix: a single deduplicating funnel (emitPointerMoveAt:) fed by THREE cheap
motion sources, active only while right/middle is held without left:

  1. the raw touchesMoved override (kept from build-39);
  2. the pan recognizer's gated early-return branch, in case UIKit routes
     non-primary drags into it;
  3. the existing UIPointerInteraction's regionForRequest: callback, which
     fires on every pointer move regardless of button state (its
     "[b26-ptr] cursor shape" activity is already proven in the logs).

Whichever stream(s) UIKit actually delivers, duplicates collapse in the
funnel and Blender sees one continuous motion stream.

Anchors target GHOST_WindowIOS.mm as it exists AFTER fix_input_v39.py.
Every edit asserts exactly-once application; non-zero exit on any mismatch.
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


# Declarations, so the pointer delegate (defined later in the file) can call
# into the window.
edit(W, "b40-decl",
     """    shouldRecognizeSimultaneouslyWithGestureRecognizer:
        (UIGestureRecognizer *)otherGestureRecognizer;
""",
     """    shouldRecognizeSimultaneouslyWithGestureRecognizer:
        (UIGestureRecognizer *)otherGestureRecognizer;
- (void)emitPointerMoveAt:(CGPoint)p;
- (void)emitScaledPointerMoveFromViewPoint:(CGPoint)p_in_view;
""")

# The funnel + scaling helper, inserted before the build-39 button emitter.
edit(W, "b40-funnel",
     "/* build-39: shared emitter for mouse button transitions.",
     """/* build-40: single funnel for cursor moves during right/middle-only drags.
 * Deduplicates across its three feeders (raw touchesMoved, the pan
 * recognizer's gated branch, UIPointerInteraction region requests): it is
 * not guaranteed WHICH of those streams UIKit delivers while a non-primary
 * button is held -- build-39 proved the button DOWN/UP arrive but no motion
 * flowed between them -- so all three feed in and duplicates drop here.
 * Takes an ALREADY window-scaled point. */
- (void)emitPointerMoveAt:(CGPoint)p
{
  static CGPoint last = {-1.0e9, -1.0e9};
  if (fabs(p.x - last.x) < 0.01 && fabs(p.y - last.y) < 0.01) {
    return;
  }
  last = p;
  UserInputEvent event_info(&p, nullptr, nullptr, false);
  event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
  [self generateUserInputEvents:event_info];
}

/* build-40: same funnel, for callers holding an unscaled view point. */
- (void)emitScaledPointerMoveFromViewPoint:(CGPoint)p_in_view
{
  [self emitPointerMoveAt:window->scalePointToWindow(p_in_view)];
}

/* build-39: shared emitter for mouse button transitions.""")

# Feeder 1: raw touchesMoved (route build-39's inline emission through the
# funnel so it dedupes against the other feeders).
edit(W, "b40-raw-moved-funnel",
     """      if ((g_ios_ptr_kind_down[1] || g_ios_ptr_kind_down[2]) && !g_ios_ptr_kind_down[0]) {
        CGPoint p = [touch locationInView:window->getView()];
        p = window->scalePointToWindow(p);
        UserInputEvent event_info(&p, nullptr, nullptr, false);
        event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
        [self generateUserInputEvents:event_info];
      }
""",
     """      if ((g_ios_ptr_kind_down[1] || g_ios_ptr_kind_down[2]) && !g_ios_ptr_kind_down[0]) {
        [self emitScaledPointerMoveFromViewPoint:[touch locationInView:window->getView()]];
      }
""")

# Feeder 2: the pan recognizer's gated branch.
edit(W, "b40-pan-feeder",
     """    if (g_ios_pointer_touch || g_ios_pointer_button_down) {
      [sender setCachedTranslation:translation];
      return;
    }
""",
     """    if (g_ios_pointer_touch || g_ios_pointer_button_down) {
      /* build-40: if UIKit routes a right/middle-button drag into this pan
       * recognizer, forward its motion (deduped) so orbit/pan track. */
      if ((g_ios_ptr_kind_down[1] || g_ios_ptr_kind_down[2]) && !g_ios_ptr_kind_down[0]) {
        [self emitPointerMoveAt:touch_point];
      }
      [sender setCachedTranslation:translation];
      return;
    }
""")

# Feeder 3: pointer-interaction region requests (fire on every pointer move
# regardless of button state).
edit(W, "b40-region-feeder",
     """  CGRect r = CGRectMake(request.location.x - 4.0, request.location.y - 4.0, 8.0, 8.0);
  return [UIPointerRegion regionWithRect:r identifier:@"ghost-pointer"];
""",
     """  /* build-40: region requests fire on every pointer move regardless of
   * button state, making this the most reliable motion source for
   * right/middle-only drags. */
  if ((g_ios_ptr_kind_down[1] || g_ios_ptr_kind_down[2]) && !g_ios_ptr_kind_down[0]) {
    UIView *v = interaction.view;
    if ([v.window isKindOfClass:[GHOSTUIWindow class]]) {
      [(GHOSTUIWindow *)v.window emitScaledPointerMoveFromViewPoint:request.location];
    }
  }
  CGRect r = CGRectMake(request.location.x - 4.0, request.location.y - 4.0, 8.0, 8.0);
  return [UIPointerRegion regionWithRect:r identifier:@"ghost-pointer"];
""")

print(f"BUILD-40 (motion during middle/right drags: MMB orbit, Shift+MMB pan, "
      f"RMB drag interactions) APPLIED OK ({len(applied)} edits)")
