import bpy, os, sys, math, mathutils

OSL = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.environ.get("OSLFILE","diffraction_grating_v2.osl"))

bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene
scn.render.engine = 'CYCLES'
scn.cycles.device = 'CPU'
scn.cycles.shading_system = True
scn.cycles.samples = 512
scn.cycles.use_denoising = True
scn.render.resolution_x = 800
scn.render.resolution_y = 600

# Large grating foil, slightly tilted toward camera
bpy.ops.mesh.primitive_plane_add(size=6)
plate = bpy.context.object; plate.name = "Grating"


# Small bright light ~35 deg off the mirror direction -> camera sits in the 1st-order fan
bpy.ops.object.light_add(type='AREA', location=(0, 3.0, 3.0))
light = bpy.context.object
light.data.size = 0.08; light.data.energy = 9000
light.rotation_euler = mathutils.Vector((0, 3.0, 3.0)).to_track_quat('Z','Y').to_euler()

bpy.ops.object.camera_add(location=(0, -3.0, 3.0))
cam = bpy.context.object
# aim at plate center: -Z of camera along (target - loc)
cam.rotation_euler = (mathutils.Vector((0,-3.0,3.0)) - mathutils.Vector((0,0.8,0))).to_track_quat('Z','Y').to_euler()
cam.data.lens = 32
scn.camera = cam

w = bpy.data.worlds.new("W"); scn.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.005, 0.005, 0.006, 1)

txt = bpy.data.texts.new(os.environ.get("OSLFILE","diffraction_grating_v2.osl"))
txt.write(open(OSL).read())

mat = bpy.data.materials.new("DiffractionGrating_OSL_v2")
mat.use_nodes = True
nt = mat.node_tree; nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial")
script = nt.nodes.new("ShaderNodeScript")
script.mode = 'INTERNAL'; script.script = txt; script.update()
assert script.outputs, "OSL v2 failed to compile"
script.inputs["Distance"].default_value = 1000.0
script.inputs["Roughness"].default_value = 0.03   # slight blur like real foil
if "Wavelengths" in script.inputs: script.inputs["Wavelengths"].default_value = 8
script.inputs["Tangent"].default_value = (1.0, 0.0, 0.0)
glossy = nt.nodes.new("ShaderNodeBsdfGlossy"); glossy.inputs["Roughness"].default_value = 0.03
glossy.inputs["Color"].default_value = (0.35,0.35,0.35,1)  # damp 0th order so colors dominate
add = nt.nodes.new("ShaderNodeAddShader")
nt.links.new(script.outputs["BRDF"], add.inputs[0])
nt.links.new(glossy.outputs[0], add.inputs[1])
nt.links.new(add.outputs[0], out.inputs["Surface"])
plate.data.materials.append(mat)

bpy.ops.wm.save_as_mainfile(filepath="/home/claude/grating/beugungsgitter_demo.blend")
if "--render" in sys.argv:
    scn.render.filepath = "/home/claude/grating/render_v2.png"
    bpy.ops.render.render(write_still=True)
    print("RENDER DONE")
