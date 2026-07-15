"""CD demo: reflective radial diffraction grating. A small bright light + camera
positioned so the reader sees the classic CD rainbow sweep. Uses the verified
mono OSL shader with a RADIAL tangent so grooves are concentric (like real CD tracks)."""
import bpy, math, mathutils, os
HERE = os.path.dirname(os.path.abspath(__file__))

def build(wavelength, samples, rx, ry):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.render.engine = 'CYCLES'; scn.cycles.device = 'CPU'
    scn.cycles.shading_system = True
    scn.cycles.samples = samples
    scn.render.resolution_x, scn.render.resolution_y = rx, ry
    scn.render.image_settings.file_format = 'OPEN_EXR'
    scn.render.image_settings.color_depth = '32'
    scn.view_settings.view_transform = 'Raw'

    # CD disc
    bpy.ops.mesh.primitive_circle_add(vertices=128, radius=1.2, fill_type='NGON')
    disc = bpy.context.object
    bpy.ops.object.shade_smooth()
    disc.rotation_euler = (math.radians(12), 0, 0)  # tilt toward camera

    # small bright light for crisp orders
    bpy.ops.object.light_add(type='AREA', location=(0.8, 1.4, 2.4))
    li = bpy.context.object
    li.data.size = 0.06; li.data.energy = 3500
    li.rotation_euler = mathutils.Vector((0.8,1.4,2.4)).to_track_quat('Z','Y').to_euler()

    bpy.ops.object.camera_add(location=(0, -2.4, 2.7))
    cam = bpy.context.object
    cam.rotation_euler = (mathutils.Vector((0,-2.4,2.7)) - mathutils.Vector((0,0,0))).to_track_quat('Z','Y').to_euler()
    cam.data.lens = 40
    scn.camera = cam
    w = bpy.data.worlds.new("W"); scn.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.004,0.004,0.006,1)

    # radial tangent: use Tangent node RADIAL so grooves are concentric circles
    mat = bpy.data.materials.new("cd"); mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    sc = nt.nodes.new("ShaderNodeScript"); sc.mode='EXTERNAL'
    sc.filepath = os.path.join(HERE, "diffraction_mono.osl"); sc.update()
    assert sc.outputs, "mono OSL failed"
    tang = nt.nodes.new("ShaderNodeTangent"); tang.direction_type='RADIAL'; tang.axis='Z'
    sc.inputs["Wavelength"].default_value = wavelength
    sc.inputs["Distance"].default_value = 1600.0   # ~625 lines/mm, CD is ~1600nm pitch
    nt.links.new(tang.outputs['Tangent'], sc.inputs['Tangent'])
    nt.links.new(sc.outputs["BRDF"], out.inputs["Surface"])
    disc.data.materials.append(mat)
    return scn
