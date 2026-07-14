# Beugungsgitter (diffraction grating) demo — physically-based spectral diffraction in Cycles

- `beugungsgitter_demo.blend` — self-contained scene. Material slot 1 uses the OSL
  diffraction shader (embedded as an internal script; per-sample wavelength via the
  grating equation `sin(θm) = sin(θi) + mλ/d`). Material slot 2 is a node-only
  approximation that also runs on the Metal GPU backend.
- `diffraction_grating.osl` — Miguel Porces' ("Secrop") 2014 shader, one line updated
  for modern Cycles (`microfacet_beckmann` → `microfacet("beckmann", …)`).
- `diffraction_grating_v2.osl` / `scene_v2.py` — v2: stratified 8-bin spectral
  integration per sample (smooth continuous rainbows instead of RGB speckle),
  orders capped at |m|<=3 to respect Cycles' per-shader closure limit, slight
  0.03 roughness, off-axis light, 512 samples + denoising. The .blend now uses v2.
- `setup_grating.py` — script that rebuilds the whole scene from scratch
  (auto-falls back to the node material where OSL is unavailable).

**On the iPad:** copy the .blend into Files → On My iPad → Blender, open it.
The OSL material needs a build with `WITH_CYCLES_OSL=ON` and Cycles set to CPU
with "Open Shading Language" enabled; otherwise switch the plate to the second
material slot (node approximation, renders on Metal).

Requires Blender 5.x. Verified in Blender 5.0.1 (CPU + OSL): renders full
spectral orders (violet→red) from a 1000 nm groove-spacing grating.

## Spectral pipeline (true spectral rendering with stock Cycles)

`spectral_render.py` renders the scene once per wavelength band (default 16 bands,
390–730 nm) using `diffraction_mono.osl` (single-wavelength grating, intensity-only),
saving linear EXR passes. `integrate_spectral.py` then integrates the passes against
the CIE 1931 color-matching functions (Wyman–Sloan–Shirley fit) → XYZ → sRGB with
hue-preserving gamut mapping. Every wavelength is light-transported independently:
this is real spectral rendering, no RGB mixing during transport.

    blender -b -P spectral_render.py -- 16 96 640 480
    python3 integrate_spectral.py      # needs numpy + imageio (or OpenEXR)

More bands = smoother spectrum (32 is lovely, 16 is fine). Works with the node
material too, so the same pipeline runs against the Metal GPU backend on desktop;
on the iPad the integration step needs to run on a PC (or any Python) afterwards.
