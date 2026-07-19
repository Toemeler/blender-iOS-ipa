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

### Next: native middle-mouse (build-52)

With the gate narrowed, the build-50 emulation is no longer needed. Reverting build-50's
`MIDDLEMOUSE` suppression (the `if (kind == 2) { … return; }` block in `emitPointerButton`)
restores the genuine desktop mapping through real modal operators, with build-49's per-frame
`UITouch` polling supplying the motion:

| Input | Operator |
|---|---|
| MMB drag | `view3d.rotate` (orbit) |
| Shift + MMB drag | `view3d.move` (pan) |
| Ctrl + MMB drag | `view3d.zoom` |
| Shift + Ctrl + MMB drag | `view3d.dolly` |

Useful cross-check: `view3d.zoom` and `view3d.dolly` are **not** gated on the ios branch, so if
Ctrl+middle-drag ever zoomed while plain middle-drag did nothing, that alone isolates the gate.
Do this only after build-51 is confirmed on device, so the two changes stay independently testable.

### Input architecture (as patched)

UIKit does **not** deliver `touchesMoved`, pan-recognizer updates or pointer-region callbacks while
a non-primary mouse button is held, and `GCMouse`'s default main-queue delivery is starved in
`UITrackingRunLoopMode` for exactly that period. What *does* work, and what the current code relies
on:

- the tracked `UITouch` object stays positionally accurate throughout such a drag, and
- a `CADisplayLink` in `NSRunLoopCommonModes` keeps firing.

So button state comes from `UIEvent.buttonMask` in the raw touch overrides, and motion comes from
**polling** that `UITouch` once per display frame (`gcDisplayTick:`). `GCMouse` remains a fallback
(deltas accumulated on a background queue, drained by the same display link). Note also that the
long-press recognizer's behaviour is **version-dependent**: on iPadOS 27 it sometimes begins for
non-primary buttons, so its `Began` is gated on `sender.buttonMask` to avoid phantom left clicks.

### Debugging without a 40-minute build

Blender's Python console is the fastest instrument available. In a Text Editor area, run:

```python
import bpy
class T(bpy.types.Operator):
    bl_idname = "wm.evtrace"; bl_label = "trace"
    def modal(self, ctx, ev):
        print("EV", ev.type, ev.value, ev.mouse_x, ev.mouse_y, flush=True)
        return {'CANCELLED'} if ev.type == 'ESC' else {'PASS_THROUGH'}
    def invoke(self, ctx, ev):
        ctx.window_manager.modal_handler_add(self); return {'RUNNING_MODAL'}
bpy.utils.register_class(T)
bpy.ops.wm.evtrace('INVOKE_DEFAULT')
```

Every event Blender actually sees is then logged to `blender_console.log`. Operators that need a
3D view must be called with a context override (`bpy.context.temp_override(window=…, area=…,
region=…)`) or `poll()` fails. Python output reaches the log because `PYTHONUNBUFFERED` is set
before the interpreter starts (build-39) — without it, tracebacks are lost when the app is killed.

Build-48 also enables `G_DEBUG_EVENTS | G_DEBUG_HANDLERS` at startup, which prints every event and
keymap decision. Two traps when reading that output: Blender **suppresses mouse-motion events**
from the print (`!ISMOUSE_MOTION`), so their absence proves nothing; and the "which keymap item
matched" line goes through CLOG, not `printf`, so it does not appear either. What *is* meaningful
is where the cascade stops — a cascade that ends early means an item consumed the event.

### Workflow conventions

- The workflow **does not check out this repository** — it only clones Blender. Every patch is
  therefore **base64-embedded** in the workflow YAML; the copies in `patches/` are the reviewable
  source of truth and must be kept byte-identical to the embedded payloads.
- Patches are strictly ordered and apply to the output of the previous one. Each asserts its anchor
  occurs an exact number of times and exits non-zero otherwise, so a drifted anchor fails the build
  loudly instead of silently producing a wrong binary.
- Verify a new patch against the real sources before pushing: fetch the pinned Blender files, run
  the whole chain in order, then check brace/paren balance and that no stale symbol survives.
- `GHOST_WindowIOS.mm` compiles under **MRC, not ARC** — `__weak` will not compile there.
- Two APIs that look right and are not: `buttonMaskRequired` exists only on
  `UITapGestureRecognizer` (setting it on a long-press recognizer broke build-38), and a combined
  button mask means *chording*, not "any of these buttons".

## License

Blender is released under the **GNU General Public License**. See
<https://www.blender.org/about/license/> for the exact version and details, and the `COPYING` file in
the Blender source tree. The patches in this repository are provided under the same GPL terms.

## Trademark

**"Blender" and the Blender logo are trademarks of the Blender Foundation.** This is an **unofficial**
build and is **not affiliated with, endorsed by, or supported by** the Blender Foundation. If you
redistribute it, please make its unofficial status clear and avoid implying any official association.

## Credits

- The **Blender Foundation** and Blender contributors — for Blender and the iOS port.
- **Megabits Studio** — for the original tutorial on compiling Blender for iPad.
