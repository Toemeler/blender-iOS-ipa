"""Grating demo (demo 3): flat reflective diffraction grating, the same setup as the
earlier v2 result, driven through the shared spectral pipeline for consistency with the
CD and prism. Uses the verified mono OSL grating shader; groove spacing 1000nm."""
import bpy, math, mathutils, os
HERE = os.path.dirname(os.path.abspath(__file__))
def build(wavelength, samples, rx, ry):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn=bpy.context.scene; scn.render.engine='CYCLES'; scn.cycles.device='CPU'
    scn.cycles.shading_system=True; scn.cycles.samples=samples
    scn.render.resolution_x,scn.render.resolution_y=rx,ry
    scn.render.image_settings.file_format='OPEN_EXR'; scn.render.image_settings.color_depth='32'
    scn.view_settings.view_transform='Raw'
    bpy.ops.mesh.primitive_plane_add(size=6); plate=bpy.context.object
    bpy.ops.object.light_add(type='AREA', location=(0,3.0,3.0)); li=bpy.context.object
    li.data.size=0.08; li.data.energy=9000
    li.rotation_euler=mathutils.Vector((0,3,3)).to_track_quat('Z','Y').to_euler()
    bpy.ops.object.camera_add(location=(0,-3.0,3.0)); cam=bpy.context.object
    cam.rotation_euler=(mathutils.Vector((0,-3,3))-mathutils.Vector((0,0.8,0))).to_track_quat('Z','Y').to_euler()
    cam.data.lens=32; scn.camera=cam
    w=bpy.data.worlds.new("W");scn.world=w;w.use_nodes=True
    w.node_tree.nodes["Background"].inputs[0].default_value=(0.004,0.004,0.006,1)
    mat=bpy.data.materials.new("grat");mat.use_nodes=True;nt=mat.node_tree;nt.nodes.clear()
    out=nt.nodes.new("ShaderNodeOutputMaterial")
    sc=nt.nodes.new("ShaderNodeScript"); sc.mode='EXTERNAL'
    sc.filepath=os.path.join(HERE,"diffraction_mono.osl"); sc.update()
    assert sc.outputs,"mono OSL failed"
    sc.inputs["Wavelength"].default_value=wavelength
    sc.inputs["Distance"].default_value=1000.0
    sc.inputs["Tangent"].default_value=(1.0,0.0,0.0)
    nt.links.new(sc.outputs["BRDF"], out.inputs["Surface"])
    plate.data.materials.append(mat)
    return scn
