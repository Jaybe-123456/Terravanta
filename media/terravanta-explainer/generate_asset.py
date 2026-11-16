"""Create the first-party source-export artwork used in the Terravanta explainer."""

import bpy
import math
from pathlib import Path
from mathutils import Vector


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

# Start with an empty scene so a rerender is deterministic.
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)


def material(name, color, roughness=0.58, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    principled = mat.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (*color, 1.0)
    principled.inputs["Roughness"].default_value = roughness
    principled.inputs["Metallic"].default_value = metallic
    return mat


PAPER = [
    material("Paper · ivory", (0.91, 0.93, 0.87)),
    material("Paper · pale sage", (0.78, 0.86, 0.76)),
    material("Paper · warm oat", (0.93, 0.88, 0.75)),
]
INK = material("Ink · deep forest", (0.13, 0.26, 0.17))
SAGE = material("Ink · muted sage", (0.37, 0.50, 0.37))
FAINT = material("Ink · soft line", (0.69, 0.76, 0.67))
AMBER = material("Accent · harvest amber", (0.72, 0.47, 0.16), metallic=0.12)


def add_box(name, parent, location, dimensions, mat, bevel=0.08):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.parent = parent
    obj.location = location
    obj.data.materials.append(mat)
    if bevel:
        modifier = obj.modifiers.new("Soft paper edges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        obj.modifiers.new("Weighted corner normals", "WEIGHTED_NORMAL")
    return obj


positions = [(-0.94, 0.25, 0.0), (0.0, 0.0, 0.16), (0.94, -0.25, 0.32)]
rotations = [-math.radians(13), 0, math.radians(13)]
for index, (position, rotation) in enumerate(zip(positions, rotations)):
    empty = bpy.data.objects.new(f"Export {index + 1} pivot", None)
    bpy.context.collection.objects.link(empty)
    empty.location = position
    empty.rotation_euler[2] = rotation
    add_box(f"Export {index + 1} · paper body", empty, (0, 0, 0), (4.5, 2.75, 0.13), PAPER[index], 0.12)

    # A small stamped mark and precise ledger lines make the objects read as business exports.
    add_box(f"Export {index + 1} · label mark", empty, (-1.78, 0.86, 0.085), (0.36, 0.36, 0.055), INK if index != 2 else AMBER, 0.055)
    add_box(f"Export {index + 1} · title line", empty, (-0.87, 0.88, 0.085), (1.18, 0.075, 0.035), INK, 0.035)
    add_box(f"Export {index + 1} · subtitle line", empty, (-0.94, 0.61, 0.085), (0.84, 0.045, 0.03), SAGE, 0.02)
    for row in range(3):
        y = 0.10 - row * 0.38
        add_box(f"Export {index + 1} · ledger line {row + 1}", empty, (-0.03, y, 0.085), (3.55, 0.035, 0.028), FAINT, 0.015)
        add_box(f"Export {index + 1} · entry mark {row + 1}", empty, (-1.75, y, 0.085), (0.14, 0.14, 0.032), SAGE, 0.025)

# A small node and connector pair hints at data joining without implying a live payment rail.
for x in (-2.65, 2.65):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.12, location=(x, -1.80, 0.10))
    node = bpy.context.object
    node.name = "Connection node · illustrative"
    node.data.materials.append(AMBER if x > 0 else INK)
    for polygon in node.data.polygons:
        polygon.use_smooth = True

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x = 1500
scene.render.resolution_y = 900
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True
scene.render.filepath = str(ASSETS / "export-stack.png")
scene.render.resolution_percentage = 100
scene.render.image_settings.color_depth = "8"
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.image_settings.compression = 12
scene.render.film_transparent = True
scene.view_settings.view_transform = "AgX"
bpy.ops.object.camera_add(location=(5.8, -7.5, 8.4))
camera = bpy.context.object
camera.name = "Explainer camera"
camera.data.type = "ORTHO"
camera.data.ortho_scale = 8.9
target = Vector((0.0, 0.0, 0.12))
camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = camera

def add_area(name, location, energy, size, color):
    bpy.ops.object.light_add(type="AREA", location=location)
    light = bpy.context.object
    light.name = name
    light.data.energy = energy
    light.data.shape = "DISK"
    light.data.size = size
    light.data.color = color
    light.rotation_euler = (target - light.location).to_track_quat("-Z", "Y").to_euler()

add_area("Key · softbox", (1.5, -3.4, 7.0), 920, 6.0, (1.0, 0.91, 0.76))
add_area("Fill · daylight", (-4.5, -1.0, 4.0), 640, 5.5, (0.79, 0.91, 0.78))
add_area("Rim · leaf", (2.5, 4.0, 5.0), 780, 4.0, (0.88, 0.96, 0.82))

scene.render.image_settings.file_format = "PNG"
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "terravanta-export-stack.blend"))
bpy.ops.render.render(write_still=True)
