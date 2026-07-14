# Diffraction grating ("Beugungsgitter") scene setup for Cycles
# Uses Secrop's (Miguel Porces) OSL Diffraction shader - physically based,
# per-sample wavelength via the grating equation: sin(theta_m) = sin(theta_i) + m*lambda/d
#
# Usage (desktop / headless):  blender -b -P setup_grating.py
# On builds without OSL support, falls back to a node-based approximation.

import bpy, os, sys

OSL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diffraction_grating.osl")

def clean_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def make_scene():
    scn = bpy.context.scene
    scn.render.engine = 'CYCLES'
    # OSL requires CPU
    scn.cycles.device = 'CPU'
    try:
        scn.cycles.shading_system = True  # enable OSL
    except Exception:
        pass
    scn.cycles.samples = 128
    scn.render.resolution_x = 640
    scn.render.resolution_y = 480

    # Grating plate (like a piece of holographic foil / CD surface)
    bpy.ops.mesh.primitive_plane_add(size=2)
    plate = bpy.context.object
    plate.name = "Grating"

    # Small sphere to catch reflections
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, location=(0, -0.8, 0.3))
    bpy.ops.object.shade_smooth()

    # Sun-like small bright area light (near point source -> crisp orders)
    bpy.ops.object.light_add(type='AREA', location=(0, 2.0, 2.0))
    light = bpy.context.object
    light.data.size = 0.1
    light.data.energy = 5000
    # aim at origin
    import mathutils
    light.rotation_euler = (mathutils.Vector((0,2,2)).to_track_quat('Z','Y').to_euler())

    # Camera mirrored across the normal -> sees 0th order + spread of orders
    bpy.ops.object.camera_add(location=(0, -2.0, 2.0))
    cam = bpy.context.object
    cam.rotation_euler = mathutils.Vector((0,-2,2)).to_track_quat('Z','Y').to_euler()
    scn.camera = cam

    # World: dark, so spectral orders stand out
    w = bpy.data.worlds.new("W"); scn.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.01, 0.01, 0.012, 1)
    return plate

def osl_material(plate):
    mat = bpy.data.materials.new("DiffractionGrating_OSL")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    script = nt.nodes.new("ShaderNodeScript")
    script.mode = 'EXTERNAL'
    script.filepath = OSL_PATH
    script.update()
    if not script.outputs:
        raise RuntimeError("OSL script did not compile / OSL unavailable")
    # Mix a plain glossy for the 0th order (shader skips order 0 by design)
    glossy = nt.nodes.new("ShaderNodeBsdfGlossy")
    glossy.inputs["Roughness"].default_value = 0.02
    add = nt.nodes.new("ShaderNodeAddShader")
    # Grating parameters: Distance = groove spacing in nm (1200 nm ~ 833 lines/mm)
    script.inputs["Distance"].default_value = 1000.0
    script.inputs["Tangent"].default_value = (1.0, 0.0, 0.0)  # groove direction (plate normal is +Z)
    script.inputs["Roughness"].default_value = 0.0
    nt.links.new(script.outputs["BRDF"], add.inputs[0])
    nt.links.new(glossy.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    plate.data.materials.append(mat)
    return mat

def node_fallback(plate):
    # Metal/GPU-safe approximation: grating equation evaluated in nodes for
    # N wavelength bins, each reflected about a rotated normal.
    import math
    mat = bpy.data.materials.new("DiffractionGrating_Nodes")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")

    d_nm = 1000.0   # groove spacing
    bins = [(380,(0.2,0,0.9)),(440,(0,0.1,1)),(490,(0,0.8,0.9)),(530,(0,1,0.1)),
            (570,(0.7,1,0)),(600,(1,0.6,0)),(650,(1,0.1,0)),(720,(0.6,0,0))]
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    tang = nt.nodes.new("ShaderNodeTangent"); tang.direction_type='RADIAL'; tang.axis='Z'
    prev = None
    for wl, col in bins:
        # first-order deflection angle offset ~ asin(lambda/d) around normal, approximated
        ang = math.asin(min(0.999, wl/d_nm))
        rot = nt.nodes.new("ShaderNodeVectorRotate")
        rot.rotation_type = 'AXIS_ANGLE'
        rot.inputs['Angle'].default_value = ang
        nt.links.new(geom.outputs['Normal'], rot.inputs['Vector'])
        nt.links.new(tang.outputs['Tangent'], rot.inputs['Axis'])
        g = nt.nodes.new("ShaderNodeBsdfGlossy")
        g.inputs['Roughness'].default_value = 0.05
        g.inputs['Color'].default_value = (*col, 1)
        nt.links.new(rot.outputs['Vector'], g.inputs['Normal'])
        if prev is None:
            prev = g
        else:
            add = nt.nodes.new("ShaderNodeAddShader")
            nt.links.new(prev.outputs[0], add.inputs[0])
            nt.links.new(g.outputs[0], add.inputs[1])
            prev = add
    base = nt.nodes.new("ShaderNodeBsdfGlossy")
    base.inputs['Roughness'].default_value = 0.02
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(prev.outputs[0], add.inputs[0])
    nt.links.new(base.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs['Surface'])
    plate.data.materials.append(mat)
    return mat

if __name__ == "__main__":
    clean_scene()
    plate = make_scene()
    try:
        osl_material(plate)
        mode = "OSL"
    except Exception as e:
        print("OSL unavailable (%s), using node fallback" % e)
        node_fallback(plate)
        mode = "NODES"
    print("MATERIAL MODE:", mode)
    if "--render" in sys.argv:
        bpy.context.scene.render.filepath = "/home/claude/grating/test_render.png"
        bpy.ops.render.render(write_still=True)
        print("RENDER DONE")
