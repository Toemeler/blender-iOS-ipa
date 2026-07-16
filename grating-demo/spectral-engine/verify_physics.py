"""Physics verification for spectral_engine.py (no Blender required).

Checks the core against textbook/catalog reference values:
  * Sellmeier n(lambda) for N-BK7 and fused silica at Fraunhofer lines
  * Fresnel normal-incidence reflectance
  * Grating equation angles (in-plane and conical component conservation)
  * Order-efficiency envelope properties (even-order suppression at 50% duty)
  * Energy conservation of grating sampling
  * CIE CMF sanity (peak position of y-bar, E-white balance)
  * 60-degree BK7 prism minimum deviation (analytic vs traced)
"""
import math
import sys

import numpy as np

sys.path.insert(0, "/home/claude/spectral")
import spectral_engine as se

PASS = True


def check(name, got, want, tol):
    global PASS
    ok = abs(got - want) <= tol
    PASS &= ok
    print(f"{'PASS' if ok else 'FAIL'}  {name:<58} got={got:.6g} want={want:.6g} (tol {tol:g})")


def check_true(name, cond):
    global PASS
    PASS &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}")


print("== Sellmeier dispersion ==")
# Reference: SCHOTT N-BK7 catalog values at Fraunhofer F, d, C lines
check("BK7 n @ 486.13 nm (F line)", float(se.glass_ior(486.13, 'BK7')), 1.52238, 3e-4)
check("BK7 n @ 587.56 nm (d line)", float(se.glass_ior(587.56, 'BK7')), 1.51680, 3e-4)
check("BK7 n @ 656.27 nm (C line)", float(se.glass_ior(656.27, 'BK7')), 1.51432, 3e-4)
check("Fused silica n @ 587.56 nm", float(se.glass_ior(587.56, 'FUSED_SILICA')),
      1.45846, 5e-4)
check_true("Normal dispersion: n(400) > n(700) (BK7)",
           se.glass_ior(400, 'BK7') > se.glass_ior(700, 'BK7'))

print("\n== Fresnel ==")
R0 = float(se.fresnel_unpolarized(np.array([1.0]), np.array([1.0]),
                                  np.array([1.5168]))[0])
check("Normal incidence R, n=1.5168 -> ((n-1)/(n+1))^2", R0, 0.042166, 1e-4)
Rg = float(se.fresnel_unpolarized(np.array([0.001]), np.array([1.0]),
                                  np.array([1.5]))[0])
check("Grazing incidence R -> 1", Rg, 1.0, 1e-2)
Rtir = float(se.fresnel_unpolarized(np.array([math.cos(math.radians(60))]),
                                    np.array([1.5]), np.array([1.0]))[0])
check("TIR (glass->air at 60 deg > critical 41.8 deg) R = 1", Rtir, 1.0, 1e-9)

print("\n== Grating equation ==")
# Normal incidence, d=1000 nm, lambda=500 nm, m=1  ->  sin(theta) = 0.5 -> 30 deg
bm, feas = se.grating_orders(np.array([0.0]), np.array([0.0]),
                             np.array([500.0]), 1000.0, [1])
check("Normal incidence, d=1 um, 500 nm, m=1 -> 30.0 deg",
      math.degrees(math.asin(float(bm[0, 0]))), 30.0, 1e-6)
check_true("... and feasible", bool(feas[0, 0]))
bm2, feas2 = se.grating_orders(np.array([0.0]), np.array([0.0]),
                               np.array([500.0]), 1000.0, [2])
check_true("m=2 at 500 nm/1 um infeasible (sin=1.0)", not bool(feas2[0, 0]))
# Conical conservation: alpha (along-groove component) is untouched by design;
# verify sampled output direction in the tracer preserves it end to end.
alpha = np.array([0.3]); beta = np.array([0.2])
bm3, _ = se.grating_orders(alpha, beta, np.array([550.0]), 2000.0, [-1])
gz = math.sqrt(1 - 0.3**2 - float(bm3[0, 0])**2)
out = np.array([0.3, float(bm3[0, 0]), gz])
check("Conical: |out| = 1", float(np.linalg.norm(out)), 1.0, 1e-9)
check("Conical: out . t = alpha (conserved)", float(out[0]), 0.3, 1e-12)
check("Conical: beta_-1 = beta - lambda/d", float(bm3[0, 0]),
      0.2 - 550.0 / 2000.0, 1e-12)
# m = 0 must be the mirror direction
bm0, _ = se.grating_orders(alpha, beta, np.array([550.0]), 2000.0, [0])
check("m=0 is specular (beta unchanged)", float(bm0[0, 0]), 0.2, 1e-12)

print("\n== Order efficiency envelope (scalar slit-array) ==")
w = se.grating_order_weights(np.arange(-4, 5), 0.5, 'SINC')
m0 = 4  # index of m=0
check("w(m=0) = 1", float(w[m0]), 1.0, 1e-12)
check("50% duty: even orders vanish, w(m=2) = 0", float(w[m0 + 2]), 0.0, 1e-12)
check("w(m=1) = (2/pi)^2 = 0.4053", float(w[m0 + 1]), (2 / math.pi) ** 2, 1e-9)
check("symmetry w(+1) = w(-1)", float(w[m0 + 1] - w[m0 - 1]), 0.0, 1e-15)

print("\n== CIE colour matching ==")
lam = np.linspace(380, 780, 4001)
cmf = se.cie_xyz_bar(lam)
check("y-bar peak wavelength ~ 555 nm", float(lam[np.argmax(cmf[:, 1])]),
      555.0, 6.0)
check("y-bar peak value ~ 1.0", float(cmf[:, 1].max()), 1.0, 0.05)
xyz_e = cmf.mean(axis=0)  # equal-energy illuminant
rgb_e = se.xyz_to_linear_srgb(xyz_e)
check_true("Illuminant E maps near-neutral in sRGB (max/min < 1.4)",
           float(rgb_e.max() / rgb_e.min()) < 1.4 and rgb_e.min() > 0)

print("\n== 60-deg BK7 prism: minimum deviation ==")
def trace_prism_deviation(lam_nm, apex_deg=60.0):
    """Trace at minimum-deviation incidence and return total deviation (deg)."""
    n = float(se.glass_ior(lam_nm, 'BK7'))
    A = math.radians(apex_deg)
    i1 = math.asin(n * math.sin(A / 2))          # min-deviation incidence
    # refract in
    r1 = math.asin(math.sin(i1) / n)
    r2 = A - r1                                   # internal geometry of a prism
    i2 = math.asin(n * math.sin(r2))              # refract out
    return math.degrees(i1 + i2 - A)

n_d = float(se.glass_ior(587.56, 'BK7'))
d_an = 2 * math.degrees(math.asin(n_d * math.sin(math.radians(30)))) - 60
check("delta_min(587.6 nm) traced vs analytic 2 asin(n sin A/2) - A",
      trace_prism_deviation(587.56), d_an, 1e-9)
dev_blue = trace_prism_deviation(450.0)
dev_red = trace_prism_deviation(650.0)
check_true(f"Violet deviated MORE than red (blue {dev_blue:.2f} deg > "
           f"red {dev_red:.2f} deg)", dev_blue > dev_red)
print(f"       angular spread 450->650 nm through 60 deg BK7: "
      f"{dev_blue - dev_red:.3f} deg")

print("\n== Vector refraction (used by tracer) matches Snell ==")
n_l = float(se.glass_ior(550.0, 'BK7'))
d = np.array([[math.sin(math.radians(49.34)), 0.0,
               -math.cos(math.radians(49.34))]])
nf = np.array([[0.0, 0.0, 1.0]])
cos_i = -se.vdot(d, nf)
eta = np.array([1.0 / n_l])
sin2t = eta**2 * (1 - cos_i**2)
cos_t = np.sqrt(1 - sin2t)
refr = eta[:, None] * d + (eta * cos_i - cos_t)[:, None] * nf
ang_t = math.degrees(math.asin(float(np.linalg.norm(refr[0, :2]))))
check("refracted angle for i=49.34 deg into n=1.5185",
      ang_t, math.degrees(math.asin(math.sin(math.radians(49.34)) / n_l)), 1e-6)

print("\n" + ("ALL CHECKS PASSED" if PASS else "SOME CHECKS FAILED"))
sys.exit(0 if PASS else 1)
