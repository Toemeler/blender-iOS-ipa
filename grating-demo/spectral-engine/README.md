# Spectral Wave Optics — a physically-based render engine for the iOS build

A wavelength-based (spectral) path tracer that registers as a **render engine
selectable next to Cycles and EEVEE** (Render Properties → Render Engine →
*Spectral Wave Optics*). Built for scientifically faithful simulation of
dispersive and diffractive optics: diffraction gratings (Beugungsgitter),
CDs, and prisms.

It is pure Python + numpy via Blender's official `bpy.types.RenderEngine`
API — the same mechanism LuxCoreRender and appleseed use — so it runs
unmodified on the iOS build (no C++ plugin loading, which iOS forbids).

## Files

| file | purpose |
|---|---|
| `spectral_engine.py` | the addon: physics core + engine + UI panels |
| `verify_physics.py` | 26-check verification vs. published reference values |
| `build_demos.py` | headless builder for the three demo scenes |
| `blends/grating_spectral.blend` | linear grating, d = 2 µm, camera/light preset |
| `blends/cd_spectral.blend` | radial grating, d = 1.6 µm (real CD track pitch) |
| `blends/prism_spectral.blend` | 60° N-BK7 prism spectroscope view |
| `renders/*.png` | reference renders produced by this engine |

## What is exact, what is approximated

**Exact (within geometric + scalar wave optics):**

- Grating order **directions**: full conical (off-plane) grating equation via
  momentum conservation — the along-groove direction cosine is conserved,
  the cross-groove cosine shifts by mλ/d, for arbitrary incidence. m = 0
  reproduces the mirror direction exactly. Radial groove fields (CD) build
  the local frame from the disc axis at every hit point.
- Dispersion n(λ): **Sellmeier** equations with SCHOTT catalog coefficients
  (N-BK7, fused silica) — verified at the Fraunhofer F/d/C lines to <3·10⁻⁴.
- **Fresnel** reflectance/transmittance (unpolarized average), total internal
  reflection, at every glass interface, per wavelength.
- Colour: CIE 1931 2° colour matching functions (Wyman–Sloan–Shirley 2013
  analytic fit, ~1% of peak accuracy) → XYZ → linear sRGB. No RGB tricks —
  every ray carries one wavelength.
- Light transport: unbiased Monte-Carlo path tracing with next-event
  estimation on diffuse surfaces and Russian roulette.

**Approximated (documented, physically motivated):**

- Relative grating order **efficiencies** use the scalar Fraunhofer envelope
  of a lamellar (slit-array) grating, sinc²(π m w/d) — exact for an
  amplitude grating in scalar theory. Real pressed-pit or blazed gratings
  redistribute energy between orders (rigorous coupled-wave territory) but
  their order *directions* are identical. A `Uniform` mode is also provided.
- Lights are spectrally flat (Illuminant E). Diffuse surfaces are neutral
  grey (no speculative RGB→spectrum uplift). Polarization is averaged.
- `Groove irregularity` adds a small Gaussian jitter to the diffracted
  direction — the analogue of pitch/orientation variance across the
  illuminated spot; set 0 for a mathematically perfect grating.

## Using it on the iPad build

**Build-36 and later: nothing to install.** The engine is bundled into the app
(`scripts/startup/` auto-registration) and is selectable in Render Properties >
Render Engine the moment Blender launches. Open a demo .blend and press Render.
The steps below are only needed on build-35 or earlier.

1. Copy `spectral_engine.py` into *On My iPad → Blender* via the Files app.
2. Blender → Edit → Preferences → Add-ons → *Install from Disk* → select the
   file → enable **Spectral Wave Optics Renderer**. (Or open it in the
   Scripting workspace and *Run Script* for a single session.)
3. Render Properties → Render Engine → **Spectral Wave Optics**.
4. Open one of the demo .blends (engine, exposure and samples are already
   saved in the file) and hit Render. If you opened the file *before*
   enabling the addon, re-select the engine once.
5. Tag your own meshes in Object Properties → *Spectral Surface*
   (Diffuse / Mirror / Diffraction grating / Dispersive glass).

Performance notes: the tracer is numpy-vectorised but CPU-only and
brute-force (no BVH) — keep scenes to a few hundred triangles and start at
25–50 % resolution on the iPad. The viewport stays on EEVEE for editing;
the spectral engine renders stills (F12).

Requires numpy (bundled with official Blender builds, including this one).

## Verification

`python3 verify_physics.py` — all 26 checks pass, including:

- N-BK7 n(486.1/587.6/656.3 nm) = 1.52238 / 1.51680 / 1.51432 (SCHOTT catalog)
- fused silica n(587.6 nm) = 1.45846
- normal-incidence Fresnel R = ((n−1)/(n+1))² = 0.04217 for n = 1.5168
- grating: sin θₘ = m λ/d (30.000° for d = 1 µm, λ = 500 nm, m = 1);
  conical component conservation; m = 0 ≡ specular; even-order suppression
  at 50 % duty; energy conservation of the order sampler
- 60° BK7 prism minimum deviation: traced = analytic 2 asin(n sin A/2) − A
  = 38.65°, violet deviated more than red (39.40° vs 38.45° at 450/650 nm)

The demo builder additionally prints per-scene predictions (which order and
wavelength should appear at which plate coordinate / cone angle / deviation
angle) so every render can be checked against theory.
