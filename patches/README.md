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
