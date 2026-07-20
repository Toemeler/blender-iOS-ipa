# Unofficial Blender for iPad / iOS (sideload build)

> ⚠️ **Unofficial community build. NOT affiliated with, endorsed by, or supported by the Blender Foundation.**
> This is a **pre-alpha, experimental** build of Blender's in-progress iOS port. Expect bugs and crashes.

This repository is an automated pipeline that compiles Blender's experimental `ios` branch into an
`.ipa` you can **sideload onto an iPad — no Mac required**, using GitHub Actions' macOS runners.

---

## Status & expectations

- Based on Blender's `ios` branch, which the Blender Foundation has **put on hold**. It began as a
  sculpting-focused tech demo, not a finished application.
- **Pre-alpha quality.** It may crash on launch or during use, and large parts of the UI/input are
  works in progress.
- Provided **as-is, with no warranty**, for people who want to experiment.

## What you need

- An iPad — **Apple-silicon (M1 or newer) strongly recommended**.
- A Windows / macOS / Linux PC for sideloading.
- A free or paid Apple ID.
- A sideloading tool: **Sideloadly**, **AltStore / SideStore**, or **Impactor**.

## Install (sideload)

1. Download the latest `Blender-ios.ipa` from the [**Releases**](../../releases) page.
2. Open your sideloading tool on your PC and connect the iPad.
3. Load the IPA, sign in with your Apple ID, and install.
4. On the iPad: **Settings → General → VPN & Device Management → trust your developer certificate**.
5. Launch Blender.

**Free Apple ID note:** the app expires after **7 days** (just re-sideload), you can have a limited
number of sideloaded apps, and special entitlements (e.g. increased memory) are stripped.

## Usage notes

- Pair a **Magic Keyboard and trackpad** — Blender is heavily keyboard-driven. Hardware-keyboard and
  trackpad support are **work-in-progress** in this build (see `patches/`).
- **Apple Pencil pressure** works for sculpting.
- Move files in/out via **Files app → On My iPad → Blender**.

## Known limitations

- May crash on launch or during use.
- Keyboard shortcuts and trackpad navigation are only partially implemented.
- Add-ons / the Extensions platform do **not** work.
- No official support of any kind.

## How it's built

The workflow ([`.github/workflows/build-ios-ipa.yml`](.github/workflows/build-ios-ipa.yml)):

1. Clones Blender's `ios` branch from `projects.blender.org` **with Git LFS** — this is essential, as
   Blender's data files (including `startup.blend`) are stored in LFS; without it the app cannot start.
2. Fetches the precompiled iOS dependency libraries (`make_update.py --use-ios-libraries`).
3. Applies the patches in [`patches/`](patches/).
4. Builds with the Xcode toolchain and packages an **unsigned** IPA (your sideloading tool re-signs it).

## Modifications — GPL corresponding source

Blender is Free Software under the GNU General Public License. This build **modifies** Blender, so, to
honor the GPL, the **complete corresponding source** is:

- **Upstream Blender source:** the `ios` branch at <https://projects.blender.org/blender/blender>
  (this pipeline builds the branch HEAD; as of writing that is commit `d9b6fe34`).
- **Our patches:** in [`patches/`](patches/) of this repository. In summary they:
  - fix a null-pointer crash in `wm_add_default` (startup window-manager setup),
  - add hardware-keyboard shortcut support via `GCKeyboard` (HID → Blender key map), including
    the numeric keypad (`GHOST_kKeyNumpad*`, build-39),
  - enable Magic Keyboard trackpad and external-mouse input (indirect-pointer click/drag, real
    wheel notches, per-button press tracking, right-click during a drag),
  - stop mouse hover from being reported to Blender as an active stylus (build-39) — this had
    been corrupting eyedropper, number-field editing and assorted clicks,
  - fix 3D-view navigation from an external mouse: the iOS branch rejected every navigation
    event lacking `WM_EVENT_MULTITOUCH_TWO_FINGERS`, which no mouse event can carry
    (build-51),
  - bundle a **Spectral Wave Optics** render engine plus an iOS-native numpy (build-42/45),
  - add an input-event log (`blender_input.log`), a console log (`blender_console.log`) and a
    startup log for the render engine (`spectral_startup.log`) in the app's Documents folder,
  - set an application icon.

To reproduce, apply the patch scripts to a fresh checkout of that commit and build — which is exactly
what the workflow does.

## Development handoff (current state)

This section is the working context for whoever picks the project up next.

### Fixed and verified on device

- **Spectral Wave Optics render engine** — appears next to EEVEE/Cycles and registers cleanly
  (`spectral_startup.log`: `physics module imported (numpy OK)` → `registered OK`).
  The engine needs numpy, and the build originally bundled the **macOS host** numpy, so `dlopen`
  refused it (`have 'macOS', need 'iOS'`). The packaging step now installs BeeWare's
  arm64 `iphoneos` numpy 1.26.2 wheel (sha256-pinned), renames its `*.cpython-311-iphoneos.so`
  libraries to the `-darwin` suffix Blender's importer looks for, and — because Blender links
  CPython **statically** into the executable, so `@rpath/Python.framework/Python` cannot exist —
  rewrites each extension's Mach-O bind opcodes to **flat-namespace lookup**
  (`patches/numpy_flat_namespace.py`, the on-disk form of `-undefined dynamic_lookup`).
  `fix_python_v42.py` force-keeps (`-Wl,-u`) the 15 CPython API symbols numpy imports that Blender
  itself never references and the linker would otherwise dead-strip.
- **Mouse wheel** — real `WHEELUP`/`WHEELDOWN` notches (zoom, list scrolling, Ctrl/Shift+wheel).
- **Numpad shortcuts** on external keyboards (viewport views, numpad enter, `+`/`-`).
- **Left click/drag, right click, and button chords** — e.g. right-click while left-dragging
  pairs correctly and no button can get stuck (which used to make clicks stop working entirely).

### Solved (build-51): the iOS two-finger navigation gate

Middle-mouse orbit never worked because Blender's `ios` branch **refuses to navigate the 3D view
from anything that is not flagged as a two-finger trackpad gesture**. Both `viewrotate_invoke`
(`view3d_navigate_view_rotate.cc`) and `viewmove_invoke` (`view3d_navigate_view_move.cc`) open with:

```c
#ifdef WITH_APPLE_CROSSPLATFORM
  /* Only scroll view with multiple fingers on iOS. */
  if (!(event->flag & WM_EVENT_MULTITOUCH_TWO_FINGERS)) {
    return OPERATOR_FINISHED;
  }
#endif
```

`WM_EVENT_MULTITOUCH_TWO_FINGERS` is set in `wm_event_system.cc` **only** when
`GHOST_TEventTrackpadData::numFingers == 2` — an iOS-branch-only field.
`generateUserInputEvents` sends `numFingers = 1` for `PAN_GESTURE` and `2` for
`PAN_GESTURE_TWO_FINGERS`, and the latter is emitted from exactly one place: `handlePan2f`, the
two-finger trackpad gesture. That single fact explains everything:

- **Real `MIDDLEMOUSE` (builds 37–49) could never pass.** `wm_event_add_ghostevent` zeroes
  `event.flag` on every event and only the trackpad branch ORs the multitouch bits in, so a button
  event cannot carry the flag. `view3d.rotate` returned `OPERATOR_FINISHED` before
  `view3d_navigate_invoke_impl` ever ran, so no modal handler was ever installed.
- **Build-50's emulation could not pass either**, because it emitted plain `PAN_GESTURE`
  (`numFingers = 1`).
- **Two-finger trackpad orbit works** because it is the one path that sets the flag.

**Modal operators are NOT broken on this build.** The earlier diagnosis was an illusion:
`OPERATOR_FINISHED` still produces `WM_HANDLER_BREAK`, which ends the keymap cascade — so a no-op
early return is indistinguishable from a successful handle in a `--debug-handlers` trace. The
cascade re-running at release, and `bpy.ops.view3d.rotate('INVOKE_DEFAULT')` doing nothing, are
both direct consequences of the same early return (a synthesised event carries no multitouch flag).
The `WM_main_entry()` vs `WM_main()` lead is a dead end.

**The fix (build-51, `patches/fix_input_v51.py`), three anchored edits:**

- `b51-mmb-two-fingers` — the middle-drag poll now emits `PAN_GESTURE_TWO_FINGERS`, reusing
  byte-for-byte the path the trackpad already proves on device. Build-50's `-d.y` negation is
  dropped: `handlePan2f` forwards `translationInView` deltas unnegated in view space, and the
  two-finger event also sets `isDirectionInverted = true`, which flips the delta term again inside
  `viewrotate_invoke_impl` (`m_xy = 2*xy - prev_xy`). Keeping the negation would orbit vertically
  backwards.
- `b51-rotate-gate` / `b51-move-gate` — narrows the gate to `ISMOUSE_GESTURE(event->type) && !flag`.
  `ISMOUSE_GESTURE` covers `MOUSEPAN..MOUSESMARTZOOM`, so one-finger trackpad pans are still
  rejected and trackpad behaviour is bit-for-bit unchanged, but physical mouse buttons are no
  longer swallowed. Inert while build-50 still suppresses `MIDDLEMOUSE` during drags.

Verified to apply cleanly on top of the whole chain (v27 → v50) against the pinned sources, with
brace/paren balance preserved. **Untested on device at time of writing — verify.**

### Confirmed on device (build-51)

Middle-drag orbit and Shift+middle-drag pan work. The console log shows 807
`TRACKPADPAN` events across six clean drags, and every `MIDDLEMOUSE` press now
reaches `view3d.rotate` / `view3d.move` for real.

### Fixed in build-52: phantom middle click

Three of six middle drags ended with a middle click nobody made:

```
[b44-gcm] btn kind=2 pressed=0 (flag=1)
[b50-mmb] drag end (travel 3890.1)
[b50-mmb] press (trackpad emulation armed)     <-- nobody touched the mouse
[b50-mmb] click (travel 0.0)
```

Two sources drive the middle button. The GCMouse handler reports the release
first and clears `g_ios_ptr_kind_down[2]`; a raw UIKit touch still carrying
button 3 in its `event.buttonMask` then reaches `syncPointerButtons`, sees the
flag disagree and re-presses it. `touchesEnded` releases it again, and
build-50's zero-travel click path turns that into a real middle click.

Harmless before build-51 because the two-finger gate swallowed it. Not harmless
now: `MIDDLEMOUSE` press invokes `view3d.rotate` for real, and both navigation
operators carry `OPTYPE_BLOCKING | OPTYPE_GRAB_CURSOR_XY`, so every long drag
ended by briefly entering a blocking modal operator with a cursor grab.
`b52-mmb-echo-guard` drops middle-button rising edges within 150 ms of a
release; no physical button bounces that fast.

### Open: dead clicks in the Properties editor after the search popup (build-53 probe + self-heal)

Two sessions, same signature: clicks in the Properties editor work until the Add
Modifier search popup has been used; afterwards a press in the main region reports

```
[b52-ui] LMB PRESS at (2851,1285) region=0 active_but=none over_but=none
```

`ui_but_find_mouse_over()` finds nothing where the user visibly clicks a button,
while the nav-bar region keeps hit-testing fine. The build-52 hypotheses are both
disproven by this line: no stale active button exists (`active_but=none`), and
hover activation is irrelevant because the direct hit test itself misses. Draw
activity continued after the tab switch (39 `make_drawable` calls before the dead
click), so blocks were rebuilt -- and the hit test still misses. The input layer,
the GHOST DOWN/UP pairing, dispatch and the repo's own patches (v27's textedit
guards only skip a string overwrite; the wm.cc edit is an allocation fix) are all
ruled out.

That leaves exactly three mechanisms inside `ui_but_find_mouse_over_ex`:

1. `ui_region_contains_point_px()` rejects the point via the View2D mask/scroller
   test (the winrct test cannot fail for a dispatched event);
2. `region->runtime->uiblocks` is empty -- layout freed blocks and never rebuilt;
3. blocks exist but `block->winmat` maps the click outside every button -- the
   matrix snapshot was captured under a wrong viewport (the popup's?).

`fix_input_v53.py` replaces the b52 probe with one that decides this in a single
repro: on any press that hits no button it dumps winrct, the v2d mask, the
local-space click, the block count, and per block both the block-space and
window-space rects (`brect` vs `wrect` -- garbage transform is visible at a
glance), plus a MOUSEMOVE counter for hover-delivery starvation. It then
**self-heals**: tags the region for a full rebuild and queues a synthetic
mouse-move, so if the state is rebuildable the user loses one click instead of
the whole panel. The 3D viewport main region has no `ui_region_handler`
(confirmed: no b52-ui lines for any viewport click), so this cannot cause
spurious viewport redraws. Dumps are capped at 40/session.

**To close this out:** reproduce once on build-53 (add a modifier via the search
popup, then click Add Modifier again), and read the `[b53-hit]` block. `contains=0`
with the mask values names mechanism 1; `nblocks=0` names 2; sane blocks whose
`wrect` excludes the click names 3. Also note whether the click *after* the dead
one works (recovery succeeded -> the state is rebuildable, and the real fix is at
whatever left it stale).
