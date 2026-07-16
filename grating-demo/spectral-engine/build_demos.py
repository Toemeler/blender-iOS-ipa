"""Build + render the three spectral demo scenes headlessly.

Usage:  blender -b -noaudio --factory-startup --python build_demos.py [-- quick]
Writes: blends/{grating,cd,prism}_spectral.blend
        renders/{grating,cd,prism}_spectral.png
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import mathutils  # noqa: E402

import spectral_engine as se  # noqa: E402

try:
    se.register()
except Exception as e:  # already registered
    print("register:", e)

QUICK = "quick" in sys.argv
ONLY = next((a for a in sys.argv if a in ("grating", "cd", "prism")), None)
os.makedirs(os.path.join(HERE, "blends"), exist_ok=True)
os.makedirs(os.path.join(HERE, "renders"), exist_ok=True)


# ---------------------------------------------------------------- helpers
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'SPECTRAL_WAVE'
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    sc.render.image_settings.file_format = 'PNG'
    sc.render.resolution_percentage = 100
    return sc


def add_mesh(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def add_plane(name, sx, sy, z=0.0):
    v = [(-sx / 2, -sy / 2, z), (sx / 2, -sy / 2, z),
         (sx / 2, sy / 2, z), (-sx / 2, sy / 2, z)]
    return add_mesh(name, v, [(0, 1, 2), (0, 2, 3)])


def add_disc(name, r, nseg=96):
    verts = [(0.0, 0.0, 0.0)]
    for i in range(nseg):
        a = 2 * math.pi * i / nseg
        verts.append((r * math.cos(a), r * math.sin(a), 0.0))
    faces = [(0, 1 + i, 1 + (i + 1) % nseg) for i in range(nseg)]
    return add_mesh(name, verts, faces)


def add_area_light(name, loc, aim_dir, size_x, size_y, power):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.shape = 'RECTANGLE'
    ld.size = size_x
    ld.size_y = size_y
    ld.energy = power
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    d = mathutils.Vector(aim_dir).normalized()
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.collection.objects.link(ob)
    return ob


def add_camera(loc, aim_dir, lens):
    cd = bpy.data.cameras.new("Camera")
    cd.lens = lens
    ob = bpy.data.objects.new("Camera", cd)
    ob.location = loc
    d = mathutils.Vector(aim_dir).normalized()
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.collection.objects.link(ob)
    bpy.context.scene.camera = ob
    return ob


def probe_exposure(target=0.45):
    """Low-res direct render; set exposure so p70 of LIT pixels = target.
    Specular glare will clip to white -- physically it IS far brighter."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    sd = se._gather_scene(dg, lambda t, m: print("[probe]", t, m))
    cam_ob = bpy.context.scene.camera.evaluated_get(dg)
    cd = cam_ob.data
    cam = se.Camera(cam_ob.matrix_world, cd.lens, cd.sensor_width,
                    cd.sensor_height, cd.sensor_fit, cd.shift_x, cd.shift_y)
    img = se.render_spectral(sd, cam, 128, 96, spp=12,
                             max_bounce=bpy.context.scene.spectral.max_bounces,
                             seed=1)
    lum = 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]
    pos = lum[lum > 1e-9]
    if len(pos) == 0:
        print("[probe] WARNING: probe image is fully black!")
        bpy.context.scene.spectral.exposure = 1.0
        return 1.0
    p = float(np.percentile(pos, 70.0))
    exp = float(np.clip(target / max(p, 1e-12), 1e-6, 1e7))
    print(f"[probe] lit fraction {len(pos)/lum.size:.2%}, p70(lit)={p:.4g} "
          f"-> exposure={exp:.4g}")
    bpy.context.scene.spectral.exposure = exp
    return exp


def finish(name, w, h, spp):
    sc = bpy.context.scene
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.spectral.samples = 16 if QUICK else spp
    blend = os.path.join(HERE, "blends", f"{name}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    sc.render.filepath = os.path.join(HERE, "renders", f"{name}.png")
    import time
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"[done] {name}: {time.time()-t0:.1f}s -> {sc.render.filepath}")


# ---------------------------------------------------------------- 1. grating
def build_grating():
    sc = reset()
    plate = add_plane("Grating", 2.0, 1.2)
    st = plate.spectral
    st.surf_type = 'GRATING'
    st.pitch_nm = 2000.0
    st.duty = 0.5
    st.weighting = 'SINC'
    st.reflectivity = 0.9
    st.roughness = 0.01
    st.radial = False
    st.groove_axis = 'Y'   # grooves along Y -> dispersion along X

    lpos = (0.9, 0.0, 1.4)
    add_area_light("Light", lpos, (0.2 - lpos[0], 0, -lpos[2]), 0.15, 0.15, 300)
    cpos = (-1.6, 0.0, 1.5)
    add_camera(cpos, (0.35 - cpos[0], 0, -cpos[2]), 35)
    sc.spectral.max_bounces = 4

    # analytic prediction: which (m, lambda) lights up each x on the plate
    print("[predict] grating rainbow bands (order m, wavelength at plate x):")
    n = np.array([0.0, 0.0, 1.0])
    t = np.array([0.0, 1.0, 0.0])
    b = np.cross(n, t)
    for x in np.arange(-0.2, 1.01, 0.1):
        p = np.array([x, 0.0, 0.0])
        din = p - np.array(cpos); din /= np.linalg.norm(din)
        dout = np.array(lpos) - p; dout /= np.linalg.norm(dout)
        bi, bo = float(din @ b), float(dout @ b)
        hits = []
        for m in (-3, -2, -1, 1, 2, 3):
            lam = (bo - bi) / m * 2000.0
            if 380 <= lam <= 780:
                hits.append(f"m={m:+d}: {lam:.0f} nm")
        if hits:
            print(f"[predict]   x={x:+.2f}  " + ", ".join(hits))
    probe_exposure()
    finish("grating_spectral", 640, 400, 160)


# ---------------------------------------------------------------- 2. CD
def build_cd():
    sc = reset()
    disc = add_disc("CD", 0.6, nseg=64)
    disc.rotation_euler = (math.radians(14), 0, 0)
    st = disc.spectral
    st.surf_type = 'GRATING'
    st.pitch_nm = 1600.0        # real CD track pitch: 1.6 um
    st.duty = 0.5
    st.weighting = 'SINC'
    st.reflectivity = 0.9
    st.roughness = 0.008
    st.radial = True            # concentric grooves about origin / local Z

    add_camera((0.0, -2.0, 1.6), (0.0, 2.0, -1.55), 50)
    sc.spectral.max_bounces = 4

    # --- place the light by SOLVING the grating equation: pick the disc point
    # q (r = 0.30, local +Y), demand that order m = +/-1 at 550 nm leaving q
    # (as seen from the camera) passes through the light. Uses the exact same
    # conical frame construction as the tracer.
    rot = np.array(disc.rotation_euler.to_matrix())
    q = rot @ np.array([0.0, 0.30, 0.0])
    z = rot @ np.array([0.0, 0.0, 1.0])
    cpos = np.array([0.0, -2.0, 1.6])
    d_in = q - cpos
    d_in /= np.linalg.norm(d_in)
    n = z if d_in @ z < 0 else -z
    r = q - (q @ z) * z
    t = np.cross(z, r); t /= np.linalg.norm(t)
    b = np.cross(n, t)
    alpha, beta = float(d_in @ t), float(d_in @ b)
    out = None
    for m in (+1, -1):
        beta_m = beta + m * 550.0 / 1600.0
        if alpha ** 2 + beta_m ** 2 < 1.0:
            cand = (alpha * t + beta_m * b
                    + math.sqrt(1 - alpha ** 2 - beta_m ** 2) * n)
            if cand[2] > 0.15 and (out is None or cand[2] > out[2]):
                out = cand
                print(f"[predict] CD anchor: m={m:+d} @ 550 nm from disc point "
                      f"({q[0]:.2f},{q[1]:.2f},{q[2]:.2f}) exits along "
                      f"({cand[0]:.2f},{cand[1]:.2f},{cand[2]:.2f})")
    assert out is not None, "no feasible CD order found for anchor point"
    lpos = q + 2.0 * out
    add_area_light("Light", tuple(lpos), tuple(-out), 0.08, 0.08, 250)
    print(f"[predict] CD light placed at ({lpos[0]:.2f},{lpos[1]:.2f},"
          f"{lpos[2]:.2f})")
    print("[predict] CD first-order cone half-angles (normal incidence):")
    for lam in (450, 550, 650):
        print(f"[predict]   {lam} nm: m=1 at "
              f"{math.degrees(math.asin(lam/1600)):.1f} deg, m=3 at "
              + (f"{math.degrees(math.asin(3*lam/1600)):.1f} deg"
                 if 3 * lam / 1600 < 1 else "infeasible"))
    probe_exposure()
    finish("cd_spectral", 560, 420, 144)


# ---------------------------------------------------------------- 3. prism
def build_prism():
    sc = reset()
    # equilateral 60-deg prism, apex edge vertical (along Z), side 0.5
    L = np.array([-0.25, 0.0]); R = np.array([0.25, 0.0])
    A = np.array([0.0, 0.25 * math.sqrt(3.0)])
    z0, z1 = -0.35, 0.35
    verts = [(L[0], L[1], z0), (R[0], R[1], z0), (A[0], A[1], z0),
             (L[0], L[1], z1), (R[0], R[1], z1), (A[0], A[1], z1)]
    faces = [(0, 2, 1), (3, 4, 5),            # caps (outward -Z, +Z)
             (0, 1, 4), (0, 4, 3),            # base y=0, outward -Y
             (0, 3, 5), (0, 5, 2),            # left face
             (1, 2, 5), (1, 5, 4)]            # right face
    prism = add_mesh("Prism", verts, faces)
    prism.spectral.surf_type = 'GLASS'
    prism.spectral.glass = 'BK7'

    floor = add_plane("Floor", 10, 10, z=-0.36)
    floor.spectral.surf_type = 'DIFFUSE'
    floor.spectral.albedo = 0.25
    back = add_mesh("Backdrop",
                    [(-3.2, -2.5, -1.3), (-3.2, 2.5, -1.3),
                     (-3.2, 2.5, 1.3), (-3.2, -2.5, 1.3)],
                    [(0, 1, 2), (0, 2, 3)])
    back.spectral.surf_type = 'DIFFUSE'
    back.spectral.albedo = 0.03

    # exact minimum-deviation geometry at 550 nm, computed by Snell
    n550 = float(se.glass_ior(550.0, 'BK7'))
    nL = np.array([-math.sqrt(3) / 2, 0.5])      # outward normal, left face
    nR = np.array([math.sqrt(3) / 2, 0.5])       # outward normal, right face
    i1 = math.asin(n550 * math.sin(math.radians(30.0)))
    tL = np.array([0.5, math.sqrt(3) / 2])       # in-plane tangent (up-slope)
    d_in = math.cos(i1) * (-nL) + math.sin(i1) * tL       # into left face
    # refract in (2D Snell, vector form)
    eta = 1.0 / n550
    ci = -(d_in @ nL)                                     # cos incidence
    ct = math.sqrt(1 - eta * eta * (1 - ci * ci))
    d_int = eta * d_in + (eta * ci - ct) * nL
    assert abs(d_int[1]) < 1e-9, f"internal ray not horizontal: {d_int}"
    E1 = 0.5 * (L + A)
    # propagate to right face:  x from E1 along +X until hitting segment R-A
    #   right face param: P = R + s (A - R);  y equal ->
    s = E1[1] / A[1]
    E2 = R + s * (A - R)
    ci2 = d_int @ nR
    st2 = n550 * math.sqrt(max(0.0, 1 - ci2 * ci2))
    c_out = math.sqrt(max(0.0, 1 - st2 * st2))
    d_out = n550 * d_int - (n550 * ci2 - c_out) * nR
    d_out /= np.linalg.norm(d_out)
    dev = math.degrees(math.acos(float(np.clip(d_in @ d_out, -1, 1))))
    print(f"[predict] prism chief ray 550 nm: deviation {dev:.2f} deg "
          f"(analytic min deviation "
          f"{2*math.degrees(math.asin(n550*0.5))-60:.2f} deg)")
    for lam in (400, 450, 550, 650, 700):
        nl = float(se.glass_ior(lam, 'BK7'))
        d = 2 * math.degrees(math.asin(nl * 0.5)) - 60
        print(f"[predict]   {lam} nm: n={nl:.5f}, min deviation {d:.2f} deg")

    slit_pos = np.array([*(E1 - 2.0 * d_in), 0.0])
    cam_pos = np.array([*(E2 + 1.8 * d_out), 0.0])
    add_area_light("Slit", tuple(slit_pos), (d_in[0], d_in[1], 0.0),
                   0.01, 0.5, 4000)
    add_camera(tuple(cam_pos), (-d_out[0], -d_out[1], 0.0), 85)
    sc.spectral.max_bounces = 8
    probe_exposure()
    finish("prism_spectral", 640, 420, 160)


if ONLY in (None, "grating"):
    build_grating()
if ONLY in (None, "cd"):
    build_cd()
if ONLY in (None, "prism"):
    build_prism()
print("DEMOS BUILT:", ONLY or "all")
