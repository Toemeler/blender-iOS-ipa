#!/usr/bin/env python3
"""build-49 source patch: middle/right drag motion by POLLING the live
pointer UITouch each display frame.

What the build-48 WM trace proved (turning point):
  * MIDDLEMOUSE PRESS reaches Blender's WM and MATCHES: the keymap cascade
    stops at '3D View' (a stopped cascade = an item consumed the event),
    i.e. view3d.rotate/move IS invoked and its modal handler runs.
  * The modal op then receives almost no motion: press xy (1538,1354),
    release xy (1560,1384) -- ~22 px total for a 2-second circle drag.
    Orbit "does nothing" because it rotates by an invisible amount.
  * Zero [b46-ptr] lines: the long-press recognizer did NOT begin for this
    session's middle presses (the phantom-left behavior of build-45 is
    intermittent), so the recognizer-Changed motion path never engaged.
  * GCMouse deltas, even accumulated on a background queue and drained by
    the display link, under-deliver during holds on this iPadOS version
    (~22 px integrated across the whole drag).

What the logs also proved, across every build so far: the RELEASE
coordinates from [touch locationInView:] are always exactly right -- UIKit
updates the tracked UITouch object continuously even though it delivers no
touchesMoved for non-primary buttons. And the CADisplayLink demonstrably
fires during holds (EMIT lines appear mid-press).

So the fix is to combine the two proven-reliable pieces: each display frame,
while right/middle is held without left and the pointer touch object exists,
read its live location and feed the absolute position through the deduping
funnel. No event delivery to depend on, no delta integration to drift or
starve. GC deltas remain as fallback only for the (unobserved) case of a
buttons-held drag with no touch object. Also: ignore the GC button backup
when no position basis exists yet (fixes the RIGHT_DOWN at 0,0 seen at
session start before any hover).

Anchors target GHOST_WindowIOS.mm as it exists AFTER fix_input_v46.py.
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


# Poll-proof logging budget.
edit(W, "b49-budget-global",
     "static std::atomic<long long> g_ios_gc_dy_mu(0);\n",
     "static std::atomic<long long> g_ios_gc_dy_mu(0);\n"
     "/* build-49: heartbeat for the motion trace during middle/right holds --\n"
     " * every 15th display tick logs whether a UITouch exists, the polled\n"
     " * position, and the cumulative GC delta travel, so ONE test session\n"
     " * distinguishes 'no touch object' from 'GC deltas under-deliver'. */\n"
     "static int g_ios_poll_tick = 0;\n"
     "static double g_ios_gc_travel = 0.0;\n")

# Arm the log budget on every non-left DOWN.
edit(W, "b49-budget-arm",
     """  g_ios_ptr_kind_down[kind] = down ? true : false;
  g_ios_pointer_button_down = g_ios_ptr_kind_down[0] || g_ios_ptr_kind_down[1] ||
                              g_ios_ptr_kind_down[2];
""",
     """  g_ios_ptr_kind_down[kind] = down ? true : false;
  g_ios_pointer_button_down = g_ios_ptr_kind_down[0] || g_ios_ptr_kind_down[1] ||
                              g_ios_ptr_kind_down[2];
  if (down && kind != 0) {
    g_ios_poll_tick = 0;      /* build-49 */
    g_ios_gc_travel = 0.0;
  }
""")

# GC button backup: never emit at a fictitious origin.
edit(W, "b49-gc-btn-basis",
     """  if (g_ios_ptr_kind_down[kind] == (bool)pressed) {
    return;
  }
""",
     """  if (g_ios_ptr_kind_down[kind] == (bool)pressed) {
    return;
  }
  if (pressed && g_ios_pointer_touch == nil && g_ios_ptr_view_pos.x == 0.0 &&
      g_ios_ptr_view_pos.y == 0.0)
  {
    /* build-49: GC saw a button before any hover/touch established a pointer
     * position; emitting a DOWN at 0,0 would click the screen corner. */
    fprintf(stderr, "[b49-ptr] GC button ignored (no position basis yet)\\n");
    return;
  }
""")

# The core: display tick polls the live touch; GC deltas demoted to fallback.
edit(W, "b49-tick-poll",
     """- (void)gcDisplayTick:(CADisplayLink *)link
{
  long long dx_mu = g_ios_gc_dx_mu.exchange(0);
  long long dy_mu = g_ios_gc_dy_mu.exchange(0);
  if (dx_mu == 0 && dy_mu == 0) {
    return;
  }
  [self gcMouseMovedDX:(float)(dx_mu / 1000.0) dy:(float)(dy_mu / 1000.0)];
}
""",
     """- (void)gcDisplayTick:(CADisplayLink *)link
{
  /* build-49: while right/middle is held without left and the pointer touch
   * object exists, POLL its live location -- UIKit keeps the UITouch's
   * position current even though it delivers no touchesMoved for
   * non-primary buttons (every release coordinate across builds 39-47 was
   * exact), and this display link demonstrably fires during holds. Absolute
   * truth at 60 Hz, funnel-deduped; no delivery or integration to fail. */
  const bool mr_held = (g_ios_ptr_kind_down[1] || g_ios_ptr_kind_down[2]) &&
                       !g_ios_ptr_kind_down[0];
  if (mr_held && g_ios_pointer_touch != nil) {
    /* Poll is absolute; discard GC deltas so the two cannot double-count. */
    long long qx = g_ios_gc_dx_mu.exchange(0);
    long long qy = g_ios_gc_dy_mu.exchange(0);
    g_ios_gc_travel += (fabs((double)qx) + fabs((double)qy)) / 1000.0;
    CGPoint p = [g_ios_pointer_touch locationInView:window->getView()];
    if ((g_ios_poll_tick++ % 15) == 0) {
      fprintf(stderr, "[b49-ptr] POLL touch=1 %.1f,%.1f (gc_travel=%.1f)\\n",
              p.x, p.y, g_ios_gc_travel);
    }
    [self emitScaledPointerMoveFromViewPoint:p];
    return;
  }
  long long dx_mu = g_ios_gc_dx_mu.exchange(0);
  long long dy_mu = g_ios_gc_dy_mu.exchange(0);
  if (mr_held) {
    g_ios_gc_travel += (fabs((double)dx_mu) + fabs((double)dy_mu)) / 1000.0;
    if ((g_ios_poll_tick++ % 15) == 0) {
      fprintf(stderr, "[b49-ptr] POLL touch=0 base=%.1f,%.1f (gc_travel=%.1f)\\n",
              g_ios_ptr_view_pos.x, g_ios_ptr_view_pos.y, g_ios_gc_travel);
    }
  }
  if (dx_mu == 0 && dy_mu == 0) {
    return;
  }
  [self gcMouseMovedDX:(float)(dx_mu / 1000.0) dy:(float)(dy_mu / 1000.0)];
}
""")

print(f"BUILD-49 (per-frame UITouch position polling for M/R drags) "
      f"APPLIED OK ({len(applied)} edits)")
