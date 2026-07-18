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

### The open problem: modal operators

Middle-mouse orbit still does not work, and the diagnosis is now precise. An in-app modal-operator
trace (see *Debugging without a build* below) shows Blender receives a **textbook** middle drag:

```
EV MIDDLEMOUSE PRESS 397 1677
EV MOUSEMOVE 400 1677 ... 434 1666 ... 512 1660      (~500 smooth moves)
EV MIDDLEMOUSE RELEASE 706 1670
```

The `--debug-handlers` trace also shows the press being consumed inside the `3D View` keymap, and
at release the **whole keymap cascade runs again** — proving no modal handler was alive. Invoking
`bpy.ops.view3d.rotate('INVOKE_DEFAULT')` by hand and then moving the mouse does not orbit either,
with no mouse buttons involved at all.

**Conclusion: modal operators appear broken on this iOS build.** Everything that works uses an
immediate (non-modal) path — wheel zoom, and the two-finger trackpad orbit/pan/zoom. Everything
that fails needs a modal handler. A cheap confirmation is to press `B` in the viewport and drag a
box select (a modal operator with no button dependency): if no box appears, the theory holds.

**Current approach (build-50):** stop fighting the modal machinery and reuse the path that works.
While the middle button is held, the per-frame poll emits `UserInputEvent::PAN_GESTURE`
(→ `GHOST_EventTrackpad(Scroll)` → Blender `TRACKPADPAN`), which the default 3D View keymap binds
to `view3d.rotate`, and with Shift to `view3d.move` — both applied immediately inside `invoke()`.
`MIDDLEMOUSE` press/release are suppressed during drags (they would start the broken modal
operator); a press with under 6 px of travel still emits a real middle click at release.
**Untested at time of writing — verify on device.**

If build-50 works, the same trick fixes any other modal-dependent interaction. If it does not, the
next step is to fix modal handling itself: the iOS branch runs `WM_main_entry()` instead of
`WM_main()` (see `source/creator/creator.cc`), so start by comparing how that loop drives
`wm_event_do_handlers()` and whether modal handlers survive between iterations.

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
