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
