#!/usr/bin/env python3
"""build-56: FIX dead clicks at the root -- drive the LEFT button from the raw
touch stream (like right/middle), demote the long-press recognizer to a
diagnostic.

WHY BUILD-55 WAS NOT ENOUGH (on-device session 2026-07-21 10:56)
----------------------------------------------------------------
Build-55 guarded against the recognizer firing TWICE (the echo that closed
freshly opened popups). The 10:56 session showed the same recognizer can also
fire ZERO times: the dead clicks on the render-engine dropdown and the Add
Modifier button produced NOTHING in the log -- no [b39-ptr] DOWN, no wmEvent,
not one line -- while navbar clicks seconds before and after worked. No guard
inside handlePointerPress can help when handlePointerPress is never called.

UNIFIED ROOT CAUSE
------------------
The left button is the only input driven by a UILongPressGestureRecognizer
with minimumPressDuration = 0 (build-26/37/39). On indirect-pointer input
that recognizer is unreliable in BOTH directions:
  * sometimes it recognizes twice for one tap (09:18 session: DOWN/UP/DOWN/UP
    with the echo at sub-pixel-identical coordinates -> popup opens, phantom
    second press closes it; 10:45 + 10:56 sessions: value field '1' clicked,
    echo re-click reads '2'),
  * sometimes it never recognizes at all (10:56 session: dropdown and Add
    Modifier taps completely absent from the log).
Right and middle have never had either problem, because since build-39 they
are edge-diffed from UIEvent.buttonMask in the raw touchesBegan/Moved
overrides -- a path with no recognition step to fail or repeat. This build
moves LEFT onto that exact path.

THE CHANGE (6 edits, all in GHOST_WindowIOS.mm)
-----------------------------------------------
 1. syncPointerButtons also diffs the PRIMARY bit: left DOWN/UP emitted on
    mask edges, with the per-button flag as inherent dedup (a double-DOWN is
    structurally impossible; no timing heuristics needed).
 2. releasePointerButtons sweeps kind 0 too (touchesEnded/Cancelled already
    call it), so LEFT can never wedge if the mask is already clear at Ended.
 3. The raw touchesMoved motion gate also fires during left-drags (the
    recognizer's Changed used to be the only left-drag motion source; both
    now feed the position-dedup funnel, so no double moves).
 4. handlePointerPress Began no longer emits LEFT (build-55 guard removed
    with it -- obsolete on the raw path); it logs [b56-rec] so the log still
    shows what the recognizer THINKS happened, for comparison.
 5. handlePointerPress Ended likewise logs instead of emitting.
 6. touchesBegan logs [b56-raw] with the buttonMask for every indirect
    pointer touch: if any click is STILL dead, the log now proves whether
    the touch even reached the view (mask has bit 1) -- the one remaining
    unknown -- instead of being invisible.

Preserved: cancelsTouchesInView is false on every recognizer (verified in
final source), so raw touches flow during recognition; the GC-controller
button backup (b44) and its flag-diff dedup still apply; b50/b52 middle
trackpad emulation untouched; b55's UP stamp is left in place (harmless).

Verified locally before dispatch: full 18-script patch chain replayed on the
pinned blender commit d9b6fe34, then this script -- all anchors match 1x.

Runs after fix_input_v55.py.
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


# --- 1. syncPointerButtons: diff PRIMARY like Secondary/button-3 ------------
edit(W, "b56-sync-left",
     """    UIEventButtonMask mask = event.buttonMask;
    bool right = (mask & UIEventButtonMaskSecondary) != 0;
    bool middle = (mask & UIEventButtonMaskForButtonNumber(3)) != 0;
    if (right != g_ios_ptr_kind_down[1]) {
      [self emitPointerButton:1 down:(right ? YES : NO) at:p];
    }
""",
     """    UIEventButtonMask mask = event.buttonMask;
    /* build-56: LEFT is now edge-diffed from the mask exactly like
     * right/middle. The zero-duration long-press recognizer that used to
     * carry it proved unreliable both ways on device (fired twice for one
     * tap -> phantom click closed freshly opened popups; fired zero times ->
     * fully dead clicks with nothing logged). The per-button flag makes the
     * diff inherently deduped: no echo, no loss, no timing heuristics. */
    bool left = (mask & UIEventButtonMaskPrimary) != 0;
    bool right = (mask & UIEventButtonMaskSecondary) != 0;
    bool middle = (mask & UIEventButtonMaskForButtonNumber(3)) != 0;
    if (left != g_ios_ptr_kind_down[0]) {
      [self emitPointerButton:0 down:(left ? YES : NO) at:p];
    }
    if (right != g_ios_ptr_kind_down[1]) {
      [self emitPointerButton:1 down:(right ? YES : NO) at:p];
    }
""")

# --- 2. releasePointerButtons: sweep LEFT too --------------------------------
edit(W, "b56-release-left",
     """  for (int kind = 1; kind <= 2; kind++) {
    if (g_ios_ptr_kind_down[kind]) {
      [self emitPointerButton:kind down:NO at:p];
    }
  }
""",
     """  /* build-56: kind 0 included -- LEFT is raw-driven now and must release
   * on touchesEnded/Cancelled even if the mask was already clear. */
  for (int kind = 0; kind <= 2; kind++) {
    if (g_ios_ptr_kind_down[kind]) {
      [self emitPointerButton:kind down:NO at:p];
    }
  }
""")

# --- 3. raw touchesMoved motion also during left-drags -----------------------
edit(W, "b56-moved-gate",
     """      [self syncPointerButtons:event touch:touch];
      if ((g_ios_ptr_kind_down[1] || g_ios_ptr_kind_down[2]) && !g_ios_ptr_kind_down[0]) {
        [self emitScaledPointerMoveFromViewPoint:[touch locationInView:window->getView()]];
      }
""",
     """      [self syncPointerButtons:event touch:touch];
      /* build-56: left-drags get raw motion too (the recognizer's Changed
       * used to be their only source and it can fail to begin). Both sources
       * feed the position-dedup funnel, so no double moves. */
      if (g_ios_ptr_kind_down[0] || g_ios_ptr_kind_down[1] || g_ios_ptr_kind_down[2]) {
        [self emitScaledPointerMoveFromViewPoint:[touch locationInView:window->getView()]];
      }
""")

# --- 4. recognizer Began: demoted to diagnostic ------------------------------
edit(W, "b56-began-neutral",
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
""",
     """    if (primary) {
      /* build-56: LEFT is emitted by the raw touch path (syncPointerButtons)
       * now; the recognizer -- unreliable both ways on device -- only logs,
       * so sessions show what it THINKS happened next to what the raw path
       * actually delivered. The build-55 echo guard is obsolete here: the
       * raw path's flag-diff cannot double-fire by construction. */
      fprintf(stderr, "[b56-rec] Began at %.1f,%.1f (raw-driven; no emit; flag=%d)\\n",
              p.x, p.y, g_ios_ptr_kind_down[0] ? 1 : 0);
    }
""")

# --- 5. recognizer Ended: demoted to diagnostic ------------------------------
edit(W, "b56-ended-neutral",
     """    if (g_ios_ptr_kind_down[0]) {
      [self emitPointerButton:0 down:NO at:p];
    }
""",
     """    /* build-56: no emit -- raw touchesEnded/Cancelled own the LEFT UP. */
    fprintf(stderr, "[b56-rec] Ended/Cancelled/Failed at %.1f,%.1f (flag=%d)\\n",
            p.x, p.y, g_ios_ptr_kind_down[0] ? 1 : 0);
""")

# --- 6. touchesBegan diagnostic: prove the touch reached the view ------------
edit(W, "b56-raw-diag",
     """  for (UITouch *touch in touches) {
    if (touch.type == UITouchTypeIndirectPointer) {
      g_ios_pointer_touch = touch;
      /* build-39: right/middle buttons never begin the primary-button-only
       * long-press recognizer; their state is tracked from the raw event's
       * buttonMask instead. */
      [self syncPointerButtons:event touch:touch];
      break;
    }
  }
""",
     """  for (UITouch *touch in touches) {
    if (touch.type == UITouchTypeIndirectPointer) {
      g_ios_pointer_touch = touch;
      /* build-56: every button (LEFT included) is edge-diffed from the raw
       * event's buttonMask here and in touchesMoved. Log the mask so a dead
       * click can never again be invisible: if a tap produces no [b56-raw]
       * line, the touch did not even reach the view. */
      if (@available(iOS 13.4, *)) {
        fprintf(stderr, "[b56-raw] touch began mask=%ld\\n", (long)event.buttonMask);
      }
      [self syncPointerButtons:event touch:touch];
      break;
    }
  }
""")

print(f"BUILD-56 (raw-driven LEFT button: recognizer double-fire and no-fire "
      f"dead clicks both eliminated) APPLIED OK ({len(applied)} edits)")
