# Patches applied to Blender's `ios` branch

These scripts run in CI against a fresh checkout of Blender's `ios` branch before the build.
They are the human-readable form of the modifications that produce the released IPA.

- **`fix_all_v9.py`** — source patches:
  - `wm.cc`: allocate `wm->runtime` before first use (fixes a launch crash).
  - `creator.cc`: disable Blender's own crash handler so iOS produces clean crash reports.
  - `GHOST_WindowIOS.mm`: add `GCKeyboard` hardware-keyboard handling + HID→GHOST key map,
    allow indirect-pointer (trackpad) touches for click/drag, enable trackpad scroll navigation,
    and log input events to `blender_input.log`.
- **`mkicon.py`** — render the Blender logo onto a charcoal background and install it as the app icon.
- **`fix_all_v23.py`** — everything in v22, plus Bluetooth-mouse fixes:
  - mouse **scroll wheel** now works: wheel notches arrive as near-instant Began->Ended scroll
    events whose delta was being swallowed by the translation cache (and each notch fired a
    phantom left click); the 0-touch scroll path now emits pure scroll with the full delta.
  - **area-edge resizing** is pixel-exact: pointer clicks are delivered from raw
    touchesBegan/Moved/Ended (no ~10 pt pan-recognizer hysteresis), and the UIPointerInteraction
    uses a per-location micro-region so the resize arrows stay in sync with the real hot zone.
- **`fix_all_v24.py`** — everything in v23, plus the two root causes found via on-device logs:
  - **Info.plist gains `UIApplicationSupportsIndirectInputEvents`** — without it, iPadOS delivered
    mouse/trackpad clicks as synthesized finger touches, so v22/v23's pointer handling never ran
    and clicks kept the ~10 pt pan hysteresis (resize arrow shown, click box-selected instead).
  - **Cycles kernel cache actually persists** — on iOS `serializeToURL:` fails with "Invalid URL"
    unless the destination file already exists (macOS creates it); pre-create dir + empty file,
    so kernels compile once and load near-instantly on later sessions.
- **`fix_input_v50.py`** — middle-drag emits trackpad PAN events instead of relying on
  `MIDDLEMOUSE` (superseded in effect by v51, which supplies the flag that made it work).
- **`fix_input_v51.py`** — the fix for external-mouse 3D-view navigation:
  - `GHOST_WindowIOS.mm`: the middle-drag poll emits `PAN_GESTURE_TWO_FINGERS` (`numFingers = 2`)
    instead of `PAN_GESTURE` (`numFingers = 1`), with the delta forwarded unnegated in view space
    to match `handlePan2f`.
  - `view3d_navigate_view_rotate.cc` / `view3d_navigate_view_move.cc`: the iOS-only
    `WM_EVENT_MULTITOUCH_TWO_FINGERS` gate is narrowed to `ISMOUSE_GESTURE(event->type)`, so it
    still rejects one-finger trackpad pans but no longer swallows physical mouse buttons. This gate
    returning `OPERATOR_FINISHED` was the real cause of "middle mouse does nothing", misread for
    many builds as broken modal operators.
- **`fix_input_v52.py`** — `b52-mmb-echo-guard` drops middle-button rising edges
  within 150 ms of a release, killing the phantom middle click produced when a
  stale UIKit `buttonMask` re-presses a button the GCMouse path already
  released. `b52-ui-click-diag` logs the UI click-routing decision
  (`active_but` / `over_but`) for every mouse press reaching `ui_region_handler`.
- **`fix_input_v53.py`** — replaces the b52 click probe with a decisive one: on a
  press that hits no button, dump winrct, v2d mask, block list with block-space
  and window-space rects, and a MOUSEMOVE counter — distinguishing mask-reject vs
  empty-block-list vs corrupt-winmat in one repro — then tag the region for a full
  rebuild plus a synthetic mouse-move so the panel recovers after one lost click.
