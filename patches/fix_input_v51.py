#!/usr/bin/env python3
"""build-51: the actual reason middle-mouse orbit/pan never worked.

ROOT CAUSE (found by reading the ios branch, not by guessing):
`viewrotate_invoke` and `viewmove_invoke` on Blender's ios branch begin with a
hard iOS-only gate --

    #ifdef WITH_APPLE_CROSSPLATFORM
      /* Only scroll view with multiple fingers on iOS. */
      if (!(event->flag & WM_EVENT_MULTITOUCH_TWO_FINGERS)) {
        return OPERATOR_FINISHED;
      }
    #endif

-- see source/blender/editors/space_view3d/view3d_navigate_view_rotate.cc:370
and view3d_navigate_view_move.cc:108.  `WM_EVENT_MULTITOUCH_TWO_FINGERS` is set
in wm_event_system.cc ONLY for `GHOST_TEventTrackpadData::numFingers == 2`, an
iOS-branch-specific field.  `generateUserInputEvents` sets numFingers = 2 for
`PAN_GESTURE_TWO_FINGERS` and numFingers = 1 for plain `PAN_GESTURE`.

Consequences, all of which match the on-device logs exactly:

  * build-50 emits plain PAN_GESTURE during a middle drag -> numFingers = 1 ->
    the flag is never set -> viewrotate_invoke returns OPERATOR_FINISHED
    immediately, rotating by nothing.  Returning FINISHED still counts as
    WM_HANDLER_BREAK, so the keymap cascade STOPS at '3D View' -- which is why
    the build-48 trace looked like the event was handled.  It was: handled by
    an early return.
  * MIDDLEMOUSE press (builds 37-49) hits the same gate.  A button event can
    never carry a trackpad multitouch flag (`event.flag` is zeroed per event in
    wm_event_add_ghostevent), so view3d.rotate returned FINISHED before ever
    reaching view3d_navigate_invoke_impl -- no modal handler was ever added.
    That is why the release re-ran the whole cascade, and why calling
    bpy.ops.view3d.rotate('INVOKE_DEFAULT') by hand did nothing either.
    MODAL OPERATORS ARE NOT BROKEN ON THIS BUILD; the handoff's conclusion was
    wrong.  Only the two-finger gate was.
  * Two-finger trackpad orbit works because handlePan2f emits
    PAN_GESTURE_TWO_FINGERS -> numFingers = 2 -> flag set -> gate passes.

FIX 1 (b51-mmb-two-fingers) -- makes middle-drag orbit/pan work now.
Emit PAN_GESTURE_TWO_FINGERS from the build-50 middle-drag poll, i.e. reuse
byte-for-byte the path the trackpad already proves on device.  The y sign is
also corrected: handlePan2f forwards `translationInView` deltas UNNEGATED
(view space, y-down) and the two-finger event sets isDirectionInverted = true,
which flips viewrotate's delta term again.  build-50 negated y on top of that,
which would have orbited vertically the wrong way; drop the negation so the
direction matches the trackpad and the desktop exactly.

FIX 2 (b51-rotate-gate / b51-move-gate) -- narrows the gate to what it was
meant for.  The gate exists so a single-finger trackpad scroll does not orbit;
it should never have applied to physical mouse buttons.  Restrict it to actual
trackpad gesture events (ISMOUSE_GESTURE covers MOUSEPAN..MOUSESMARTZOOM) and
let button-driven invokes through.  This is INERT while build-50 suppresses
MIDDLEMOUSE during drags, and is what makes native MMB orbit/pan/zoom/dolly
possible the moment that suppression is dropped.  It cannot double up trackpad
navigation, because one-finger PAN_GESTURE is still a gesture and still gated.

Anchors target the sources as they exist AFTER fix_input_v50.py.
"""
import sys

W = "blender/intern/ghost/intern/GHOST_WindowIOS.mm"
R = "blender/source/blender/editors/space_view3d/view3d_navigate_view_rotate.cc"
M = "blender/source/blender/editors/space_view3d/view3d_navigate_view_move.cc"

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


# --- FIX 1: the middle-drag emulation must look like a TWO-FINGER trackpad pan,
# because that is the only kind of pan the ios branch lets navigate. ----------
edit(W, "b51-mmb-two-fingers",
     """        CGPoint tran = CGPointMake(d.x, -d.y); /* view y-down -> GHOST y-up */
        UserInputEvent pan_info(&loc, &tran, nullptr, false);
        pan_info.add_event(UserInputEvent::EventTypes::PAN_GESTURE);
""",
     """        /* build-51: PAN_GESTURE sets numFingers = 1, and the ios branch's
         * viewrotate_invoke/viewmove_invoke return OPERATOR_FINISHED for any
         * pan that is not flagged WM_EVENT_MULTITOUCH_TWO_FINGERS -- which is
         * why build-50 was consumed by the '3D View' keymap and still did
         * nothing.  PAN_GESTURE_TWO_FINGERS sets numFingers = 2 (and
         * isDirectionInverted = true, exactly like handlePan2f), so the delta
         * is forwarded UNNEGATED in view space to match that path's direction. */
        CGPoint tran = CGPointMake(d.x, d.y); /* view space, as handlePan2f */
        UserInputEvent pan_info(&loc, &tran, nullptr, false);
        pan_info.add_event(UserInputEvent::EventTypes::PAN_GESTURE_TWO_FINGERS);
""")

# --- FIX 2: stop the gate from swallowing real mouse buttons. ----------------
GATE_ROTATE_OLD = """#ifdef WITH_APPLE_CROSSPLATFORM
  /* Only scroll view with multiple fingers on iOS. */
  if (!(event->flag & WM_EVENT_MULTITOUCH_TWO_FINGERS)) {
    return OPERATOR_FINISHED;
  }
#endif
"""
GATE_ROTATE_NEW = """#ifdef WITH_APPLE_CROSSPLATFORM
  /* Only scroll view with multiple fingers on iOS.
   * build-51: restrict this to actual trackpad GESTURES.  It used to reject
   * every event without WM_EVENT_MULTITOUCH_TWO_FINGERS, and a button event
   * can never carry that flag (it is set only for trackpad events with
   * numFingers == 2), so MIDDLEMOUSE orbit returned OPERATOR_FINISHED here
   * before a modal handler was ever installed -- the real cause of "middle
   * mouse does nothing", misdiagnosed for many builds as broken modal
   * operators.  One-finger pans are still gated, so trackpad behaviour is
   * unchanged. */
  if (ISMOUSE_GESTURE(event->type) && !(event->flag & WM_EVENT_MULTITOUCH_TWO_FINGERS)) {
    return OPERATOR_FINISHED;
  }
#endif
"""
edit(R, "b51-rotate-gate", GATE_ROTATE_OLD, GATE_ROTATE_NEW)

GATE_MOVE_OLD = """#ifdef WITH_APPLE_CROSSPLATFORM
  /* Only handle inverted events for 3D view interaction on iOS */
  if (!(event->flag & WM_EVENT_MULTITOUCH_TWO_FINGERS)) {
    return OPERATOR_FINISHED;
  }
#endif
"""
GATE_MOVE_NEW = """#ifdef WITH_APPLE_CROSSPLATFORM
  /* Only handle inverted events for 3D view interaction on iOS.
   * build-51: gesture events only -- see view3d_navigate_view_rotate.cc. */
  if (ISMOUSE_GESTURE(event->type) && !(event->flag & WM_EVENT_MULTITOUCH_TWO_FINGERS)) {
    return OPERATOR_FINISHED;
  }
#endif
"""
edit(M, "b51-move-gate", GATE_MOVE_OLD, GATE_MOVE_NEW)

print(f"BUILD-51 (middle-drag pans as two fingers; iOS navigation gate no longer "
      f"swallows mouse buttons) APPLIED OK ({len(applied)} edits)")
