#!/usr/bin/env python3
"""build-55: FIX the Add Modifier dead click -- left-button echo guard.

WHAT THE ON-DEVICE build-53 LOG ACTUALLY SHOWED (blender_console.log,
session 2026-07-21 09:18)
----------------------------------------------------------------------
The dead click is NOT a hit-test miss. The failing press logged

    [b53-ui] LMB PRESS at (2420,1301) region=0 active=Add Modifier over=Add Modifier

i.e. ui_but_find_mouse_over() FOUND the button, and there is not one
[b53-hit] MISS line in the whole 6825-line session. The m1/m2/m3 dead-panel
theory (builds 52-54) targeted a miss that does not occur. What does occur,
for one physical tap on Add Modifier:

    [b39-ptr] kind=0 DOWN 2420.8,1098.8   <- real press: popup OPENS
    [b39-ptr] kind=0 UP   2421.4,1098.8
    [b39-ptr] kind=0 DOWN 2421.4,1098.8   <- phantom press: popup CLOSES
    [b39-ptr] kind=0 UP   2421.4,1098.8

Two proofs it is synthetic: (1) the echo DOWN is byte-identical in
sub-pixel coordinates to the preceding UP -- a working click in the same
log jitters 1723.2 -> 1723.8 between press and release; (2) only the FIRST
press reaches ui_region_handler ([b53-ui] logs a PRESS but never the
RELEASE), which is exactly what happens when a popup opens on the press
and its handler then swallows the rest -- so the popup opened and the
phantom second press toggled it shut. Net effect: "the click did nothing".
It was invisible on ordinary buttons (double-click on a tab/checkbox is
harmless) and only surfaced on popup-opening buttons.

MECHANISM
---------
The left button is emitted from exactly ONE place: handlePointerPress, the
UILongPressGestureRecognizer with minimumPressDuration = 0 (build-26/37/39).
syncPointerButtons only ever emits kinds 1 and 2. Two kind=0 cycles for one
tap therefore mean that recognizer ran Began->Ended TWICE for one physical
click -- a known fragility of zero-duration long-press recognizers fed by
indirect-pointer touches. The existing dedup (if (!g_ios_ptr_kind_down[0]))
cannot stop it: after the first UP the flag is false again.

build-52 added a 150 ms echo guard for EXACTLY this class of bug -- but
only inside `if (kind == 2)`. The left button had no guard. This build
gives it one, in the same spirit:

  * emitPointerButton stamps the time and position of every LEFT UP
    (single choke point -- every left release passes through it).
  * handlePointerPress's Began branch drops the press if it lands within
    150 ms AND 8 px of that last left UP. No physical re-press is that
    fast and that still; the observed echo is same-frame and 0.0-0.6 px.
    Dropping the Began leaves g_ios_ptr_kind_down[0] false, so the echo's
    paired Ended emits nothing either (guarded by the existing flag test).
    A genuine fast double-click (typically 150-500 ms apart, with real
    pointer jitter) passes.

Diagnostic retained: each dropped echo logs "[b55-lmb] dropped Began echo"
with the ms/px deltas, so the on-device log verifies the fix fires on the
Add Modifier tap and never on legitimate clicks.

Anchors target the sources as they exist AFTER fix_input_v49.py (last
patch to touch emitPointerButton) and fix_input_v46.py (last patch to
touch handlePointerPress). Runs after v54 in the chain; v50-v54 do not
modify either function.
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


# --- 1. globals: last-left-UP stamp, next to the build-49 poll globals -------
edit(W, "b55-globals",
     """static int g_ios_poll_tick = 0;
static double g_ios_gc_travel = 0.0;
""",
     """static int g_ios_poll_tick = 0;
static double g_ios_gc_travel = 0.0;
/* build-55: left-button echo guard. The zero-duration long-press recognizer
 * that carries the left button can run Began->Ended twice for ONE physical
 * click (observed on device: the echo Began arrives same-frame at sub-pixel
 * identical coordinates to the preceding UP, and it toggled the freshly
 * opened Add Modifier popup shut -- the "dead click"). Stamp every left UP;
 * a Began within 150 ms and 8 px of it is the echo and is dropped. */
static uint64_t g_ios_lmb_up_ms = 0;
static CGPoint g_ios_lmb_up_pos = {0.0, 0.0};
""")

# --- 2. emitPointerButton: stamp time+pos of every LEFT UP -------------------
# Anchor is the build-49 budget-arm block -- the current text of the flag
# section inside emitPointerButton, unique in the file.
edit(W, "b55-up-stamp",
     """  g_ios_ptr_kind_down[kind] = down ? true : false;
  g_ios_pointer_button_down = g_ios_ptr_kind_down[0] || g_ios_ptr_kind_down[1] ||
                              g_ios_ptr_kind_down[2];
  if (down && kind != 0) {
    g_ios_poll_tick = 0;      /* build-49 */
    g_ios_gc_travel = 0.0;
  }
""",
     """  g_ios_ptr_kind_down[kind] = down ? true : false;
  g_ios_pointer_button_down = g_ios_ptr_kind_down[0] || g_ios_ptr_kind_down[1] ||
                              g_ios_ptr_kind_down[2];
  if (down && kind != 0) {
    g_ios_poll_tick = 0;      /* build-49 */
    g_ios_gc_travel = 0.0;
  }
  if (kind == 0 && !down) {
    /* build-55: every left release passes through this choke point. */
    g_ios_lmb_up_ms = GHOST_GetMilliSeconds((GHOST_SystemHandle)system);
    g_ios_lmb_up_pos = p;
  }
""")

# --- 3. handlePointerPress Began: drop the echo ------------------------------
# Anchor is the build-46 primary branch exactly as fix_input_v46.py wrote it.
edit(W, "b55-began-guard",
     """    if (primary) {
      if (!g_ios_ptr_kind_down[0]) {
        [self emitPointerButton:0 down:YES at:p];
      }
    }
""",
     """    if (primary) {
      /* build-55: drop the recognizer's echo re-Began. A physical re-press
       * cannot arrive within 150 ms at (near-)identical sub-pixel
       * coordinates; the observed echo is same-frame and <1 px. Dropping it
       * here leaves the kind-0 flag false, so the echo's paired Ended is
       * already suppressed by the existing flag test. Genuine double-clicks
       * (>=150 ms apart, with real jitter) pass unchanged. */
      const uint64_t b55_now = GHOST_GetMilliSeconds((GHOST_SystemHandle)system);
      const double b55_dx = fabs((double)p.x - (double)g_ios_lmb_up_pos.x);
      const double b55_dy = fabs((double)p.y - (double)g_ios_lmb_up_pos.y);
      if (g_ios_lmb_up_ms != 0 && (b55_now - g_ios_lmb_up_ms) < 150 &&
          b55_dx < 8.0 && b55_dy < 8.0)
      {
        fprintf(stderr,
                "[b55-lmb] dropped Began echo (%llu ms, %.1f/%.1f px after UP)\\n",
                (unsigned long long)(b55_now - g_ios_lmb_up_ms),
                b55_dx,
                b55_dy);
      }
      else if (!g_ios_ptr_kind_down[0]) {
        [self emitPointerButton:0 down:YES at:p];
      }
    }
""")

print(f"BUILD-55 (left-button echo guard: Add Modifier popup no longer "
      f"self-closes) APPLIED OK ({len(applied)} edits)")
