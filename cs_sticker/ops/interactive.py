# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Interactive placement: the selected sticker follows the mouse over mesh
surfaces as a live preview, wheel rotates, Ctrl+wheel scales, click places."""

import math

import bpy
from bpy_extras import view3d_utils
from mathutils import Matrix

from ..library import registry
from . import placement as P
from .spawn import report_warnings, select_only

HELP = ("LMB: place  |  Shift+LMB: place & continue  |  Wheel: rotate (Shift: fine)  |  "
        "Ctrl+Wheel: scale  |  F: flip upright  |  RMB/Esc: finish/cancel")

# Events that should still reach the viewport (navigation).
_PASS_THROUGH = {
    "MIDDLEMOUSE", "TRACKPADPAN", "TRACKPADZOOM", "MOUSEROTATE", "MOUSESMARTZOOM",
    "NDOF_MOTION", "NUMPAD_0", "NUMPAD_1", "NUMPAD_2", "NUMPAD_3", "NUMPAD_4",
    "NUMPAD_5", "NUMPAD_6", "NUMPAD_7", "NUMPAD_8", "NUMPAD_9", "NUMPAD_PERIOD",
}


def _remove_object(obj):
    mesh = obj.data
    mats = [m for m in mesh.materials if m] if mesh else []
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)
    for m in mats:
        if m.users == 0:
            bpy.data.materials.remove(m)


class CSSTICKER_OT_place_interactive(bpy.types.Operator):
    """Move the selected sticker over surfaces with a live preview and click to place it"""
    bl_idname = "cs_sticker.place_interactive"
    bl_label = "Place Interactively"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (context.mode == "OBJECT" and context.area is not None
                and context.area.type == "VIEW_3D")

    # -- lifecycle -------------------------------------------------------------

    def invoke(self, context, event):
        self.sticker = registry.selected_sticker(context)
        if self.sticker is None:
            self.report({"ERROR"}, "No sticker selected in the library")
            return {"CANCELLED"}
        settings = context.scene.cs_sticker_place
        self.rotation = settings.rotation
        self.scale = 1.0
        self.upright = settings.align_up
        self.region = context.region
        self.rv3d = context.region_data
        self.candidates = P.surface_candidates(context)
        if not self.candidates:
            self.report({"ERROR"}, "No visible mesh surface to place on")
            return {"CANCELLED"}
        self.placed = []
        self.warnings = []
        self.ghost = None
        self.hit = None
        self._new_ghost(context)
        self._update(context, event)
        context.window_manager.modal_handler_add(self)
        context.area.header_text_set(HELP)
        return {"RUNNING_MODAL"}

    def _new_ghost(self, context):
        settings = context.scene.cs_sticker_place
        obj, warnings = P.create_sticker_object(context, self.sticker, settings)
        self.warnings += warnings
        # Keep the preview out of selection and raycasts until placed.
        obj.hide_select = True
        self.ghost = obj
        self.base_size = P.sticker_width(settings)  # size the ghost was built with

    def _finish(self, context):
        context.area.header_text_set(None)

    # -- modal -------------------------------------------------------------------

    def modal(self, context, event):
        context.area.tag_redraw()
        if event.type in _PASS_THROUGH:
            return {"PASS_THROUGH"}

        if event.type == "MOUSEMOVE":
            self._update(context, event)
        elif event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            sign = 1 if event.type == "WHEELUPMOUSE" else -1
            if event.ctrl:
                self.scale *= 1.1 ** sign
            else:
                self.rotation += math.radians(5 if event.shift else 15) * sign
            self._apply(context)
        elif event.type == "F" and event.value == "PRESS":
            self.upright = not self.upright
            self._apply(context)
        elif event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.hit is None:
                self.report({"WARNING"}, "Not over a surface")
                return {"RUNNING_MODAL"}
            self._place(context)
            if event.shift:
                self._new_ghost(context)
                self._apply(context)
                return {"RUNNING_MODAL"}
            return self._done(context)
        elif event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            if self.ghost is not None:
                _remove_object(self.ghost)
                self.ghost = None
            if self.placed:
                return self._done(context)
            self._finish(context)
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}

    # -- helpers -------------------------------------------------------------------

    def _update(self, context, event):
        coord = (event.mouse_region_x, event.mouse_region_y)
        origin = view3d_utils.region_2d_to_origin_3d(self.region, self.rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(self.region, self.rv3d, coord)
        self.hit = P.raycast_surfaces(context, origin, direction, self.candidates)
        self._apply(context)

    def _apply(self, context):
        if self.ghost is None or self.hit is None:
            return
        target, location, normal = self.hit
        settings = context.scene.cs_sticker_place
        # Relative size follows the surface under the mouse.
        width = P.sticker_width(settings, target) * self.scale
        matrix = P.orientation_matrix(location, normal, self.rotation, self.upright)
        self.ghost.matrix_world = matrix @ Matrix.Scale(width / self.base_size, 4)
        sw = self.ghost.modifiers.get(P.MOD_SHRINKWRAP)
        if sw is not None:
            if sw.target != target:
                sw.target = target
            sw.offset = P.surface_offset(settings, width)
            if settings.project_limit > 0:
                sw.project_limit = settings.project_limit * width

    def _place(self, context):
        obj = self.ghost
        target = self.hit[0]
        obj.hide_select = False
        P.attach(obj, target, context.scene.cs_sticker_place.attach)
        self.placed.append(obj)
        self.ghost = None

    def _done(self, context):
        if self.ghost is not None:
            _remove_object(self.ghost)
            self.ghost = None
        self._finish(context)
        if self.placed:
            select_only(context, self.placed[-1])
        report_warnings(self, self.warnings)
        self.report({"INFO"}, f"Placed {len(self.placed)} sticker(s)")
        return {"FINISHED"}


classes = (CSSTICKER_OT_place_interactive,)
