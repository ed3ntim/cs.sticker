# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Geometry side of sticker placement: plane creation, the modifier stack
(Subdivision -> Shrinkwrap project), orientation and attachment."""

import bpy
from mathutils import Matrix, Vector

from .. import utils
from ..library import finishes as F
from ..nodes import material as M

MOD_SUBDIV = "CS Subdivision"
MOD_SHRINKWRAP = "CS Shrinkwrap"
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


def create_plane_mesh(name, width, height):
    """Unit quad (centered, +Z normal) with a 'UVMap' layer covering 0..1."""
    hw, hh = width / 2.0, height / 2.0
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-hw, -hh, 0), (hw, -hh, 0), (hw, hh, 0), (-hw, hh, 0)], [], [(0, 1, 2, 3)])
    uv = mesh.uv_layers.new(name="UVMap")
    for loop, co in zip(uv.data, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop.uv = co
    mesh.update()
    return mesh


def add_modifier_stack(obj, target, settings, size):
    """Simple subdivision so the plane can bend, then project onto ``target``
    along the sticker's local Z (both directions)."""
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
    sw.use_positive_direction = True
    sw.cull_face = "OFF"
    sw.offset = settings.offset
    sw.project_limit = settings.project_limit * size if settings.project_limit > 0 else 0.0
    sw.target = target
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
    width = settings.size
    height = settings.size / aspect
    mesh = create_plane_mesh(f"CS2 {sticker.name}", width, height)
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
