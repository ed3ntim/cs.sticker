# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Spawn operators: snap to the selected surface, or manual mode, and the
reset of the placement settings."""

import bpy
from bpy.props import EnumProperty, StringProperty
from mathutils import Vector

from .. import utils
from ..library import registry
from . import placement as P


def _resolve_sticker(op, context):
    """Sticker given by id property or the one selected in the library."""
    if op.sticker_id:
        return registry.get_catalog().get(op.sticker_id)
    return registry.selected_sticker(context)


def report_warnings(op, warnings, limit=3):
    for msg in warnings[:limit]:
        op.report({"WARNING"}, msg)
    if len(warnings) > limit:
        op.report({"WARNING"}, f"... and {len(warnings) - limit} more texture warnings (see console)")
    for msg in warnings:
        utils.log.warning(msg)


def select_only(context, obj):
    for o in context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


class CSSTICKER_OT_spawn(bpy.types.Operator):
    """Spawn the selected sticker on the selected mesh surface"""
    bl_idname = "cs_sticker.spawn"
    bl_label = "Spawn Sticker"
    bl_options = {"REGISTER", "UNDO"}

    sticker_id: StringProperty(name="Sticker ID", options={"SKIP_SAVE", "HIDDEN"})
    mode: EnumProperty(
        name="Mode",
        items=[
            ("SURFACE", "Snap to Surface",
             "Place at the point of the target surface closest to the 3D cursor, "
             "aligned to its normal, projected via Shrinkwrap and attached"),
            ("MANUAL", "Manual",
             "Create the plane and modifier stack at the 3D cursor for manual adjustment"),
        ],
        default="SURFACE",
    )

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    @classmethod
    def description(cls, context, props):
        if props.mode == "MANUAL":
            return ("Create the sticker plane with its modifier stack at the 3D cursor. "
                    "Shrinkwrap targets the selected mesh if there is one")
        return ("Place the sticker on the selected mesh at the point closest to the 3D cursor "
                "(tip: Shift+Right-click on the surface to set the cursor)")

    def execute(self, context):
        sticker = _resolve_sticker(self, context)
        if sticker is None:
            self.report({"ERROR"}, "No sticker selected in the library")
            return {"CANCELLED"}
        settings = context.scene.cs_sticker_place
        target = P.pick_target(context)

        if self.mode == "SURFACE":
            if target is None:
                self.report({"ERROR"}, "Select the mesh the sticker should go on")
                return {"CANCELLED"}
            hit = P.surface_hit_from_point(context, target, context.scene.cursor.location)
            if hit is None:
                self.report({"ERROR"}, f"'{target.name}' has no surface to place on")
                return {"CANCELLED"}
            location, normal = hit
            matrix = P.orientation_matrix(location, normal, settings.rotation, settings.align_up)
            obj, warnings = P.create_sticker_object(context, sticker, settings, target, matrix)
            P.attach(obj, target, settings.attach)
        else:
            matrix = P.orientation_matrix(
                context.scene.cursor.location,
                context.scene.cursor.matrix.to_3x3() @ Vector((0, 0, 1)),
                settings.rotation, settings.align_up)
            obj, warnings = P.create_sticker_object(context, sticker, settings, target, matrix)

        select_only(context, obj)
        report_warnings(self, warnings)
        if not warnings:
            self.report({"INFO"}, f"Spawned '{sticker.name}' ({P.finish_label(sticker.finish)})")
        return {"FINISHED"}


class CSSTICKER_OT_reset_placement(bpy.types.Operator):
    """Restore the default placement settings (size, subdivisions, offset, ...)"""
    bl_idname = "cs_sticker.reset_placement"
    bl_label = "Reset to Defaults"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.cs_sticker_place
        for prop in settings.bl_rna.properties:
            if prop.identifier != "rna_type" and not prop.is_readonly:
                settings.property_unset(prop.identifier)
        return {"FINISHED"}


classes = (CSSTICKER_OT_spawn, CSSTICKER_OT_reset_placement)
