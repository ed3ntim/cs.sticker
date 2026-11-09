# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Operators acting on already spawned stickers, and the handler that keeps
in-material stickers consistent with their projectors."""

import math

import bpy
from bpy.app.handlers import persistent
from bpy.props import FloatProperty
from mathutils import Matrix

from .. import utils
from ..nodes import decal as D
from . import placement as P


def _active_sticker(context):
    obj = context.active_object
    return obj if utils.is_sticker(obj) else None


class CSSTICKER_OT_rotate(bpy.types.Operator):
    """Rotate the active sticker around its own normal"""
    bl_idname = "cs_sticker.rotate"
    bl_label = "Rotate Sticker"
    bl_options = {"REGISTER", "UNDO"}

    angle: FloatProperty(name="Angle", default=math.radians(15), subtype="ANGLE")

    @classmethod
    def poll(cls, context):
        return _active_sticker(context) is not None

    def execute(self, context):
        for obj in [o for o in context.selected_objects if utils.is_sticker(o)]:
            # Rotate before scaling: projectors are scaled non-uniformly.
            loc, rot, scale = obj.matrix_world.decompose()
            rot = rot.to_matrix().to_4x4() @ Matrix.Rotation(self.angle, 4, "Z")
            obj.matrix_world = Matrix.LocRotScale(loc, rot.to_quaternion(), scale)
        return {"FINISHED"}


class CSSTICKER_OT_make_unique(bpy.types.Operator):
    """Give the active sticker its own copy of the material"""
    bl_idname = "cs_sticker.make_unique"
    bl_label = "Make Material Unique"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = _active_sticker(context)
        return obj is not None and obj.active_material is not None and obj.active_material.users > 1

    def execute(self, context):
        obj = _active_sticker(context)
        obj.active_material = obj.active_material.copy()
        return {"FINISHED"}


class CSSTICKER_OT_retarget(bpy.types.Operator):
    """Project and attach the active sticker onto the other selected mesh"""
    bl_idname = "cs_sticker.retarget"
    bl_label = "Retarget to Selected"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_sticker(context) is not None

    def execute(self, context):
        obj = _active_sticker(context)
        targets = [o for o in context.selected_objects if o.type == "MESH" and not utils.is_sticker(o)]
        if not targets:
            self.report({"ERROR"}, "Also select the mesh to project onto")
            return {"CANCELLED"}
        target = targets[0]
        if utils.is_decal(obj):
            P.retarget_decal(obj, target)
        else:
            sw = obj.modifiers.get(P.MOD_SHRINKWRAP)
            if sw is None:
                P.add_modifier_stack(obj, target, context.scene.cs_sticker_place,
                                     max(obj.dimensions.x, obj.dimensions.y))
            else:
                P.set_target(obj, target)
        P.attach(obj, target, context.scene.cs_sticker_place.attach)
        return {"FINISHED"}


class CSSTICKER_OT_remove_decal(bpy.types.Operator):
    """Remove the active in-material sticker: its projector and its nodes in the target materials"""
    bl_idname = "cs_sticker.remove_decal"
    bl_label = "Remove Sticker"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return utils.is_decal(context.active_object)

    def execute(self, context):
        for obj in [o for o in context.selected_objects if utils.is_decal(o)]:
            tree = P.decal_group(obj)
            bpy.data.objects.remove(obj, do_unlink=True)
            if tree is not None:
                D.remove(tree)
        return {"FINISHED"}


classes = (CSSTICKER_OT_rotate, CSSTICKER_OT_make_unique, CSSTICKER_OT_retarget,
           CSSTICKER_OT_remove_decal)


# ---------------------------------------------------------------------------
# Keep in-material stickers consistent
# ---------------------------------------------------------------------------

def own_group(obj):
    """A duplicated projector still points at the original's decal group:
    give it a copy of its own in the same materials. Returns True if done."""
    tree = P.decal_group(obj)
    if tree is None or D.projector_of(tree) in (obj, None):
        return False
    mats = D.materials_with(tree)
    copy = tree.copy()
    D.set_projector(copy, obj)
    obj[utils.PROP_DECAL_GROUP] = copy
    for mat in mats:
        D.insert(mat, copy, label=f"Sticker: {obj.name.removeprefix('CS2 ')}")
    return True


_busy = [False]


def sync(depsgraph=None):
    """Remove decal groups of deleted projectors, split duplicated ones."""
    if _busy[0]:
        return
    _busy[0] = True
    try:
        if depsgraph is not None:
            for update in depsgraph.updates:
                obj = update.id.original if isinstance(update.id, bpy.types.Object) else None
                if obj is not None and utils.is_decal(obj):
                    own_group(obj)
        D.remove_orphans()
    finally:
        _busy[0] = False


@persistent
def _on_depsgraph_update(scene, depsgraph):
    if any(D.is_decal_group(t) for t in bpy.data.node_groups):
        sync(depsgraph)


def register():
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)


def unregister():
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
