#!/usr/bin/env python3
"""build-50: middle-button drags emit TRACKPAD PAN events (the path that
already works on device) instead of relying on Blender's modal operators.

Evidence: an in-app modal trace proved Blender receives a textbook middle
drag -- MIDDLEMOUSE PRESS, ~500 smooth MOUSEMOVEs, MIDDLEMOUSE RELEASE --
and still does not orbit. Invoking view3d.rotate directly from Python and
moving the mouse also did not orbit, with no mouse buttons involved. So the
MODAL operator path is broken on this iOS build, while every immediate
(non-modal) path works: wheel zoom, and the two-finger trackpad
orbit/pan/zoom the user already relies on.

The trackpad path emits GHOST_EventTrackpad(GHOST_kTrackpadEventScroll)
via UserInputEvent::PAN_GESTURE. Blender turns that into MOUSEPAN
(keymap name TRACKPADPAN), and the default 3D View keymap binds:
    TRACKPADPAN            -> view3d.rotate   (orbit)
    Shift + TRACKPADPAN    -> view3d.move     (pan)
Both are applied immediately inside invoke and return FINISHED -- no modal
handler required.

So: while the middle button is held, the build-49 per-frame poll (already
delivering exact positions) now emits PAN_GESTURE deltas. Middle button
DOWN/UP are no longer sent during drags; a middle CLICK (travel under the
threshold) still emits a real MIDDLEMOUSE down/up pair at release, so
click-only uses keep working. Right button is untouched (context menus).

Anchors target GHOST_WindowIOS.mm as it exists AFTER fix_input_v49.py.
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


# State for middle-button trackpad emulation.
edit(W, "b50-globals",
     "static double g_ios_gc_travel = 0.0;\n",
     """static double g_ios_gc_travel = 0.0;
/* build-50: middle-button trackpad emulation. While MMB is held we send
 * PAN_GESTURE (trackpad scroll) deltas instead of MIDDLEMOUSE + motion,
 * because the modal-operator path is broken on this build while the
 * immediate trackpad path works. A short press with no travel still
 * produces a real middle click at release. */
static bool g_ios_mmb_active = false;
static bool g_ios_mmb_click_pending = false;
static double g_ios_mmb_travel = 0.0;
static CGPoint g_ios_mmb_last = {0.0, 0.0};
#define GHOST_IOS_MMB_CLICK_SLOP 6.0
""")

# Intercept middle-button transitions: suppress the GHOST button events while
# dragging; synthesize a click at release when there was no real travel.
edit(W, "b50-button-intercept",
     """  g_ios_ptr_kind_down[kind] = down ? true : false;
  g_ios_pointer_button_down = g_ios_ptr_kind_down[0] || g_ios_ptr_kind_down[1] ||
                              g_ios_ptr_kind_down[2];
""",
     """  g_ios_ptr_kind_down[kind] = down ? true : false;
  g_ios_pointer_button_down = g_ios_ptr_kind_down[0] || g_ios_ptr_kind_down[1] ||
                              g_ios_ptr_kind_down[2];
  if (kind == 2) {
    /* build-50: trackpad emulation owns the middle button. */
    if (down) {
      g_ios_mmb_active = true;
      g_ios_mmb_click_pending = true;
      g_ios_mmb_travel = 0.0;
      g_ios_mmb_last = g_ios_ptr_view_pos;
      fprintf(stderr, "[b50-mmb] press (trackpad emulation armed)\\n");
      return; /* no MIDDLEMOUSE press: it would start the broken modal op */
    }
    g_ios_mmb_active = false;
    if (g_ios_mmb_click_pending) {
      /* No drag -> deliver a genuine middle click. */
      g_ios_mmb_click_pending = false;
      fprintf(stderr, "[b50-mmb] click (travel %.1f)\\n", g_ios_mmb_travel);
      UserInputEvent click_down(&p, nullptr, nullptr, false);
      click_down.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
      click_down.add_event(UserInputEvent::EventTypes::MIDDLE_BUTTON_DOWN);
      [self generateUserInputEvents:click_down];
      UserInputEvent click_up(&p, nullptr, nullptr, false);
      click_up.add_event(UserInputEvent::EventTypes::MIDDLE_BUTTON_UP);
      [self generateUserInputEvents:click_up];
    }
    else {
      fprintf(stderr, "[b50-mmb] drag end (travel %.1f)\\n", g_ios_mmb_travel);
    }
    return;
  }
""")

# Feed pan deltas from the per-frame poll.
edit(W, "b50-pan-from-poll",
     """    CGPoint p = [g_ios_pointer_touch locationInView:window->getView()];
    if ((g_ios_poll_tick++ % 15) == 0) {
""",
     """    CGPoint p = [g_ios_pointer_touch locationInView:window->getView()];
    if (g_ios_mmb_active) {
      /* build-50: emit trackpad-pan deltas -> TRACKPADPAN -> view3d.rotate
       * (Shift: view3d.move), the immediate path that works on device. */
      CGPoint d = CGPointMake(p.x - g_ios_mmb_last.x, p.y - g_ios_mmb_last.y);
      g_ios_mmb_last = p;
      double moved = fabs((double)d.x) + fabs((double)d.y);
      g_ios_mmb_travel += moved;
      if (g_ios_mmb_travel > GHOST_IOS_MMB_CLICK_SLOP) {
        g_ios_mmb_click_pending = false;
      }
      if (moved > 0.0) {
        CGPoint loc = window->scalePointToWindow(p);
        CGPoint tran = CGPointMake(d.x, -d.y); /* view y-down -> GHOST y-up */
        UserInputEvent pan_info(&loc, &tran, nullptr, false);
        pan_info.add_event(UserInputEvent::EventTypes::PAN_GESTURE);
        [self generateUserInputEvents:pan_info];
        if ((g_ios_poll_tick % 15) == 0) {
          fprintf(stderr, "[b50-mmb] pan d=%.1f,%.1f at %.1f,%.1f\\n",
                  tran.x, tran.y, loc.x, loc.y);
        }
      }
      g_ios_poll_tick++;
      return;
    }
    if ((g_ios_poll_tick++ % 15) == 0) {
""")

print(f"BUILD-50 (middle-drag -> trackpad pan events; click preserved) "
      f"APPLIED OK ({len(applied)} edits)")
