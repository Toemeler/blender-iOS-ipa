"""True spectral rendering with stock Cycles: one monochrome render per
wavelength band, integrated against CIE 1931 CMFs -> XYZ -> sRGB.
Usage: blender -b -P spectral_render.py [-- bands samples resx resy]"""
import bpy, os, sys, math, mathutils, json

HERE = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
BANDS = int(argv[0]) if len(argv) > 0 else 16
SAMPLES = int(argv[1]) if len(argv) > 1 else 96
RX = int(argv[2]) if len(argv) > 2 else 640
RY = int(argv[3]) if len(argv) > 3 else 480
LMIN, LMAX = 390.0, 730.0

def build(wavelength):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.render.engine = 'CYCLES'; scn.cycles.device = 'CPU'
    scn.cycles.shading_system = True
    scn.cycles.samples = SAMPLES
    scn.cycles.use_denoising = False
    scn.render.resolution_x, scn.render.resolution_y = RX, RY
    scn.render.image_settings.file_format = 'OPEN_EXR'
    scn.render.image_settings.color_depth = '32'
    scn.view_settings.view_transform = 'Raw'   # linear radiometric output

    bpy.ops.mesh.primitive_plane_add(size=6)
    plate = bpy.context.object
    bpy.ops.object.light_add(type='AREA', location=(0, 3.0, 3.0))
    li = bpy.context.object
    li.data.size = 0.08; li.data.energy = 9000
    li.rotation_euler = mathutils.Vector((0,3,3)).to_track_quat('Z','Y').to_euler()
    bpy.ops.object.camera_add(location=(0, -3.0, 3.0))
    cam = bpy.context.object
    cam.rotation_euler = (mathutils.Vector((0,-3,3)) - mathutils.Vector((0,0.8,0))).to_track_quat('Z','Y').to_euler()
    cam.data.lens = 32
    scn.camera = cam
    w = bpy.data.worlds.new("W"); scn.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0,0,0,1)

    mat = bpy.data.materials.new("mono"); mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    sc = nt.nodes.new("ShaderNodeScript"); sc.mode='EXTERNAL'
    sc.filepath = os.path.join(HERE, "diffraction_mono.osl"); sc.update()
    assert sc.outputs, "mono OSL failed"
    sc.inputs["Wavelength"].default_value = wavelength
    sc.inputs["Distance"].default_value = 1000.0
    nt.links.new(sc.outputs["BRDF"], out.inputs["Surface"])
    plate.data.materials.append(mat)
    return scn

waves = [LMIN + (LMAX-LMIN)*(i+0.5)/BANDS for i in range(BANDS)]
os.makedirs("/home/claude/grating/spectral_passes", exist_ok=True)
for i, wl in enumerate(waves):
    scn = build(wl)
    scn.render.filepath = f"/home/claude/grating/spectral_passes/pass_{i:02d}.exr"
    bpy.ops.render.render(write_still=True)
    print(f"PASS {i} {wl:.1f}nm DONE", flush=True)
json.dump(waves, open("/home/claude/grating/spectral_passes/waves.json","w"))
print("ALL PASSES DONE")
