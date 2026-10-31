"""Builds the machine's rigid hardware and exports it as one glTF file. Runs on Blender 4.5:

    blender --background --python web/models/machine.py -- web/public/models/machine.glb

Each node() below is one rigid group that the viewer places with <Model name="..." />, so its coordinates are that
group's own (the same numbers as the group in stations.jsx etc.). Sizes are scene units in the viewer's axes: y up,
z towards the camera. Whatever changes at runtime stays in the JSX: belts, lamps, screens, stoppers, the scaled rods,
vacuum cups, trays, parts, the syringe's contents and the transparent guards.
"""
import math
import sys
from contextlib import contextmanager

import bmesh
import bpy
from mathutils import Matrix, Vector

OUT = sys.argv[sys.argv.index("--") + 1]

# keep in step with web/src/viewer/layout.js
BELT_TOP = 0.15
LANE_Z, LANE_W = 0.14, 0.07
ZONE_LEN = 2.1
PART_W, PART_D = 0.7, 0.36
LIFT_H = 0.05
FLOOR_Y = -1.15
FRAME_X, Z_BACK, Z_FRONT, H = 6.85, -2.65, 2.05, 2.6
W, D, ZC = FRAME_X * 2, Z_FRONT - Z_BACK, (Z_FRONT + Z_BACK) / 2
P = 0.08
STOPPER_X = PART_W / 2 + 0.05

bpy.ops.wm.read_factory_settings(use_empty=True)


def linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def material(name, hex_color, metallic, roughness):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    rgb = [linear(int(hex_color[i:i + 2], 16) / 255) for i in (1, 3, 5)]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return m


ANODIZED = material("anodized", "#1c2127", 0.35, 0.42)
SLOT = material("slot", "#20262c", 0.3, 0.6)
ALU = material("alu", "#b9c3cd", 0.8, 0.3)
ALU_DARK = material("alu_dark", "#56626e", 0.65, 0.38)
STEEL = material("steel", "#d4dbe2", 0.95, 0.18)
BRASS = material("brass", "#b08d57", 0.9, 0.32)
LUER = material("luer", "#e1709f", 0.0, 0.4)
WHITE = material("white", "#e3e7eb", 0.05, 0.45)
BLUE = material("blue", "#2f6fc0", 0.05, 0.38)
GLASS = material("glass", "#0a1622", 0.9, 0.05)
PLATE = material("plate", "#2f3740", 0.5, 0.45)
CABINET = material("cabinet", "#b4bcc5", 0.2, 0.55)
PANEL = material("panel", "#d5dade", 0.1, 0.5)
YELLOW = material("yellow", "#e2b521", 0.1, 0.45)
PAD = material("pad", "#e6c34a", 0.1, 0.5)
RED = material("red", "#b9262d", 0.1, 0.42)
RUBBER = material("rubber", "#14171b", 0.0, 0.85)

TO_B = Matrix.Rotation(math.pi / 2, 4, "X")  # viewer (x, y up, z front) to Blender (x, y back, z up)


def to_b(p):
    return Vector((p[0], -p[2], p[1]))


def add(mesh_data, mat, location=(0, 0, 0), rotation=None):
    mesh = bpy.data.meshes.new("part")
    mesh_data.to_mesh(mesh)
    mesh_data.free()
    obj = bpy.data.objects.new("part", mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    if rotation is not None:
        obj.rotation_mode = "QUATERNION"
        obj.rotation_quaternion = rotation
    obj.data.materials.append(mat)
    return obj


def finish(obj, bevel=0.0, flat=False):
    if bevel:
        mod = obj.modifiers.new("bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "ANGLE"
        mod.angle_limit = math.radians(30)
    if not flat:
        for poly in obj.data.polygons:
            poly.use_smooth = True
        split = obj.modifiers.new("split", "EDGE_SPLIT")
        # below the bevel's 30 degree steps, or the flat faces blend into their bevels and look dented
        split.split_angle = math.radians(20)
    return obj


def box(size, center, mat, bevel=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(size[0], size[2], size[1]), verts=bm.verts)
    return finish(add(bm, mat, to_b(center)), bevel)


def cyl(start, end, r, mat, r2=None, segments=24, bevel=0.0, knurl=False):
    """Cylinder or cone from start (radius r) to end (radius r2)."""
    a, b = to_b(start), to_b(end)
    d = b - a
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=r, radius2=r if r2 is None else r2, depth=d.length)
    if knurl:
        for v in bm.verts:
            if round(math.atan2(v.co.y, v.co.x) / (2 * math.pi / segments)) % 2:
                v.co.x *= 0.93
                v.co.y *= 0.93
    obj = add(bm, mat, (a + b) / 2, Vector((0, 0, 1)).rotation_difference(d))
    return finish(obj, bevel, flat=knurl or segments <= 8)


def cut(target, cutter):
    bpy.context.view_layer.objects.active = target
    mod = target.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter
    # the boolean goes before the bevel, so the edges of the cut get softened too
    bpy.ops.object.modifier_move_to_index(modifier=mod.name, index=0)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter)
    return target


@contextmanager
def at(position=(0, 0, 0), rotation=(0, 0, 0)):
    """Everything built inside is moved as a group; the rotation is a three.js XYZ euler."""
    before = set(bpy.data.objects)
    yield
    bpy.context.view_layer.update()
    r = Matrix.Rotation(rotation[0], 4, "X") @ Matrix.Rotation(rotation[1], 4, "Y") @ Matrix.Rotation(rotation[2], 4, "Z")
    m = TO_B @ Matrix.Translation(position) @ r @ TO_B.inverted()
    for obj in set(bpy.data.objects) - before:
        obj.matrix_world = m @ obj.matrix_world


NODES = []


@contextmanager
def node(name):
    """Joins everything built inside into one mesh per material, which keeps the draw calls down."""
    before = set(bpy.data.objects)
    yield
    new = list(set(bpy.data.objects) - before)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in new:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = name
    joined.data.name = name
    NODES.append(joined)
    print(f"node {name}: {len(joined.data.polygons)} faces, {len(joined.data.materials)} materials")


# --- shared hardware ---------------------------------------------------------------------------------------------


def bolt(p, d=(0, 0, 1), r=0.007):
    """Socket head screw at p, standing out along direction d."""
    end = (p[0] + d[0] * 0.005, p[1] + d[1] * 0.005, p[2] + d[2] * 0.005)
    cyl(p, end, r, STEEL, segments=12)
    cyl((p[0] + d[0] * 0.003, p[1] + d[1] * 0.003, p[2] + d[2] * 0.003),
        (p[0] + d[0] * 0.006, p[1] + d[1] * 0.006, p[2] + d[2] * 0.006), r * 0.55, ANODIZED, segments=6)


def profile(size, center, mat=ALU):
    """Aluminium extrusion: softened bar with a T-slot down the middle of each long face."""
    box(size, center, mat, bevel=0.004)
    long = size.index(max(size))
    sides = [i for i in range(3) if i != long]
    for i in sides:
        across = next(j for j in sides if j != i)
        slot = list(size)
        slot[i] = 0.004
        slot[long] = size[long] - 0.01
        slot[across] = size[across] * 0.24
        for side in (-1, 1):
            p = list(center)
            p[i] += side * (size[i] / 2 - 0.001)
            box(slot, p, SLOT)


def rail(length, center, axis="z"):
    """Linear guide: stepped steel rail with counterbored screws along the top."""
    along = (lambda w, h: (w, h, length)) if axis == "z" else (lambda w, h: (length, h, w))
    x, y, z = center
    box(along(0.05, 0.02), (x, y - 0.01, z), STEEL, bevel=0.002)
    box(along(0.032, 0.02), (x, y + 0.01, z), STEEL, bevel=0.002)
    count = max(2, round(length / 0.16))
    for i in range(count):
        d = -length / 2 + (i + 0.5) * (length / count)
        p = (x, y + 0.02, z + d) if axis == "z" else (x + d, y + 0.02, z)
        cyl(p, (p[0], p[1] + 0.002, p[2]), 0.007, ANODIZED, segments=8)


def servo(position, rotation=(0, 0, 0)):
    """Servo motor with cooling fins, bolted flange, shaft, encoder cap and connector; the shaft points along +z."""
    with at(position, rotation):
        box((0.15, 0.15, 0.24), (0, 0, 0), ANODIZED, bevel=0.01)
        for z in (-0.08, -0.04, 0, 0.04):
            box((0.156, 0.156, 0.008), (0, 0, z), SLOT, bevel=0.002)
        box((0.17, 0.17, 0.03), (0, 0, 0.13), ALU_DARK, bevel=0.004)
        for sx in (-0.065, 0.065):
            for sy in (-0.065, 0.065):
                bolt((sx, sy, 0.145), r=0.008)
        cyl((0, 0, 0.145), (0, 0, 0.17), 0.022, STEEL, segments=16)
        box((0.1, 0.1, 0.03), (0, 0, -0.13), ALU_DARK, bevel=0.005)
        box((0.05, 0.04, 0.06), (0, 0.09, -0.06), SLOT, bevel=0.003)
        cyl((0, 0.11, -0.06), (0, 0.13, -0.06), 0.012, BRASS, segments=8)


def chain(length, position, axis="z"):
    """Energy chain: pairs of side plates joined by a cross bar."""
    links = max(2, round(length / 0.07))
    with at(position, (0, 0, 0) if axis == "z" else (0, math.pi / 2, 0)):
        for i in range(links):
            d = -length / 2 + (i + 0.5) * (length / links)
            for sx in (-0.04, 0.04):
                box((0.01, 0.05, 0.062), (sx, 0, d), ANODIZED, bevel=0.002)
            box((0.07, 0.008, 0.02), (0, 0.021, d), ANODIZED)


def camera_mount(arm_y):
    """Overhead column with an arm reaching over the belt."""
    box((0.26, 0.03, 0.26), (0, 0.015, -0.95), ALU_DARK, bevel=0.004)
    for sx in (-0.1, 0.1):
        for sz in (-1.05, -0.85):
            bolt((sx, 0.03, sz), (0, 1, 0))
    profile((0.08, arm_y + 0.06, 0.08), (0, (arm_y + 0.06) / 2, -0.95))
    profile((0.08, 0.08, 1.0), (0, arm_y, -0.47))
    with at((0, arm_y - 0.13, -0.84), (-math.pi / 4, 0, 0)):
        box((0.05, 0.025, 0.2), (0, 0, 0), ALU_DARK, bevel=0.003)


def lens(top, bottom, r):
    """Machine vision lens from the camera body down, with knurled focus rings and dark glass."""
    cyl((0, top, 0), (0, bottom, 0), r, ANODIZED, segments=32, bevel=0.002)
    span = top - bottom
    for f in (0.3, 0.62):
        y = top - span * f
        cyl((0, y, 0), (0, y - span * 0.14, 0), r * 1.06, ALU_DARK, segments=48, knurl=True)
    cyl((0, bottom, 0), (0, bottom - 0.002, 0), r * 0.82, GLASS, segments=32)


def air_cylinder(size, center, axis):
    """Compact air cylinder: anodized body, end caps, two brass ports."""
    box(size, center, ALU, bevel=0.004)
    long = size.index(max(size))
    for side in (-1, 1):
        cap = list(size)
        cap[long] = 0.016
        cap = [c + 0.006 if i != long else c for i, c in enumerate(cap)]
        p = list(center)
        p[long] += side * (size[long] / 2 - 0.006)
        box(cap, p, ALU_DARK, bevel=0.003)
        q = list(center)
        q[long] += side * (size[long] / 2 - 0.035)
        cyl((q[0], q[1] + size[1] / 2, q[2]), (q[0], q[1] + size[1] / 2 + 0.018, q[2]), 0.007, BRASS, segments=6)


# --- conveyor ----------------------------------------------------------------------------------------------------


def conveyor_zone(frame):
    for z in (-LANE_Z, LANE_Z):
        # channel the belt runs in: two side plates on a base, a slide bed under the belt, idlers at the ends
        for side in (-1, 1):
            box((ZONE_LEN, 0.13, 0.012), (0, 0.065, z + side * 0.044), frame, bevel=0.002)
            for x in (-0.9, -0.45, 0, 0.45, 0.9):
                bolt((x, 0.04, z + side * 0.05), (0, 0, side), r=0.006)
        box((ZONE_LEN, 0.012, 0.1), (0, 0.006, z), frame)
        box((ZONE_LEN - 0.14, 0.05, 0.07), (0, 0.105, z), SLOT)
        for x in (-ZONE_LEN / 2 + 0.03, ZONE_LEN / 2 - 0.03):
            cyl((x, 0.115, z - 0.038), (x, 0.115, z + 0.038), 0.026, STEEL, segments=24)
            cyl((x, 0.115, z - 0.052), (x, 0.115, z + 0.052), 0.008, ANODIZED, segments=12)
    # guide rails on posts keep the part between the lanes
    for side in (-1, 1):
        z = side * (PART_D / 2 + 0.03)
        box((ZONE_LEN, 0.03, 0.012), (0, BELT_TOP + 0.03, z), STEEL, bevel=0.002)
        for x in (-0.8, 0, 0.8):
            box((0.02, 0.06, 0.02), (x, BELT_TOP, side * (PART_D / 2 + 0.045)), ALU_DARK, bevel=0.002)
            box((0.03, 0.02, 0.022), (x, BELT_TOP + 0.03, side * (PART_D / 2 + 0.043)), ANODIZED, bevel=0.002)
    # cross members and the zone drive
    for x in (-ZONE_LEN / 2 + 0.1, ZONE_LEN / 2 - 0.1):
        profile((0.06, 0.04, 2 * LANE_Z + LANE_W), (x, 0.03, 0), ALU_DARK)
    servo((ZONE_LEN / 2 - 0.25, 0.07, -LANE_Z - 0.17))
    box((0.13, 0.13, 0.03), (ZONE_LEN / 2 - 0.25, 0.09, -LANE_Z - 0.03 - 0.035), ALU_DARK, bevel=0.004)


with node("conveyor_zone"):
    conveyor_zone(ALU)

with node("conveyor_zone_neighbour"):
    conveyor_zone(ALU_DARK)

with node("conveyor_stop"):
    # stop pin's air cylinder between the lanes, and the part sensor on the front rail
    box((0.06, 0.12, 0.05), (STOPPER_X, 0.05, 0), ALU_DARK, bevel=0.004)
    cyl((STOPPER_X + 0.03, 0.03, 0), (STOPPER_X + 0.045, 0.03, 0), 0.006, BRASS, segments=6)
    box((0.04, 0.04, 0.03), (0.1, BELT_TOP + 0.05, PART_D / 2 + 0.06), ANODIZED, bevel=0.004)
    box((0.03, 0.05, 0.006), (0.1, BELT_TOP + 0.02, PART_D / 2 + 0.05), ALU, bevel=0.001)

with node("lift_base"):
    cyl((0, 0, 0), (0, 0.1, 0), 0.045, ALU, segments=32, bevel=0.002)
    cyl((0, 0, 0), (0, 0.012, 0), 0.052, ALU_DARK, segments=32, bevel=0.002)
    cyl((0, 0.088, 0), (0, 0.1, 0), 0.052, ALU_DARK, segments=32, bevel=0.002)
    cyl((0.045, 0.05, 0), (0.062, 0.05, 0), 0.007, BRASS, segments=6)

with node("lift_plate"):
    plate = box((0.5, 0.02, 2 * LANE_Z - LANE_W - 0.03), (0, -0.01, 0), ALU_DARK, bevel=0.002)
    cyl((0, -0.14, 0), (0, -0.02, 0), 0.015, STEEL, segments=16)
    for x in (-0.19, 0.19):
        cyl((x, -0.1, 0), (x, -0.02, 0), 0.007, STEEL, segments=12)

# --- infeed ------------------------------------------------------------------------------------------------------

with node("infeed_reader"):
    box((0.14, 0.015, 0.14), (-0.2, 0.0075, -0.5), ALU_DARK, bevel=0.003)
    profile((0.05, 0.6, 0.05), (-0.2, 0.3, -0.5), ALU_DARK)
    box((0.07, 0.05, 0.1), (-0.2, 0.585, -0.45), ALU, bevel=0.004)
    with at((-0.2, 0.62, -0.38), (0.9, 0, 0)):
        box((0.12, 0.08, 0.16), (0, 0, 0), ANODIZED, bevel=0.008)
        box((0.09, 0.002, 0.04), (0, 0.041, -0.03), ALU)
        cyl((0, 0, -0.08), (0, 0, -0.1), 0.012, BRASS, segments=8)
        for sx in (-0.045, 0.045):
            bolt((sx, 0.04, 0.055), (0, 1, 0), r=0.005)

# --- vision ------------------------------------------------------------------------------------------------------

PAD_Y = BELT_TOP + LIFT_H + 0.03

with node("vision_fixed"):
    camera_mount(1.6)
    # camera with fins, connectors, its mount, then the lens
    box((0.16, 0.24, 0.16), (0, 1.42, 0), ANODIZED, bevel=0.008)
    for y in (1.36, 1.4, 1.44, 1.48):
        box((0.166, 0.01, 0.166), (0, y, 0), SLOT, bevel=0.002)
    box((0.17, 0.02, 0.17), (0, 1.55, 0), ALU_DARK, bevel=0.003)
    box((0.12, 0.04, 0.012), (0, 1.5, 0.083), ALU)
    for x in (-0.03, 0.03):
        cyl((x, 1.34, 0.08), (x, 1.34, 0.1), 0.013, BRASS, segments=12)
    lens(1.3, 1.16, 0.055)
    # ring light housing on its arm (the lit ring itself is in the JSX)
    profile((0.04, 0.48, 0.04), (0.32, 1.0, 0), ALU_DARK)
    housing = cyl((0, 0.76, 0), (0, 0.8, 0), 0.335, ANODIZED, segments=72, bevel=0.004)
    cut(housing, cyl((0, 0.74, 0), (0, 0.82, 0), 0.265, ANODIZED, segments=72))
    # end pusher and side pusher bodies on short stands
    air_cylinder((0.18, 0.06, 0.06), (-0.86, PAD_Y, 0), "x")
    box((0.05, PAD_Y - 0.03, 0.05), (-0.86, (PAD_Y - 0.03) / 2, 0), ALU_DARK, bevel=0.003)
    air_cylinder((0.06, 0.06, 0.18), (0, PAD_Y, 0.74), "z")
    box((0.05, PAD_Y - 0.03, 0.05), (0, (PAD_Y - 0.03) / 2, 0.74), ALU_DARK, bevel=0.003)

with node("vision_pusher_x"):
    cyl((-0.25, 0, 0), (0, 0, 0), 0.01, STEEL, segments=12)
    box((0.02, 0.04, 0.12), (0, 0, 0), PAD, bevel=0.003)
    box((0.012, 0.03, 0.05), (-0.015, 0, 0), ALU_DARK)

with node("vision_pusher_z"):
    cyl((0, 0, 0.25), (0, 0, 0), 0.01, STEEL, segments=12)
    box((0.2, 0.04, 0.02), (0, 0, 0), PAD, bevel=0.003)
    box((0.05, 0.03, 0.012), (0, 0, 0.015), ALU_DARK)

# --- dispenser ---------------------------------------------------------------------------------------------------

BEAM_Y = 1.85
SCALE_X, SCALE_Z, SCALE_TOP = 0.75, -1.0, 0.2

with node("dispenser_fixed"):
    rail(1.4, (0, 0.02, -1.9), "x")
    servo((-0.85, 0.08, -1.9), (0, -math.pi / 2, 0))
    # dispensing controller (its screen is in the JSX)
    with at((-0.8, 0, -2.2)):
        box((0.7, 0.32, 0.4), (0, 0.17, 0), PANEL, bevel=0.012)
        box((0.68, 0.012, 0.38), (0, 0.33, 0), ALU_DARK, bevel=0.002)
        for x in (-0.31, 0.31):
            for z in (-0.17, 0.17):
                cyl((x, 0, z), (x, 0.015, z), 0.022, RUBBER, segments=12)
        for x in (0.12, 0.22):
            cyl((x, 0.2, 0.2), (x, 0.2, 0.232), 0.026, ALU, segments=32, knurl=True)
            cyl((x, 0.2, 0.232), (x, 0.2, 0.236), 0.012, ANODIZED, segments=16)
        for i in range(5):
            box((0.1, 0.006, 0.002), (-0.12, 0.1 + i * 0.012, 0.2), ANODIZED)
    # weigh scale base and pan (its draft shield and screen are in the JSX)
    with at((SCALE_X, 0, SCALE_Z)):
        box((0.42, 0.12, 0.38), (0, 0.06, 0), PANEL, bevel=0.01)
        box((0.36, 0.01, 0.32), (0, 0.122, -0.01), ALU_DARK, bevel=0.002)
        cyl((0, 0.127, 0), (0, SCALE_TOP - 0.06, 0), 0.03, ALU, segments=16)
        cyl((0, SCALE_TOP - 0.066, 0), (0, SCALE_TOP - 0.054, 0), 0.11, STEEL, segments=48, bevel=0.002)

with node("dispenser_bridge"):
    box((0.3, 0.08, 0.3), (0, 0.06, -1.9), ALU_DARK, bevel=0.008)
    for x in (-0.12, 0.12):
        for z in (-2.02, -1.78):
            bolt((x, 0.1, z), (0, 1, 0), r=0.009)
    profile((0.14, BEAM_Y, 0.14), (0, BEAM_Y / 2 + 0.1, -1.9))
    profile((0.18, 0.16, 2.35), (0, BEAM_Y, -0.8))
    with at((0, BEAM_Y - 0.24, -1.665), (-math.pi / 4, 0, 0)):
        box((0.08, 0.04, 0.46), (0, 0, 0), ALU_DARK, bevel=0.004)
    rail(2.2, (0.11, BEAM_Y, -0.8))
    servo((0, BEAM_Y, -2.1), (0, math.pi, 0))
    chain(1.3, (-0.03, BEAM_Y + 0.11, -1.25))
    box((0.18, 0.18, 0.02), (0, BEAM_Y, 0.385), ALU_DARK, bevel=0.003)

with node("dispenser_carriage"):
    box((0.3, 0.24, 0.3), (0, BEAM_Y, 0), ALU_DARK, bevel=0.012)
    for x in (-0.12, 0.12):
        for y in (-0.09, 0.09):
            bolt((x, BEAM_Y + y, 0.15), r=0.009)
    box((0.2, 0.06, 0.003), (0, BEAM_Y, 0.15), ALU)
    box((0.07, 0.05, 0.12), (0.11, BEAM_Y + 0.03, 0.06), STEEL, bevel=0.004)
    box((0.07, 0.05, 0.12), (0.11, BEAM_Y + 0.03, -0.06), STEEL, bevel=0.004)
    servo((0, BEAM_Y + 0.2, -0.12), (-math.pi / 2, 0, 0))


def socket_screw(x, y, z):
    bolt((x, y, z), r=0.0065)


def collar(y0, y1, outer, inner, mat):
    """Barrel collar with a clamp screw on the front."""
    r = cyl((0, y0, 0), (0, y1, 0), outer, mat, segments=48, bevel=0.002)
    cut(r, cyl((0, y0 - 0.01, 0), (0, y1 + 0.01, 0), inner, mat, segments=48))
    y = (y0 + y1) / 2
    box((0.042, y1 - y0, 0.022), (0, y, outer + 0.006), mat, bevel=0.002)
    cyl((-0.027, y, outer + 0.006), (0.027, y, outer + 0.006), 0.0055, STEEL, segments=12)


with node("dispenser_head"):
    # needle and luer hub (the needle tip is this group's origin)
    cyl((0, 0, 0), (0, 0.12, 0), 0.0045, STEEL, r2=0.007, segments=16)
    cyl((0, 0.115, 0), (0, 0.165, 0), 0.012, LUER, r2=0.028, segments=24)
    box((0.07, 0.03, 0.006), (0, 0.15, 0), LUER, bevel=0.002)
    cyl((0, 0.163, 0), (0, 0.177, 0), 0.031, STEEL, segments=48, knurl=True)
    # valve body with grooves on its right side, a front plate and four screws
    valve = box((0.17, 0.1, 0.17), (0, 0.22, 0), ANODIZED, bevel=0.006)
    for y in (0.195, 0.22, 0.245):
        cut(valve, box((0.012, 0.006, 0.19), (0.085, y, 0), ANODIZED))
    plate = box((0.14, 0.085, 0.006), (0, 0.22, 0.087), ALU, bevel=0.0015)
    cut(plate, cyl((0, 0.22, 0.08), (0, 0.22, 0.095), 0.011, ALU, segments=24))  # the valve lamp sits in this hole
    for sx in (-0.058, 0.058):
        for y in (0.19, 0.25):
            socket_screw(sx, y, 0.09)
    # solenoid on the left with coil bands, end cap and connector
    cyl((-0.085, 0.2, 0), (-0.155, 0.2, 0), 0.03, ALU_DARK, segments=32, bevel=0.002)
    for x in (-0.103, -0.137):
        cyl((x, 0.2, 0), (x - 0.006, 0.2, 0), 0.032, ANODIZED, segments=32)
    cyl((-0.155, 0.2, 0), (-0.168, 0.2, 0), 0.019, ANODIZED, segments=24, bevel=0.002)
    box((0.03, 0.022, 0.036), (-0.125, 0.24, 0), ANODIZED, bevel=0.002)
    for z in (-0.009, 0.009):
        cyl((-0.125, 0.251, z), (-0.125, 0.258, z), 0.003, BRASS, segments=8)
    # air inlet: hex fitting, brass push-in and its blue release ring
    cyl((-0.085, 0.25, 0.05), (-0.1, 0.25, 0.05), 0.016, BRASS, segments=6)
    cyl((-0.1, 0.25, 0.05), (-0.128, 0.25, 0.05), 0.011, BRASS, segments=16)
    cyl((-0.128, 0.25, 0.05), (-0.134, 0.25, 0.05), 0.013, BLUE, segments=16)
    # cradle that holds the barrel: two collars, guide rods, a back plate with lightening holes
    collar(0.27, 0.295, 0.082, 0.0712, ALU)
    collar(0.715, 0.74, 0.082, 0.0712, ALU)
    for x in (-0.078, 0.078):
        cyl((x, 0.295, 0), (x, 0.715, 0), 0.005, STEEL, segments=12)
    back = box((0.1, 0.6, 0.012), (0, 0.48, -0.079), ALU_DARK, bevel=0.002)
    for y in (0.37, 0.49, 0.61):
        cut(back, cyl((0, y, -0.1), (0, y, -0.06), 0.028, ALU_DARK, segments=32))
    for sx in (-0.035, 0.035):
        socket_screw(sx, 0.765, -0.073)
    # bracket that carries the head on the Z rod
    box((0.08, 0.14, 0.085), (0, 0.24, -0.115), ALU_DARK, bevel=0.006)
    # finger flange, then the blue air adapter with bayonet ears and a brass barb
    cyl((0, 0.74, 0), (0, 0.752, 0), 0.095, WHITE, segments=48, bevel=0.002)
    cyl((0, 0.752, 0), (0, 0.8, 0), 0.08, BLUE, segments=48, bevel=0.003)
    box((0.19, 0.012, 0.03), (0, 0.76, 0), BLUE, bevel=0.002)
    cyl((0, 0.8, 0), (0, 0.83, 0), 0.03, BLUE, segments=24, bevel=0.002)
    cyl((0, 0.83, 0), (0, 0.86, 0), 0.012, BRASS, r2=0.007, segments=16)
    # height sensor on an arm, with a label, a lens and a cable gland
    box((0.075, 0.022, 0.03), (0.1125, 0.255, 0), ALU, bevel=0.002)
    box((0.07, 0.13, 0.08), (0.14, 0.2, 0), ANODIZED, bevel=0.007)
    box((0.05, 0.03, 0.002), (0.14, 0.225, 0.0405), ALU)
    cyl((0.14, 0.135, 0), (0.14, 0.132, 0), 0.02, STEEL, segments=24)
    cyl((0.14, 0.265, 0), (0.14, 0.285, 0), 0.012, ANODIZED, segments=6)

# --- inspection --------------------------------------------------------------------------------------------------

with node("inspection_fixed"):
    camera_mount(1.55)
    profile((1.2, 0.08, 0.1), (0, 1.47, 0))
    rail(1.1, (0, 1.42, 0.06), "x")
    servo((0.68, 1.47, 0), (0, math.pi / 2, 0))
    for x in (-0.61, 0.61):
        box((0.02, 0.1, 0.12), (x, 1.47, 0), ALU_DARK, bevel=0.003)

with node("inspection_scanner"):
    box((0.2, 0.06, 0.18), (0, 1.39, 0), ALU_DARK, bevel=0.006)
    for x in (-0.08, 0.08):
        for z in (-0.07, 0.07):
            bolt((x, 1.42, z), (0, 1, 0), r=0.006)
    box((0.14, 0.18, 0.16), (0, 1.27, 0), ANODIZED, bevel=0.008)
    for y in (1.3, 1.33):
        box((0.146, 0.008, 0.166), (0, y, 0), SLOT, bevel=0.002)
    box((0.07, 0.03, 0.002), (-0.025, 1.26, 0.081), ALU)
    cyl((0, 1.18, 0), (0, 1.08, 0), 0.045, ANODIZED, segments=32, bevel=0.002)
    cyl((0, 1.14, 0), (0, 1.12, 0), 0.048, ALU_DARK, segments=48, knurl=True)
    cyl((0, 1.08, 0), (0, 1.078, 0), 0.037, GLASS, segments=32)
    # line laser, tilted towards the camera's view
    box((0.09, 0.02, 0.05), (0.11, 1.28, 0), ALU_DARK, bevel=0.002)
    with at((0.16, 1.2, 0), (0, 0, 0.35)):
        box((0.05, 0.16, 0.07), (0, 0, 0), ANODIZED, bevel=0.006)
        box((0.03, 0.004, 0.05), (0, -0.081, 0), GLASS)
        cyl((0, 0.08, 0), (0, 0.095, 0), 0.01, BRASS, segments=8)

# --- outfeed -----------------------------------------------------------------------------------------------------

GANTRY_Y = 1.6
COLUMN_Z = -1.9

with node("ng_drawer"):
    box((1.06, 0.06, 0.7), (0, 0, 0), RED, bevel=0.008)
    box((1.0, 0.004, 0.012), (0, 0.03, 0.34), YELLOW)
    box((0.3, 0.03, 0.03), (0, 0.03, 0.37), STEEL, bevel=0.006)
    for x in (-0.13, 0.13):
        box((0.03, 0.03, 0.05), (x, 0.03, 0.355), ALU_DARK, bevel=0.003)

with node("gantry_fixed"):
    box((0.32, 0.03, 0.32), (0, 0.015, COLUMN_Z), ALU_DARK, bevel=0.004)
    for x in (-0.13, 0.13):
        for z in (COLUMN_Z - 0.13, COLUMN_Z + 0.13):
            bolt((x, 0.03, z), (0, 1, 0), r=0.009)
    profile((0.12, GANTRY_Y + 0.12, 0.12), (0, (GANTRY_Y + 0.12) / 2, COLUMN_Z))
    profile((0.16, 0.14, 2.35), (0, GANTRY_Y + 0.08, -0.78))
    with at((0, GANTRY_Y - 0.15, COLUMN_Z + 0.24), (-math.pi / 4, 0, 0)):
        box((0.07, 0.035, 0.42), (0, 0, 0), ALU_DARK, bevel=0.004)
    rail(2.2, (0.1, GANTRY_Y + 0.06, -0.78))
    servo((0, GANTRY_Y + 0.08, COLUMN_Z - 0.2), (0, math.pi, 0))
    chain(1.2, (-0.03, GANTRY_Y + 0.18, -1.3))

with node("gantry_carriage"):
    box((0.28, 0.22, 0.24), (0, GANTRY_Y + 0.07, 0), ALU_DARK, bevel=0.01)
    for x in (-0.11, 0.11):
        for y in (0, 0.14):
            bolt((x, GANTRY_Y + y, 0.12), r=0.008)
    # pneumatic cylinder with end caps and tie rods (its rod is in the JSX)
    cyl((0, GANTRY_Y + 0.02, 0), (0, GANTRY_Y - 0.32, 0), 0.05, ALU, segments=32)
    for y in (GANTRY_Y + 0.0, GANTRY_Y - 0.3):
        box((0.125, 0.03, 0.125), (0, y, 0), ALU_DARK, bevel=0.004)
    for x in (-0.05, 0.05):
        for z in (-0.05, 0.05):
            cyl((x, GANTRY_Y, z), (x, GANTRY_Y - 0.3, z), 0.005, STEEL, segments=8)
    cyl((0.06, GANTRY_Y - 0.28, 0), (0.08, GANTRY_Y - 0.28, 0), 0.007, BRASS, segments=6)
    cyl((0.06, GANTRY_Y - 0.02, 0), (0.08, GANTRY_Y - 0.02, 0), 0.007, BRASS, segments=6)

with node("gantry_head"):
    plate = box((0.36, 0.035, 0.24), (0, 0.085, 0), ALU, bevel=0.003)
    for x in (-0.05, 0.05):
        cut(plate, cyl((x, 0.05, 0.075), (x, 0.12, 0.075), 0.02, ALU, segments=24))
        cut(plate, cyl((x, 0.05, -0.075), (x, 0.12, -0.075), 0.02, ALU, segments=24))
    box((0.1, 0.06, 0.1), (0, 0.125, 0), ALU_DARK, bevel=0.005)
    for x in (-0.12, 0.12):
        for z in (-0.07, 0.07):
            cyl((x, 0.02, z), (x, 0.07, z), 0.008, STEEL, segments=12)
            cyl((x, 0.103, z), (x, 0.12, z), 0.01, BLUE, segments=12)

# --- machine frame -----------------------------------------------------------------------------------------------

with node("frame_base"):
    body_h = -0.06 - (FLOOR_Y + 0.12)
    body_y = FLOOR_Y + 0.12 + body_h / 2
    box((W + 0.1, 0.06, D + 0.1), (0, -0.03, ZC), PLATE, bevel=0.006)
    box((W - 0.1, body_h, D - 0.1), (0, body_y, ZC), CABINET, bevel=0.006)
    for x in (-5.1, -1.7, 1.7, 5.1):
        with at((x, body_y, Z_FRONT - 0.04)):
            box((3.2, body_h - 0.12, 0.02), (0, 0, 0), CABINET, bevel=0.005)
            box((3.1, body_h - 0.2, 0.004), (0, 0, 0.011), PANEL)
            box((0.03, 0.22, 0.03), (1.4, 0.05, 0.03), STEEL, bevel=0.006)
            cyl((1.4, -0.14, 0.01), (1.4, -0.14, 0.024), 0.018, ALU, segments=16)
            for i in range(4):
                box((0.6, 0.02, 0.01), (-0.9, -0.25 + i * 0.06, 0.012), SLOT, bevel=0.002)
            for y in (-0.3, 0.3):
                box((0.03, 0.08, 0.016), (-1.59, y, 0.01), ALU_DARK, bevel=0.002)
    for x in (-6.5, 0, 6.5):
        for z in (Z_BACK + 0.2, Z_FRONT - 0.2):
            with at((x, FLOOR_Y, z)):
                cyl((0, 0.02, 0), (0, 0.12, 0), 0.025, STEEL, segments=16)
                cyl((0, 0, 0), (0, 0.03, 0), 0.08, RUBBER, r2=0.07, segments=24, bevel=0.003)
                cyl((0, 0.05, 0), (0, 0.075, 0), 0.042, ALU, segments=6)
    # emergency stop box and collar (the mushroom head is in the JSX)
    with at((6.55, body_y + 0.25, Z_FRONT)):
        box((0.22, 0.22, 0.08), (0, 0, 0), YELLOW, bevel=0.01)
        cyl((0, 0, 0.035), (0, 0, 0.085), 0.045, ANODIZED, segments=24)
        cyl((0, 0, 0.04), (0, 0, 0.05), 0.085, ALU_DARK, segments=32, bevel=0.002)

with node("frame_posts"):
    for x in (-FRAME_X, -FRAME_X / 3, FRAME_X / 3, FRAME_X):
        profile((P, H, P), (x, H / 2, Z_BACK))
    for x in (-FRAME_X, FRAME_X):
        profile((P, H, P), (x, H / 2, Z_FRONT))
    for z in (Z_BACK, Z_FRONT):
        profile((W + P, P, P), (0, H, z))
    for x in (-FRAME_X, FRAME_X):
        profile((P, P, D), (x, H, ZC))
    profile((W + P, P, P), (0, 0.9, Z_BACK))
    # cast corner brackets where the top rails meet the posts
    for x in (-FRAME_X, FRAME_X):
        for z in (Z_BACK, Z_FRONT):
            box((0.1, 0.1, 0.1), (x, H - 0.1, z), ALU_DARK, bevel=0.008)

with node("frame_front_rail"):
    profile((W + P, P, P), (0, 0.9, Z_FRONT))

with node("hmi_pendant"):
    box((0.2, 0.012, 0.2), (0, 0.006, 0), ALU_DARK, bevel=0.003)
    profile((0.08, 1.55, 0.08), (0, 0.775, 0), ALU_DARK)
    profile((0.08, 0.08, 0.4), (0, 1.55, -0.16), ALU_DARK)
    cyl((0, 1.5, 0.03), (0, 1.6, 0.03), 0.05, ALU, segments=24, bevel=0.003)
    with at((0, 1.55, 0.05), (-0.25, -0.3, 0)):
        box((0.62, 0.46, 0.06), (0, 0, 0), ANODIZED, bevel=0.012)
        box((0.57, 0.4, 0.002), (0, 0, 0.03), SLOT)
        box((0.3, 0.2, 0.03), (0, 0, -0.04), ALU_DARK, bevel=0.005)

with node("signal_tower"):
    cyl((0, 0, 0), (0, 0.04, 0), 0.06, ANODIZED, segments=24, bevel=0.003)
    cyl((0, 0.03, 0), (0, 0.17, 0), 0.025, STEEL, segments=16)
    cyl((0, 0.71, 0), (0, 0.74, 0), 0.077, ANODIZED, r2=0.06, segments=24, bevel=0.003)

bpy.ops.object.select_all(action="DESELECT")
for obj in NODES:
    obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_animations=False)
print(f"exported {OUT}: {sum(len(n.data.polygons) for n in NODES)} faces, {len(NODES)} nodes")
