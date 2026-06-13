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
  - add hardware-keyboard shortcut support via `GCKeyboard` (HID → Blender key map),
  - enable Magic Keyboard trackpad input (indirect-pointer click/drag + scroll navigation),
  - add an input-event log (written to `blender_input.log` in the app's Documents folder),
  - set an application icon.

To reproduce, apply the patch scripts to a fresh checkout of that commit and build — which is exactly
what the workflow does.

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
