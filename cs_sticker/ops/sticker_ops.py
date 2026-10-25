# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Operators acting on already spawned stickers."""

import math

import bpy
from bpy.props import FloatProperty
from mathutils import Matrix

from .. import utils
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
            obj.matrix_world = obj.matrix_world @ Matrix.Rotation(self.angle, 4, "Z")
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
        sw = obj.modifiers.get(P.MOD_SHRINKWRAP)
        if sw is None:
            P.add_modifier_stack(obj, target, context.scene.cs_sticker_place,
                                 max(obj.dimensions.x, obj.dimensions.y))
        else:
            sw.target = target
        P.attach(obj, target, context.scene.cs_sticker_place.attach)
        return {"FINISHED"}


classes = (CSSTICKER_OT_rotate, CSSTICKER_OT_make_unique, CSSTICKER_OT_retarget)
