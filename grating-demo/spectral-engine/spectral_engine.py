"""Spectral Wave Optics render engine for Blender.

A wavelength-based (spectral) path tracer that registers as a render engine
selectable next to Cycles and EEVEE. Built for scientifically faithful
simulation of dispersive/diffractive optics:

  * Diffraction gratings (linear and radial/CD) -- exact conical grating
    equation, per-wavelength order enumeration via momentum conservation.
  * Prisms / glass -- Sellmeier dispersion (BK7, fused silica, custom
    Cauchy), Fresnel (unpolarized) reflection/transmission, TIR.
  * Colour -- CIE 1931 2-deg colour matching functions (Wyman/Sloan/Shirley
    2013 analytic fit), XYZ -> linear sRGB.

Exact:        order/refraction DIRECTIONS, dispersion n(lambda), Fresnel.
Approximate:  relative grating order EFFICIENCY uses the scalar lamellar
              (slit-array, Fraunhofer) envelope sinc^2(pi m w/d) -- or
              'uniform'; lights are spectrally flat (Illuminant E); diffuse
              surfaces are neutral grey (no RGB->spectral uplift guessing).

Pure Python + numpy. No compiled code, so it also runs on the iOS build.
"""

bl_info = {
    "name": "Spectral Wave Optics Renderer",
    "author": "blender-iOS-ipa project",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "Render Properties > Render Engine",
    "description": "Physically-based spectral renderer for gratings, CDs and prisms",
    "category": "Render",
}

import math

import numpy as np

try:
    import bpy
    HAVE_BPY = True
except ImportError:  # allows importing the physics core for unit tests
    HAVE_BPY = False

F = np.float32
WL_MIN, WL_MAX = 380.0, 780.0
WL_RANGE = WL_MAX - WL_MIN
EPS = 1e-4
INF = np.float32(1e30)

# ----------------------------------------------------------------------------
# Colour science
# ----------------------------------------------------------------------------

def _pw_gauss(lam, mu, s1, s2):
    """Piecewise Gaussian used by the CIE 1931 analytic fit."""
    s = np.where(lam < mu, s1, s2)
    t = (lam - mu) / s
    return np.exp(-0.5 * t * t)


def cie_xyz_bar(lam):
    """CIE 1931 2-deg colour matching functions x̄,ȳ,z̄ at wavelength(s) in nm.

    Multi-lobe Gaussian fit: Wyman, Sloan & Shirley, JCGT 2(2), 2013.
    Accurate to ~1% of peak, which is far below the noise floor of a
    Monte-Carlo render. Returns array shaped (..., 3)."""
    lam = np.asarray(lam, dtype=np.float64)
    x = (1.056 * _pw_gauss(lam, 599.8, 37.9, 31.0)
         + 0.362 * _pw_gauss(lam, 442.0, 16.0, 26.7)
         - 0.065 * _pw_gauss(lam, 501.1, 20.4, 26.2))
    y = (0.821 * _pw_gauss(lam, 568.8, 46.9, 40.5)
         + 0.286 * _pw_gauss(lam, 530.9, 16.3, 31.1))
    z = (1.217 * _pw_gauss(lam, 437.0, 11.8, 36.0)
         + 0.681 * _pw_gauss(lam, 459.0, 26.0, 13.8))
    return np.stack([x, y, z], axis=-1)


# linear sRGB (D65) <- XYZ
XYZ_TO_SRGB = np.array([[ 3.2406, -1.5372, -0.4986],
                        [-0.9689,  1.8758,  0.0415],
                        [ 0.0557, -0.2040,  1.0570]], dtype=np.float64)


def xyz_to_linear_srgb(xyz):
    return xyz @ XYZ_TO_SRGB.T


# ----------------------------------------------------------------------------
# Dispersion models
# ----------------------------------------------------------------------------

SELLMEIER = {
    # name: (B1, B2, B3, C1, C2, C3)  with lambda in micrometres, C in um^2
    "BK7": (1.03961212, 0.231792344, 1.01046945,
            0.00600069867, 0.0200179144, 103.560653),
    "FUSED_SILICA": (0.6961663, 0.4079426, 0.8974794,
                     0.0046791486, 0.0135120631, 97.9340025),
}


def glass_ior(lam_nm, preset="BK7", cauchy_a=1.52, cauchy_b=0.0042):
    """Refractive index at wavelength(s) in nm."""
    lam = np.asarray(lam_nm, dtype=np.float64)
    if preset == "CAUCHY":
        lum2 = (lam * 1e-3) ** 2
        return cauchy_a + cauchy_b / lum2
    b1, b2, b3, c1, c2, c3 = SELLMEIER[preset]
    l2 = (lam * 1e-3) ** 2
    n2 = 1.0 + b1 * l2 / (l2 - c1) + b2 * l2 / (l2 - c2) + b3 * l2 / (l2 - c3)
    return np.sqrt(n2)


def fresnel_unpolarized(cos_i, n1, n2):
    """Unpolarized Fresnel reflectance. cos_i >= 0. Returns R in [0,1] (1 on TIR)."""
    cos_i = np.clip(cos_i, 0.0, 1.0)
    eta = n1 / n2
    sin2_t = eta * eta * (1.0 - cos_i * cos_i)
    tir = sin2_t >= 1.0
    cos_t = np.sqrt(np.clip(1.0 - sin2_t, 0.0, 1.0))
    rs = (n1 * cos_i - n2 * cos_t) / (n1 * cos_i + n2 * cos_t + 1e-12)
    rp = (n1 * cos_t - n2 * cos_i) / (n1 * cos_t + n2 * cos_i + 1e-12)
    R = 0.5 * (rs * rs + rp * rp)
    return np.where(tir, 1.0, R)


# ----------------------------------------------------------------------------
# Grating physics: exact conical diffraction geometry
# ----------------------------------------------------------------------------

def grating_orders(alpha, beta, lam_nm, pitch_nm, m_values):
    """Direction cosines of diffracted orders for a reflective grating.

    Incoming direction d (unit, pointing INTO the surface) is decomposed in the
    local frame (t = groove tangent, b = n x t = dispersion direction, n).
    Momentum conservation along the surface:
        alpha_out = alpha              (component along grooves conserved)
        beta_m    = beta + m * lam/d   (grating equation, conical form)
    The outgoing normal component is + sqrt(1 - alpha^2 - beta_m^2)
    (reflection side). m = 0 reproduces the mirror direction exactly.

    Returns (beta_m [N,M], feasible [N,M])."""
    shift = np.asarray(m_values, dtype=np.float64)[None, :] * (
        np.asarray(lam_nm, dtype=np.float64)[:, None] / float(pitch_nm))
    beta_m = np.asarray(beta, dtype=np.float64)[:, None] + shift
    feas = (np.asarray(alpha, dtype=np.float64)[:, None] ** 2 + beta_m ** 2) < 1.0
    return beta_m, feas


def grating_order_weights(m_values, duty, mode="SINC"):
    """Relative order efficiencies (before feasibility masking + normalisation).

    'SINC': scalar Fraunhofer envelope of a lamellar (slit-array) grating,
    w_m = sinc^2(pi m w/d) with duty = w/d. Exact within scalar diffraction
    for an amplitude grating; real pit/blazed gratings redistribute energy
    between orders but NOT their directions. 'UNIFORM': equal weights."""
    m = np.asarray(m_values, dtype=np.float64)
    if mode == "UNIFORM":
        return np.ones_like(m)
    return np.sinc(m * duty) ** 2  # np.sinc(x) = sin(pi x)/(pi x)


# ----------------------------------------------------------------------------
# Small vector helpers (arrays of shape (N,3))
# ----------------------------------------------------------------------------

def vdot(a, b):
    return np.einsum('ij,ij->i', a, b)


def vnorm(a):
    n = np.sqrt(np.einsum('ij,ij->i', a, a))
    return a / np.maximum(n, 1e-20)[:, None]


def make_frame(n):
    """Arbitrary orthonormal tangent frame for normals n (N,3) -> (t, b)."""
    a = np.where(np.abs(n[:, 2:3]) < 0.9,
                 np.array([0.0, 0.0, 1.0])[None, :],
                 np.array([1.0, 0.0, 0.0])[None, :])
    t = vnorm(np.cross(a, n))
    b = np.cross(n, t)
    return t, b


# ----------------------------------------------------------------------------
# Scene description (plain data, no bpy)
# ----------------------------------------------------------------------------

class Surface:
    __slots__ = ("kind", "albedo", "reflectivity", "pitch_nm", "duty",
                 "weighting", "radial", "roughness", "glass", "cauchy_a",
                 "cauchy_b", "origin", "zaxis", "gaxis", "name")

    def __init__(self, kind="DIFFUSE", **kw):
        self.kind = kind
        self.albedo = kw.get("albedo", 0.5)
        self.reflectivity = kw.get("reflectivity", 0.9)
        self.pitch_nm = kw.get("pitch_nm", 2000.0)
        self.duty = kw.get("duty", 0.5)
        self.weighting = kw.get("weighting", "SINC")
        self.radial = kw.get("radial", False)
        self.roughness = kw.get("roughness", 0.01)
        self.glass = kw.get("glass", "BK7")
        self.cauchy_a = kw.get("cauchy_a", 1.52)
        self.cauchy_b = kw.get("cauchy_b", 0.0042)
        self.origin = np.asarray(kw.get("origin", (0, 0, 0)), dtype=np.float64)
        self.zaxis = np.asarray(kw.get("zaxis", (0, 0, 1)), dtype=np.float64)
        self.gaxis = np.asarray(kw.get("gaxis", (1, 0, 0)), dtype=np.float64)
        self.name = kw.get("name", "surface")


class SceneData:
    def __init__(self):
        self.v0 = np.zeros((0, 3), F)   # triangle origin vertex
        self.e1 = np.zeros((0, 3), F)
        self.e2 = np.zeros((0, 3), F)
        self.tri_surf = np.zeros(0, np.int32)
        self.surfaces = []
        # area lights (rectangles)
        self.l_corner = np.zeros((0, 3), F)
        self.l_e1 = np.zeros((0, 3), F)
        self.l_e2 = np.zeros((0, 3), F)
        self.l_normal = np.zeros((0, 3), F)   # emission direction
        self.l_radiance = np.zeros(0, F)      # spectral radiance W/(m^2 sr nm)
        self.l_area = np.zeros(0, F)

    def add_mesh(self, verts, tris, surface):
        sid = len(self.surfaces)
        self.surfaces.append(surface)
        v = np.asarray(verts, dtype=F)
        t = np.asarray(tris, dtype=np.int64)
        v0 = v[t[:, 0]]
        self.v0 = np.concatenate([self.v0, v0])
        self.e1 = np.concatenate([self.e1, v[t[:, 1]] - v0])
        self.e2 = np.concatenate([self.e2, v[t[:, 2]] - v0])
        self.tri_surf = np.concatenate(
            [self.tri_surf, np.full(len(t), sid, np.int32)])

    def add_area_light(self, corner, e1, e2, normal, power_w):
        self.l_corner = np.concatenate([self.l_corner, [np.asarray(corner, F)]])
        self.l_e1 = np.concatenate([self.l_e1, [np.asarray(e1, F)]])
        self.l_e2 = np.concatenate([self.l_e2, [np.asarray(e2, F)]])
        self.l_normal = np.concatenate([self.l_normal, [np.asarray(normal, F)]])
        area = float(np.linalg.norm(np.cross(e1, e2)))
        # Lambertian emitter, flat spectrum over [380,780] nm (Illuminant E):
        # L_lambda = P / (A * pi * range)
        rad = power_w / max(area * math.pi * WL_RANGE, 1e-12)
        self.l_radiance = np.concatenate([self.l_radiance, [F(rad)]])
        self.l_area = np.concatenate([self.l_area, [F(area)]])


# ----------------------------------------------------------------------------
# Intersection
# ----------------------------------------------------------------------------

def intersect_tris(scene, O, D, t_max=None):
    """Brute-force Moller-Trumbore, vectorised over rays, python-loop over tris.
    Returns (t, tri_index) with t=INF where no hit."""
    N = len(O)
    best_t = np.full(N, INF, F)
    best_i = np.full(N, -1, np.int32)
    if t_max is not None:
        best_t = np.minimum(best_t, t_max.astype(F))
    for i in range(len(scene.v0)):
        e1 = scene.e1[i]; e2 = scene.e2[i]; v0 = scene.v0[i]
        p = np.cross(D, e2[None, :])
        det = np.einsum('ij,j->i', p, e1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = O - v0[None, :]
        u = np.einsum('ij,ij->i', tv, p) * inv
        q = np.cross(tv, e1[None, :])
        v = np.einsum('ij,ij->i', D, q) * inv
        t = np.einsum('ij,j->i', q, e2) * inv
        hit = ok & (u >= -1e-7) & (v >= -1e-7) & (u + v <= 1.0 + 1e-7) \
                 & (t > EPS) & (t < best_t)
        best_t = np.where(hit, t.astype(F), best_t)
        best_i = np.where(hit, i, best_i)
    return best_t, best_i


def occluded(scene, O, D, dist):
    t, _ = intersect_tris(scene, O, D, t_max=dist * (1.0 - 1e-4))
    return t < dist * (1.0 - 1e-4)


def intersect_lights(scene, O, D):
    """Nearest rectangle-light hit. Returns (t, light_index)."""
    N = len(O)
    best_t = np.full(N, INF, F)
    best_i = np.full(N, -1, np.int32)
    for i in range(len(scene.l_corner)):
        nrm = scene.l_normal[i]
        denom = np.einsum('ij,j->i', D, nrm)
        ok = np.abs(denom) > 1e-9
        t = np.einsum('j,ij->i', nrm, scene.l_corner[i][None, :] - O) / \
            np.where(ok, denom, 1.0)
        p = O + D * t[:, None] - scene.l_corner[i][None, :]
        e1 = scene.l_e1[i]; e2 = scene.l_e2[i]
        u = np.einsum('ij,j->i', p, e1) / np.dot(e1, e1)
        v = np.einsum('ij,j->i', p, e2) / np.dot(e2, e2)
        hit = ok & (t > EPS) & (u >= 0) & (u <= 1) & (v >= 0) & (v <= 1) & (t < best_t)
        best_t = np.where(hit, t.astype(F), best_t)
        best_i = np.where(hit, i, best_i)
    return best_t, best_i


# ----------------------------------------------------------------------------
# The integrator (wavefront spectral path tracer)
# ----------------------------------------------------------------------------

def render_spectral(scene, cam, W, H, spp=64, max_bounce=8, seed=0,
                    m_min=-6, m_max=6, progress=None, want_break=None):
    """Returns linear-sRGB image (H, W, 3), float64, un-exposed."""
    rng = np.random.default_rng(seed)
    Npx = W * H
    acc_xyz = np.zeros((Npx, 3), np.float64)
    m_values = np.arange(m_min, m_max + 1)

    for s in range(spp):
        if want_break is not None and want_break():
            spp = max(s, 1)
            break
        O, D = cam.generate_rays(W, H, rng)
        lam = WL_MIN + WL_RANGE * ((s + rng.random(Npx)) / spp)  # stratified
        T = np.ones(Npx, np.float64)
        pix = np.arange(Npx)
        spec_prev = np.ones(Npx, bool)  # camera / specular chain -> may see emitter

        for bounce in range(max_bounce):
            if len(O) == 0:
                break
            t_geo, tri = intersect_tris(scene, O, D)
            t_l, li = intersect_lights(scene, O, D)

            # --- emitter hits (only from camera or a specular chain: diffuse
            #     vertices already counted the light via next-event estimation)
            hit_l = (t_l < t_geo) & (li >= 0)
            add = hit_l & spec_prev
            if np.any(add):
                # one-sided emission (Blender area lights emit along -Z local)
                facing = np.einsum('ij,ij->i', D[add],
                                   scene.l_normal[li[add]]) < 0.0
                idx = np.where(add)[0][facing]
                if len(idx):
                    Le = scene.l_radiance[li[idx]].astype(np.float64)
                    cmf = cie_xyz_bar(lam[idx])
                    acc_xyz[pix[idx]] += (T[idx] * Le)[:, None] * cmf * WL_RANGE

            alive = (~hit_l) & (tri >= 0)
            if not np.any(alive):
                break
            O = O[alive]; D = D[alive]; T = T[alive]; lam = lam[alive]
            pix = pix[alive]; tri = tri[alive]; t_geo = t_geo[alive]

            P = O + D * t_geo[:, None]
            n_geo = vnorm(np.cross(scene.e1[tri], scene.e2[tri]))
            sids = scene.tri_surf[tri]
            front = vdot(D, n_geo) < 0.0
            n = np.where(front[:, None], n_geo, -n_geo)  # facing the ray

            new_O = np.empty_like(O)
            new_D = np.empty_like(D)
            new_T = T.copy()
            spec_new = np.ones(len(O), bool)
            kill = np.zeros(len(O), bool)

            for sid in np.unique(sids):
                surf = scene.surfaces[sid]
                m = sids == sid
                if surf.kind == "DIFFUSE":
                    _shade_diffuse(scene, surf, m, P, n, D, T, lam, pix,
                                   acc_xyz, rng, new_O, new_D, new_T)
                    spec_new[m] = False
                elif surf.kind == "MIRROR":
                    d = D[m] - 2.0 * vdot(D[m], n[m])[:, None] * n[m]
                    new_D[m] = d
                    new_O[m] = P[m] + n[m] * EPS
                    new_T[m] = T[m] * surf.reflectivity
                elif surf.kind == "GRATING":
                    _shade_grating(surf, m, P, n, D, T, lam, m_values, rng,
                                   new_O, new_D, new_T, kill)
                elif surf.kind == "GLASS":
                    _shade_glass(surf, m, P, n_geo, D, lam, rng,
                                 new_O, new_D)
                else:
                    kill[m] = True

            # Russian roulette
            if bounce >= 3:
                pc = np.clip(new_T, 0.05, 0.95)
                kill |= rng.random(len(new_T)) >= pc
                new_T = new_T / pc
            keep = (~kill) & (new_T > 1e-7)
            O = new_O[keep]; D = vnorm(new_D[keep]); T = new_T[keep]
            lam = lam[keep]; pix = pix[keep]; spec_prev = spec_new[keep]

        if progress is not None:
            progress(s + 1, spp, acc_xyz)

    xyz = acc_xyz / spp
    rgb = xyz_to_linear_srgb(xyz)
    return np.clip(rgb, 0.0, None).reshape(H, W, 3)


def _shade_diffuse(scene, surf, m, P, n, D, T, lam, pix, acc_xyz, rng,
                   new_O, new_D, new_T):
    idx = np.where(m)[0]
    p = P[idx]; nn = n[idx]
    # --- next-event estimation to every rectangle light
    for i in range(len(scene.l_corner)):
        q = (scene.l_corner[i][None, :]
             + rng.random((len(idx), 1)) * scene.l_e1[i][None, :]
             + rng.random((len(idx), 1)) * scene.l_e2[i][None, :])
        wi = q - p
        d2 = np.einsum('ij,ij->i', wi, wi)
        dist = np.sqrt(d2)
        wi = wi / dist[:, None]
        cos_s = vdot(nn, wi)
        cos_l = -np.einsum('ij,j->i', wi, scene.l_normal[i])
        vis = (cos_s > 0) & (cos_l > 0)
        if not np.any(vis):
            continue
        sh = ~occluded(scene, p[vis] + nn[vis] * EPS, wi[vis], dist[vis])
        j = np.where(vis)[0][sh]
        if len(j) == 0:
            continue
        geo = cos_s[j] * cos_l[j] * scene.l_area[i] / d2[j]
        contrib = (T[idx[j]] * surf.albedo / math.pi
                   * scene.l_radiance[i] * geo)
        cmf = cie_xyz_bar(lam[idx[j]])
        acc_xyz[pix[idx[j]]] += contrib[:, None] * cmf * WL_RANGE
    # --- cosine-weighted bounce
    t, b = make_frame(nn)
    r1 = rng.random(len(idx)); r2 = rng.random(len(idx))
    r = np.sqrt(r1); phi = 2 * math.pi * r2
    d = (t * (r * np.cos(phi))[:, None] + b * (r * np.sin(phi))[:, None]
         + nn * np.sqrt(np.clip(1 - r1, 0, 1))[:, None])
    new_D[idx] = d
    new_O[idx] = p + nn * EPS
    new_T[idx] = T[idx] * surf.albedo


def _shade_grating(surf, m, P, n, D, T, lam, m_values, rng,
                   new_O, new_D, new_T, kill):
    idx = np.where(m)[0]
    p = P[idx]; nn = n[idx]; d = D[idx]
    # groove tangent
    if surf.radial:
        r = p - surf.origin[None, :]
        r = r - np.einsum('ij,j->i', r, surf.zaxis)[:, None] * surf.zaxis[None, :]
        tg = np.cross(np.broadcast_to(surf.zaxis, r.shape), r)
        bad = np.einsum('ij,ij->i', tg, tg) < 1e-16
        if np.any(bad):
            tf, _ = make_frame(nn[bad])
            tg[bad] = tf
        tg = vnorm(tg)
    else:
        g = np.broadcast_to(surf.gaxis, nn.shape)
        tg = g - vdot(g, nn)[:, None] * nn
        tg = vnorm(tg)
    tg = tg - vdot(tg, nn)[:, None] * nn
    tg = vnorm(tg)
    bg = vnorm(np.cross(nn, tg))

    alpha = vdot(d, tg)
    beta = vdot(d, bg)
    beta_m, feas = grating_orders(alpha, beta, lam[idx], surf.pitch_nm, m_values)
    w = grating_order_weights(m_values, surf.duty, surf.weighting)[None, :] * feas
    wsum = w.sum(axis=1)
    dead = wsum <= 1e-12
    kill[idx[dead]] = True
    ok = ~dead
    if not np.any(ok):
        return
    cdf = np.cumsum(w[ok], axis=1)
    u = rng.random(ok.sum()) * cdf[:, -1]
    pick = (u[:, None] > cdf).sum(axis=1)
    bm = beta_m[ok, pick]
    a = alpha[ok]
    gz = np.sqrt(np.clip(1.0 - a * a - bm * bm, 0.0, 1.0))
    out = (tg[ok] * a[:, None] + bg[ok] * bm[:, None] + nn[ok] * gz[:, None])
    # groove irregularity: small gaussian jitter (keeps energy, physical
    # analogue of pitch/orientation variance across the illuminated spot)
    if surf.roughness > 0:
        j = rng.normal(0.0, surf.roughness, out.shape)
        out = out + j
        out = vnorm(out)
        below = vdot(out, nn[ok]) <= 1e-4
        out[below] = (out - 2 * vdot(out, nn[ok])[:, None] * nn[ok])[below]
    ii = idx[ok]
    new_D[ii] = out
    new_O[ii] = p[ok] + nn[ok] * EPS
    # pdf = w_pick/sum(w); estimator value = R * w_pick/sum(w)  =>  ratio = R
    new_T[ii] = T[ii] * surf.reflectivity


def _shade_glass(surf, m, P, n_geo, D, lam, rng, new_O, new_D):
    idx = np.where(m)[0]
    d = D[idx]; ng = n_geo[idx]
    entering = vdot(d, ng) < 0.0
    nf = np.where(entering[:, None], ng, -ng)
    n_glass = glass_ior(lam[idx], surf.glass, surf.cauchy_a, surf.cauchy_b)
    n1 = np.where(entering, 1.0, n_glass)
    n2 = np.where(entering, n_glass, 1.0)
    cos_i = -vdot(d, nf)
    R = fresnel_unpolarized(cos_i, n1, n2)
    refl = rng.random(len(idx)) < R
    eta = n1 / n2
    sin2t = eta * eta * np.clip(1.0 - cos_i * cos_i, 0.0, 1.0)
    cos_t = np.sqrt(np.clip(1.0 - sin2t, 0.0, 1.0))
    d_refl = d + 2.0 * cos_i[:, None] * nf
    d_refr = (eta[:, None] * d + (eta * cos_i - cos_t)[:, None] * nf)
    out = np.where(refl[:, None], d_refl, d_refr)
    off = np.where(refl[:, None], nf * EPS, -nf * EPS)
    new_D[idx] = out
    new_O[idx] = P[idx] + off
    # throughput unchanged: MC selection with prob R / (1-R) is unbiased


# ----------------------------------------------------------------------------
# Camera
# ----------------------------------------------------------------------------

class Camera:
    def __init__(self, matrix, lens_mm, sensor_w, sensor_h, sensor_fit,
                 shift_x=0.0, shift_y=0.0):
        Mw = np.asarray(matrix, dtype=np.float64)
        self.origin = Mw[:3, 3].copy()
        self.right = Mw[:3, 0].copy()
        self.up = Mw[:3, 1].copy()
        self.fwd = -Mw[:3, 2].copy()
        self.lens = lens_mm
        self.sw = sensor_w
        self.sh = sensor_h
        self.fit = sensor_fit
        self.shift_x = shift_x
        self.shift_y = shift_y

    def tans(self, W, H):
        base = self.sw / (2.0 * self.lens)
        fit = self.fit
        if fit == 'AUTO':
            fit = 'HORIZONTAL' if W >= H else 'VERTICAL'
        if fit == 'HORIZONTAL':
            tx = base
            ty = base * H / W
        else:
            ty = self.sh / (2.0 * self.lens) if self.fit == 'VERTICAL' else base
            tx = ty * W / H
        return tx, ty

    def generate_rays(self, W, H, rng):
        tx, ty = self.tans(W, H)
        px, py = np.meshgrid(np.arange(W), np.arange(H))
        px = px.ravel().astype(np.float64) + rng.random(W * H)
        py = py.ravel().astype(np.float64) + rng.random(W * H)
        u = (px / W * 2.0 - 1.0) + 2.0 * self.shift_x
        v = (1.0 - py / H * 2.0) + 2.0 * self.shift_y
        d = (self.right[None, :] * (u * tx)[:, None]
             + self.up[None, :] * (v * ty)[:, None]
             + self.fwd[None, :])
        O = np.broadcast_to(self.origin, d.shape).copy()
        return O.astype(F), vnorm(d).astype(F)


# ============================================================================
# Blender integration
# ============================================================================

if HAVE_BPY:

    SURF_ITEMS = [
        ('DIFFUSE', "Diffuse (neutral)", "Lambertian, neutral grey albedo"),
        ('MIRROR', "Mirror", "Perfect specular reflector"),
        ('GRATING', "Diffraction grating", "Reflective grating (linear or radial/CD)"),
        ('GLASS', "Dispersive glass", "Sellmeier/Cauchy dispersive dielectric (prism)"),
    ]

    class SpectralObjectSettings(bpy.types.PropertyGroup):
        surf_type: bpy.props.EnumProperty(name="Surface", items=SURF_ITEMS,
                                          default='DIFFUSE')
        albedo: bpy.props.FloatProperty(name="Albedo", default=0.5,
                                        min=0.0, max=1.0)
        reflectivity: bpy.props.FloatProperty(name="Reflectivity", default=0.9,
                                              min=0.0, max=1.0)
        pitch_nm: bpy.props.FloatProperty(name="Groove pitch (nm)",
                                          default=2000.0, min=100.0,
                                          max=100000.0)
        duty: bpy.props.FloatProperty(name="Duty cycle w/d", default=0.5,
                                      min=0.05, max=0.95)
        weighting: bpy.props.EnumProperty(
            name="Order efficiency",
            items=[('SINC', "Scalar slit-array (sinc²)",
                    "Fraunhofer envelope of a lamellar amplitude grating"),
                   ('UNIFORM', "Uniform",
                    "Equal energy in every feasible order")],
            default='SINC')
        radial: bpy.props.BoolProperty(
            name="Radial grooves (CD)", default=False,
            description="Concentric grooves around the object origin/Z axis")
        groove_axis: bpy.props.EnumProperty(
            name="Groove axis", items=[('X', "Local X", ""), ('Y', "Local Y", "")],
            default='Y')
        roughness: bpy.props.FloatProperty(name="Groove irregularity",
                                           default=0.01, min=0.0, max=0.2)
        glass: bpy.props.EnumProperty(
            name="Glass", items=[('BK7', "N-BK7 (Sellmeier)", ""),
                                 ('FUSED_SILICA', "Fused silica (Sellmeier)", ""),
                                 ('CAUCHY', "Custom (Cauchy)", "")],
            default='BK7')
        cauchy_a: bpy.props.FloatProperty(name="Cauchy A", default=1.52)
        cauchy_b: bpy.props.FloatProperty(name="Cauchy B (µm²)", default=0.0042)

    class SpectralSceneSettings(bpy.types.PropertyGroup):
        samples: bpy.props.IntProperty(name="Samples", default=128, min=1,
                                       max=16384)
        max_bounces: bpy.props.IntProperty(name="Max bounces", default=8,
                                           min=1, max=32)
        exposure: bpy.props.FloatProperty(name="Exposure", default=1.0,
                                          min=0.0, soft_max=1e6)
        seed: bpy.props.IntProperty(name="Seed", default=0)

    def _gather_scene(depsgraph, report):
        sd = SceneData()
        warned = False
        for inst in depsgraph.object_instances:
            ob = inst.object
            if ob.type == 'MESH':
                key = ob.original if hasattr(ob, "original") else ob
                st = getattr(key, "spectral", None)
                mw = np.array(inst.matrix_world, dtype=np.float64)
                R3 = mw[:3, :3]
                me = ob.to_mesh()
                try:
                    me.calc_loop_triangles()
                    nv = len(me.vertices)
                    verts32 = np.empty(nv * 3, np.float32)
                    me.vertices.foreach_get("co", verts32)
                    verts = verts32.astype(np.float64).reshape(nv, 3) @ R3.T \
                        + mw[:3, 3]
                    nt = len(me.loop_triangles)
                    if nt == 0:
                        continue
                    tris32 = np.empty(nt * 3, np.int32)
                    me.loop_triangles.foreach_get("vertices", tris32)
                    tris = tris32.astype(np.int64).reshape(nt, 3)
                finally:
                    ob.to_mesh_clear()
                if nt > 5000 and not warned:
                    report({'WARNING'},
                           "Scene has >5000 triangles; brute-force tracer "
                           "will be slow")
                    warned = True
                kw = {}
                kind = 'DIFFUSE'
                if st is not None:
                    kind = st.surf_type
                    gax_local = (1.0, 0.0, 0.0) if st.groove_axis == 'X' \
                        else (0.0, 1.0, 0.0)
                    gaxis = R3 @ np.asarray(gax_local)
                    kw = dict(albedo=st.albedo, reflectivity=st.reflectivity,
                              pitch_nm=st.pitch_nm, duty=st.duty,
                              weighting=st.weighting, radial=st.radial,
                              roughness=st.roughness, glass=st.glass,
                              cauchy_a=st.cauchy_a, cauchy_b=st.cauchy_b,
                              origin=mw[:3, 3],
                              zaxis=R3 @ np.array([0.0, 0.0, 1.0]),
                              gaxis=gaxis, name=key.name)
                    kw["zaxis"] = kw["zaxis"] / np.linalg.norm(kw["zaxis"])
                    kw["gaxis"] = gaxis / max(np.linalg.norm(gaxis), 1e-12)
                sd.add_mesh(verts, tris, Surface(kind, **kw))
            elif ob.type == 'LIGHT' and ob.data.type == 'AREA':
                mw = np.array(inst.matrix_world, dtype=np.float64)
                sx = ob.data.size
                sy = ob.data.size_y if ob.data.shape in {'RECTANGLE', 'ELLIPSE'} \
                    else ob.data.size
                ex = mw[:3, 0] * sx
                ey = mw[:3, 1] * sy
                corner = mw[:3, 3] - 0.5 * ex - 0.5 * ey
                nrm = -mw[:3, 2]
                nrm = nrm / max(np.linalg.norm(nrm), 1e-12)
                sd.add_area_light(corner, ex, ey, nrm, ob.data.energy)
            elif ob.type == 'LIGHT':
                report({'WARNING'},
                       f"Light '{ob.name}': only AREA lights are supported; "
                       "ignored")
        return sd

    class SpectralRenderEngine(bpy.types.RenderEngine):
        bl_idname = "SPECTRAL_WAVE"
        bl_label = "Spectral Wave Optics"
        bl_use_preview = False
        bl_use_eevee_viewport = True   # viewport keeps using EEVEE for editing

        def render(self, depsgraph):
            scene = depsgraph.scene
            st = scene.spectral
            scale = scene.render.resolution_percentage / 100.0
            W = max(1, int(scene.render.resolution_x * scale))
            H = max(1, int(scene.render.resolution_y * scale))

            cam_ob = scene.camera
            if cam_ob is None:
                self.report({'ERROR'}, "No camera in scene")
                return
            cam_eval = cam_ob.evaluated_get(depsgraph)
            cd = cam_eval.data
            cam = Camera(cam_eval.matrix_world, cd.lens, cd.sensor_width,
                         cd.sensor_height, cd.sensor_fit,
                         cd.shift_x, cd.shift_y)

            sd = _gather_scene(depsgraph, self.report)
            if len(sd.l_corner) == 0:
                self.report({'WARNING'}, "No AREA light found; image will be black")

            self._print_grating_report(sd, cam)

            spp = max(1, st.samples)
            exposure = st.exposure

            def progress(done, total, acc):
                self.update_progress(done / total)
                if done % max(1, total // 8) == 0 and done != total:
                    self._write(acc / done, W, H, exposure)

            img = render_spectral(sd, cam, W, H, spp=spp,
                                  max_bounce=st.max_bounces, seed=st.seed,
                                  progress=progress,
                                  want_break=self.test_break)
            self._write_rgb(img, W, H, exposure)

        # -- result writing helpers
        def _write(self, acc_xyz, W, H, exposure):
            rgb = np.clip(xyz_to_linear_srgb(acc_xyz), 0.0, None)
            self._write_rgb(rgb.reshape(H, W, 3), W, H, exposure)

        def _write_rgb(self, img, W, H, exposure):
            rgba = np.empty((H, W, 4), np.float32)
            rgba[..., :3] = img * exposure
            rgba[..., 3] = 1.0
            rgba = rgba[::-1].reshape(-1, 4)
            result = self.begin_result(0, 0, W, H)
            layer = result.layers[0]
            try:
                p = layer.passes["Combined"]
            except (KeyError, TypeError):
                p = layer.passes[0]
            try:
                p.rect.foreach_set(rgba.ravel())
            except (AttributeError, TypeError):
                p.rect = rgba.tolist()
            self.end_result(result)

        def _print_grating_report(self, sd, cam):
            for s in sd.surfaces:
                if s.kind != "GRATING":
                    continue
                print(f"[spectral] grating '{s.name}': pitch={s.pitch_nm:.0f} nm,"
                      f" duty={s.duty:.2f}, weighting={s.weighting},"
                      f" radial={s.radial}")
                print("[spectral]   normal-incidence order angles "
                      "(sin th_m = m lambda/d):")
                for lam, nm in ((450, "blue"), (550, "green"), (650, "red")):
                    angs = []
                    mm = 1
                    while mm * lam / s.pitch_nm < 1.0:
                        angs.append(f"m={mm}: "
                                    f"{math.degrees(math.asin(mm*lam/s.pitch_nm)):.1f}°")
                        mm += 1
                    print(f"[spectral]     {lam} nm ({nm}): " + ", ".join(angs))

    # ------------------------------------------------------------------ UI
    class RENDER_PT_spectral(bpy.types.Panel):
        bl_idname = "RENDER_PT_spectral"
        bl_label = "Spectral Wave Optics"
        bl_space_type = 'PROPERTIES'
        bl_region_type = 'WINDOW'
        bl_context = "render"
        COMPAT_ENGINES = {'SPECTRAL_WAVE'}

        @classmethod
        def poll(cls, context):
            return context.engine == 'SPECTRAL_WAVE'

        def draw(self, context):
            st = context.scene.spectral
            col = self.layout.column()
            col.prop(st, "samples")
            col.prop(st, "max_bounces")
            col.prop(st, "exposure")
            col.prop(st, "seed")
            col.separator()
            col.label(text="Spectral 380–780 nm, CIE 1931, Illuminant-E lights")
            col.label(text="Tag meshes in Object Properties > Spectral Surface")

    class OBJECT_PT_spectral(bpy.types.Panel):
        bl_idname = "OBJECT_PT_spectral"
        bl_label = "Spectral Surface"
        bl_space_type = 'PROPERTIES'
        bl_region_type = 'WINDOW'
        bl_context = "object"

        @classmethod
        def poll(cls, context):
            return (context.engine == 'SPECTRAL_WAVE'
                    and context.object is not None
                    and context.object.type == 'MESH')

        def draw(self, context):
            st = context.object.spectral
            col = self.layout.column()
            col.prop(st, "surf_type")
            if st.surf_type == 'DIFFUSE':
                col.prop(st, "albedo")
            elif st.surf_type == 'MIRROR':
                col.prop(st, "reflectivity")
            elif st.surf_type == 'GRATING':
                col.prop(st, "pitch_nm")
                col.prop(st, "duty")
                col.prop(st, "weighting")
                col.prop(st, "reflectivity")
                col.prop(st, "roughness")
                col.prop(st, "radial")
                if not st.radial:
                    col.prop(st, "groove_axis")
            elif st.surf_type == 'GLASS':
                col.prop(st, "glass")
                if st.glass == 'CAUCHY':
                    col.prop(st, "cauchy_a")
                    col.prop(st, "cauchy_b")

    _classes = (SpectralObjectSettings, SpectralSceneSettings,
                SpectralRenderEngine, RENDER_PT_spectral, OBJECT_PT_spectral)

    def register():
        for c in _classes:
            bpy.utils.register_class(c)
        bpy.types.Scene.spectral = bpy.props.PointerProperty(
            type=SpectralSceneSettings)
        bpy.types.Object.spectral = bpy.props.PointerProperty(
            type=SpectralObjectSettings)

    def unregister():
        del bpy.types.Object.spectral
        del bpy.types.Scene.spectral
        for c in reversed(_classes):
            bpy.utils.unregister_class(c)

    if __name__ == "__main__":
        register()
