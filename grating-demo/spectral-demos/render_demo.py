"""Shared spectral multi-pass driver. Usage:
   blender -b -P render_demo.py -- <scene_module> <out_prefix> <bands> <samples> <rx> <ry>"""
import bpy, sys, os, json, importlib.util
argv = sys.argv[sys.argv.index("--")+1:]
mod_path, out_prefix, bands, samples, rx, ry = argv[0], argv[1], int(argv[2]), int(argv[3]), int(argv[4]), int(argv[5])
HERE = os.path.dirname(os.path.abspath(__file__))

spec = importlib.util.spec_from_file_location("scene", os.path.join(HERE, mod_path))
scene = importlib.util.module_from_spec(spec); spec.loader.exec_module(scene)

LMIN, LMAX = 400.0, 700.0
waves = [LMIN + (LMAX-LMIN)*(i+0.5)/bands for i in range(bands)]
outdir = os.path.join(HERE, out_prefix + "_passes")
os.makedirs(outdir, exist_ok=True)
for i, wl in enumerate(waves):
    scene.build(wl, samples, rx, ry)
    bpy.context.scene.render.filepath = os.path.join(outdir, f"p{i:02d}.exr")
    bpy.ops.render.render(write_still=True)
    print(f"PASS {i+1}/{bands} {wl:.0f}nm done", flush=True)
json.dump(waves, open(os.path.join(outdir,"waves.json"),"w"))
print("ALL PASSES DONE", out_prefix)
