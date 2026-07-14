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
