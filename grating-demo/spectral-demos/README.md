# Spectral diffraction demos (CD + grating)

Two physically-based demonstrations of diffraction color, rendered with stock Cycles using
a **true spectral multi-pass pipeline**: the scene is rendered once per wavelength band as a
monochrome intensity pass, and the passes are integrated against the CIE 1931 color-matching
functions to sRGB. Every wavelength is light-transported independently — real spectral
rendering, no RGB mixing during transport.

Both demos use the grating equation `sin(theta_m) = sin(theta_i) + m*lambda/d`, summed over
diffraction orders, via the monochromatic OSL shader `diffraction_mono.osl`.

## Results

- `cd_result.png` — a CD: reflective **radial** grating at real CD track pitch (~1600 nm).
  The iridescent rainbow sweeps around the disc, exactly as a CD does under a small bright
  light. Full spectral spread (all hue bins present).
- `grating_result.png` — a flat reflective diffraction grating (groove spacing 1000 nm).
  Clean diffraction orders fanning violet -> red, with red deviating most (the diffraction
  signature, opposite of a prism).

## Files

- `diffraction_mono.osl` — single-wavelength grating shader (intensity only), the physics core.
- `cd_scene.py` / `grating_scene.py` — scene builders (called per wavelength by the driver).
- `render_demo.py` — shared spectral driver. Renders N wavelength passes as linear EXR:
      blender -b -P render_demo.py -- <scene.py> <out_prefix> <bands> <samples> <rx> <ry>
  e.g.  blender -b -P render_demo.py -- cd_scene.py cd 16 96 640 480
- `integrate_demo.py` — integrates the passes into an sRGB PNG (needs numpy + imageio):
      OPENCV_IO_ENABLE_OPENEXR=1 python3 integrate_demo.py cd
- `cd_demo.blend` / `grating_demo.blend` — self-contained scenes (OSL embedded internally),
  open directly in Blender. They open at a single mid-band wavelength (550 nm) as a preview;
  the full rainbow comes from running the multi-pass pipeline above.

## Running on the iPad build

The per-wavelength render passes run on-device (CPU, OSL enabled — requires the OSL-enabled
IPA). The lightweight integration step (`integrate_demo.py`) runs on any machine with Python;
copy the `*_passes` folder off the iPad and integrate there. Increase `bands` (16 -> 32) for
a smoother spectrum.

## Note on the prism demo

A third demo (a glass prism showing refractive dispersion — white light in, rainbow out) was
prototyped but is **not included**: refraction through a single glass prism spreads the visible
spectrum only ~2-3 degrees, which does not separate visibly at this scene scale, and the bright
entry beam dominated every wavelength pass. It is refraction, not diffraction, so it is also
outside the scope of the diffraction-grating feature. The two demos here cover the diffraction
physics directly.
