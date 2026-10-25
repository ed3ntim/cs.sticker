# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Geometry side of sticker placement: plane creation, the modifier stack
(Subdivision -> Shrinkwrap project -> Clip), orientation and attachment.

Projection works like a decal: the plane sits slightly above the surface
(LIFT) and is projected inward only, so it lands on the outermost surface
(over levers and plates, not under them). Points that hit nothing keep their
lifted height; the Clip node group marks them and the material hides them,
so a sticker never floats past the edge of the target."""

import bpy
from mathutils import Matrix, Vector

from .. import utils
from ..library import finishes as F
from ..nodes import material as M
from ..nodes.builder import find_socket

MOD_SUBDIV = "CS Subdivision"
MOD_SHRINKWRAP = "CS Shrinkwrap"
MOD_CLIP = "CS Clip"
CLIP_GROUP = "CS2 Sticker Clip"
CLIP_VERSION = 2
LIFT_ATTRIBUTE = "cs_lift"  # point attribute: the plane's lifted local z
# Plane height above the surface point, as a factor of the sticker width.
# Must exceed the height of surface details under the sticker.
LIFT = 0.2
CONSTRAINT_NAME = "CS Attach"


def sticker_aspect(sticker):
    """Width / height of one sticker frame (lenticular strips hold N frames)."""
    w, h = M.image_size(sticker.base_path)
    if sticker.finish == "LENTICULAR" and F.ROLE_HOLOMASK not in sticker.textures:
        try:
            w /= max(1.0, float(sticker.params.get("frames", 2)))
        except (TypeError, ValueError):
            pass
    return max(w, 1) / max(h, 1)


def sticker_width(settings, target=None):
    """Sticker width in scene units: relative to the target's longest side
    (world space), or the absolute size without target / in absolute mode."""
    if settings.size_mode == "RELATIVE" and target is not None:
        longest = max(target.dimensions)
        if longest > 0:
            return longest * settings.size_relative / 100.0
    return settings.size


def surface_offset(settings, width):
    return width * settings.offset_factor / 100.0


def create_plane_mesh(name, width, height, lift=0.0):
    """Quad (centered, +Z normal, at local z = ``lift``) with a 'UVMap'
    layer covering 0..1."""
    hw, hh = width / 2.0, height / 2.0
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-hw, -hh, lift), (hw, -hh, lift), (hw, hh, lift), (-hw, hh, lift)],
                     [], [(0, 1, 2, 3)])
    attr = mesh.attributes.new(LIFT_ATTRIBUTE, "FLOAT", "POINT")
    attr.data.foreach_set("value", [lift] * 4)
    uv = mesh.uv_layers.new(name="UVMap")
    for loop, co in zip(uv.data, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop.uv = co
    mesh.update()
    return mesh


def clip_group():
    """Geometry nodes: store 'cs_unprojected' = 1 on points still at the
    lifted plane height (the projection missed the target). The lift comes
    from the mesh attribute LIFT_ATTRIBUTE, so the group needs no inputs."""
    tree = bpy.data.node_groups.get(CLIP_GROUP)
    if tree is not None and tree.get("cs_sticker_version") == CLIP_VERSION:
        return tree
    if tree is not None:
        tree.name = f"{CLIP_GROUP} (v{tree.get('cs_sticker_version', 0)})"
    tree = bpy.data.node_groups.new(CLIP_GROUP, "GeometryNodeTree")
    tree["cs_sticker_version"] = CLIP_VERSION
    iface = tree.interface
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes, links = tree.nodes, tree.links
    gin = nodes.new("NodeGroupInput")
    gout = nodes.new("NodeGroupOutput")
    pos = nodes.new("GeometryNodeInputPosition")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    cmp = nodes.new("FunctionNodeCompare")
    cmp.data_type = "FLOAT"
    cmp.operation = "GREATER_THAN"
    lift = nodes.new("GeometryNodeInputNamedAttribute")
    lift.data_type = "FLOAT"
    find_socket(lift.inputs, "Name").default_value = LIFT_ATTRIBUTE
    below = nodes.new("ShaderNodeMath")
    below.operation = "MULTIPLY"
    below.inputs[1].default_value = 0.99  # a hit lies clearly below the plane
    store = nodes.new("GeometryNodeStoreNamedAttribute")
    store.data_type = "FLOAT"
    store.domain = "POINT"
    for i, n in enumerate((gin, pos, lift, sep, below, cmp, store, gout)):
        n.location = (i * 200 - 700, 0)
    links.new(pos.outputs["Position"], sep.inputs[0])
    links.new(find_socket(lift.outputs, "Attribute"), below.inputs[0])
    links.new(sep.outputs["Z"], find_socket(cmp.inputs, "A"))
    links.new(below.outputs[0], find_socket(cmp.inputs, "B"))
    links.new(gin.outputs["Geometry"], store.inputs["Geometry"])
    find_socket(store.inputs, "Name").default_value = M.UNPROJECTED_ATTRIBUTE
    links.new(cmp.outputs["Result"], find_socket(store.inputs, "Value"))
    links.new(store.outputs["Geometry"], gout.inputs["Geometry"])
    return tree


def set_target(obj, target):
    """Point the projection at ``target`` (None = free plane, nothing clipped)."""
    sw = obj.modifiers.get(MOD_SHRINKWRAP)
    if sw is not None and sw.target != target:
        sw.target = target
    clip = obj.modifiers.get(MOD_CLIP)
    active = target is not None
    if clip is not None and clip.show_viewport != active:
        # Without a target nothing is projected, so nothing may be clipped.
        clip.show_viewport = clip.show_render = active


def project_distance(settings, width):
    """Shrinkwrap limit: from the lifted plane down past the surface."""
    if settings.project_limit <= 0:
        return 0.0
    return (LIFT + settings.project_limit) * width


def add_modifier_stack(obj, target, settings, size):
    """Simple subdivision so the plane can bend, then project onto ``target``
    along the sticker's local -Z (decal style), then clip misses."""
    sub = obj.modifiers.get(MOD_SUBDIV) or obj.modifiers.new(MOD_SUBDIV, "SUBSURF")
    sub.subdivision_type = "SIMPLE"
    sub.levels = settings.subdiv_levels
    sub.render_levels = settings.subdiv_levels
    sub.show_only_control_edges = True

    sw = obj.modifiers.get(MOD_SHRINKWRAP) or obj.modifiers.new(MOD_SHRINKWRAP, "SHRINKWRAP")
    sw.wrap_method = "PROJECT"
    sw.wrap_mode = "ABOVE_SURFACE"
    sw.use_project_z = True
    sw.use_project_x = sw.use_project_y = False
    sw.use_negative_direction = True
    sw.use_positive_direction = False
    sw.cull_face = "OFF"
    sw.offset = surface_offset(settings, size)
    sw.project_limit = project_distance(settings, size)

    clip = obj.modifiers.get(MOD_CLIP) or obj.modifiers.new(MOD_CLIP, "NODES")
    clip.node_group = clip_group()
    set_target(obj, target)
    return sub, sw


def orientation_matrix(location, normal, rotation=0.0, keep_upright=True):
    """World matrix placing the plane at ``location`` facing ``normal``.

    With ``keep_upright`` the sticker's +Y points as close to world +Z as the
    surface allows (on floors/ceilings world +Y is used instead)."""
    z = Vector(normal).normalized()
    if z.length < 1e-6:
        z = Vector((0, 0, 1))
    up = Vector((0, 0, 1)) if keep_upright else Vector((0, 1, 0))
    if abs(z.dot(up)) > 0.999:
        up = Vector((0, 1, 0))
    y = (up - z * up.dot(z)).normalized()
    x = y.cross(z).normalized()
    basis = Matrix((x, y, z)).transposed().to_4x4()
    basis = basis @ Matrix.Rotation(rotation, 4, "Z")
    basis.translation = location
    return basis


def attach(obj, target, mode):
    """Parent or constrain ``obj`` to ``target`` without moving it."""
    for con in [c for c in obj.constraints if c.name == CONSTRAINT_NAME]:
        obj.constraints.remove(con)
    world = obj.matrix_world.copy()
    obj.parent = None
    if target is None or mode == "NONE":
        obj.matrix_world = world
        return
    if mode == "PARENT":
        obj.parent = target
        obj.matrix_parent_inverse = target.matrix_world.inverted()
        obj.matrix_world = world
    elif mode == "CONSTRAINT":
        con = obj.constraints.new("CHILD_OF")
        con.name = CONSTRAINT_NAME
        con.target = target
        con.inverse_matrix = target.matrix_world.inverted()
        obj.matrix_world = world


def create_sticker_object(context, sticker, settings, target=None, matrix=None):
    """Create a sticker object with material and modifier stack.

    Returns (object, warnings). ``matrix`` defaults to the 3D cursor."""
    aspect = sticker_aspect(sticker)
    width = sticker_width(settings, target)
    height = width / aspect
    mesh = create_plane_mesh(f"CS2 {sticker.name}", width, height, LIFT * width)
    obj = bpy.data.objects.new(f"CS2 {sticker.name}", mesh)
    utils.sticker_collection(context).objects.link(obj)

    mat, warnings = M.build_material(sticker, unique=settings.unique_material)
    mesh.materials.append(mat)

    obj[utils.PROP_STICKER_ID] = sticker.id
    obj[utils.PROP_STICKER_FINISH] = sticker.finish
    if hasattr(obj, "visible_shadow"):
        # Thin decal: its own shadow on the surface only adds acne.
        obj.visible_shadow = False

    if matrix is None:
        matrix = context.scene.cursor.matrix.copy()
    obj.matrix_world = matrix
    add_modifier_stack(obj, target, settings, max(width, height))
    return obj, warnings


def surface_hit_from_point(context, target, point):
    """Closest point + normal on the evaluated ``target`` to a world point."""
    depsgraph = context.evaluated_depsgraph_get()
    eval_obj = target.evaluated_get(depsgraph)
    inv = target.matrix_world.inverted()
    ok, loc, nrm, _ = eval_obj.closest_point_on_mesh(inv @ point)
    if not ok:
        return None
    world_loc = target.matrix_world @ loc
    world_nrm = (target.matrix_world.inverted().transposed().to_3x3() @ nrm).normalized()
    return world_loc, world_nrm


def raycast_surfaces(context, origin, direction, candidates):
    """Nearest hit among ``candidates``: (object, location, normal) or None."""
    depsgraph = context.evaluated_depsgraph_get()
    best = None
    for obj in candidates:
        eval_obj = obj.evaluated_get(depsgraph)
        inv = obj.matrix_world.inverted()
        o = inv @ origin
        d = (inv.to_3x3() @ direction).normalized()
        ok, loc, nrm, _ = eval_obj.ray_cast(o, d)
        if not ok:
            continue
        world_loc = obj.matrix_world @ loc
        dist = (world_loc - origin).length
        if best is None or dist < best[0]:
            world_nrm = (obj.matrix_world.inverted().transposed().to_3x3() @ nrm).normalized()
            best = (dist, obj, world_loc, world_nrm)
    return best[1:] if best else None


def surface_candidates(context):
    """Meshes a sticker can land on: selected ones if any, else all visible."""
    def ok(o):
        return o.type == "MESH" and not utils.is_sticker(o) and o.visible_get()
    selected = [o for o in context.selected_objects if ok(o)]
    return selected or [o for o in context.visible_objects if ok(o)]


def pick_target(context):
    """Active mesh (non-sticker) or first selected one."""
    obj = context.active_object
    if obj and obj.type == "MESH" and not utils.is_sticker(obj) and obj.select_get():
        return obj
    for o in context.selected_objects:
        if o.type == "MESH" and not utils.is_sticker(o):
            return o
    return None


def finish_label(finish_id):
    return F.FINISHES.get(finish_id, F.FINISHES[F.DEFAULT_FINISH]).label
