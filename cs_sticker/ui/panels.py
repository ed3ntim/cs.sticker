# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""3D Viewport sidebar panels (N-panel, tab "cs.sticker")."""

import math

import bpy

from .. import utils
from ..library import finishes as F
from ..library import registry
from ..nodes import decal as D
from ..nodes import material as M
from ..ops import placement as P


class _Base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "cs.sticker"


class CSSTICKER_PT_main(_Base, bpy.types.Panel):
    bl_label = "cs.sticker"
    bl_idname = "CSSTICKER_PT_main"

    def draw(self, context):
        cat = registry.get_catalog()
        row = self.layout.row()
        row.label(text=f"{len(cat.stickers)} stickers in {len(cat.collections())} collections",
                  icon="ASSET_MANAGER")
        row.operator("cs_sticker.refresh_library", text="", icon="FILE_REFRESH")


class CSSTICKER_PT_library(_Base, bpy.types.Panel):
    bl_label = "Library"
    bl_parent_id = "CSSTICKER_PT_main"

    def draw(self, context):
        layout = self.layout
        state = context.window_manager.cs_sticker
        layout.prop(state, "search", text="", icon="VIEWZOOM")
        row = layout.row(align=True)
        row.prop(state, "filter_collection", text="")
        row.prop(state, "filter_finish", text="")
        layout.template_list("CSSTICKER_UL_stickers", "", state, "items", state, "index", rows=6)
        total = registry.match_count()
        if total > len(state.items):
            layout.label(text=f"Showing {len(state.items)} of {total}, refine the search", icon="INFO")

        row = layout.row(align=True)
        row.operator("cs_sticker.add_folder", icon="NEWFOLDER")
        row.operator("cs_sticker.open_user_folder", text="", icon="FILEBROWSER")
        if not utils.user_library_dir():
            layout.label(text="Set a user folder in Preferences for more stickers", icon="INFO")

        warnings = registry.get_catalog().report.warnings
        if warnings:
            box = layout.box()
            box.prop(state, "show_warnings", text=f"Load Warnings ({len(warnings)})",
                     icon="TRIA_DOWN" if state.show_warnings else "TRIA_RIGHT", emboss=False)
            if state.show_warnings:
                col = box.column(align=True)
                for msg in warnings[:20]:
                    col.label(text=msg, icon="ERROR")
                if len(warnings) > 20:
                    col.label(text=f"... {len(warnings) - 20} more in the console")


class CSSTICKER_PT_preview(_Base, bpy.types.Panel):
    bl_label = "Preview"
    bl_parent_id = "CSSTICKER_PT_main"

    def draw(self, context):
        layout = self.layout
        sticker = registry.selected_sticker(context)
        if sticker is None:
            layout.label(text="No sticker selected", icon="INFO")
            return
        icon_id = registry.preview_icon(sticker)
        if icon_id:
            layout.template_icon(icon_value=icon_id, scale=8.0)
        else:
            layout.label(text="No preview (base texture missing)", icon="ERROR")

        col = layout.column(align=True)
        finish = F.FINISHES.get(sticker.finish)
        col.label(text=sticker.name, icon="BOOKMARKS")
        col.label(text=sticker.collection, icon="OUTLINER_COLLECTION")
        col.label(text=f"{finish.label}: {finish.description}" if finish else sticker.finish,
                  icon=finish.icon if finish else "NONE")
        maps = ", ".join(sorted(r for r in sticker.textures))
        col.label(text=f"Maps: {maps or 'none'}", icon="TEXTURE")
        for role in sticker.missing_required():
            col.label(text=f"Missing required {role} map", icon="ERROR")
        for role in sticker.missing_files():
            if role not in sticker.missing_required():
                col.label(text=f"{role} file not found", icon="ERROR")


class CSSTICKER_PT_place(_Base, bpy.types.Panel):
    bl_label = "Placement"
    bl_parent_id = "CSSTICKER_PT_main"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.cs_sticker_place
        layout.use_property_split = True
        layout.use_property_decorate = False
        target = P.pick_target(context)
        in_material = settings.method == "MATERIAL"
        layout.prop(settings, "method", expand=True)
        layout.prop(settings, "size_mode", expand=True)
        col = layout.column(align=True)
        if settings.size_mode == "RELATIVE":
            col.prop(settings, "size_relative")
            if target is not None:
                width = P.sticker_width(settings, target)
                col.label(text=f"= {width:.4g} units on {target.name}", icon="DRIVER_DISTANCE")
        else:
            col.prop(settings, "size")
        col.prop(settings, "rotation")
        col = layout.column(align=True)
        mesh_only = col.column(align=True)
        mesh_only.active = not in_material
        mesh_only.prop(settings, "subdiv_levels")
        mesh_only.prop(settings, "offset_factor")
        col.prop(settings, "project_limit")
        layout.prop(settings, "attach")
        layout.prop(settings, "align_up")
        row = layout.row()
        row.active = not in_material
        row.prop(settings, "unique_material")
        row = layout.row()
        row.alignment = "RIGHT"
        row.operator("cs_sticker.reset_placement", icon="LOOP_BACK")

        layout.use_property_split = False
        has_sticker = registry.selected_sticker(context) is not None
        col = layout.column(align=True)
        col.scale_y = 1.4
        col.enabled = has_sticker
        col.operator("cs_sticker.place_interactive", icon="RESTRICT_SELECT_OFF")
        sub = col.row(align=True)
        sub.enabled = target is not None
        sub.operator("cs_sticker.spawn", text="Spawn Sticker", icon="SNAP_FACE").mode = "SURFACE"
        sub = col.row(align=True)
        sub.enabled = target is not None or not in_material
        sub.operator("cs_sticker.spawn", text="Manual (at Cursor)",
                     icon="CUBE" if in_material else "MESH_PLANE").mode = "MANUAL"
        if target is None:
            layout.label(text="Select a mesh to snap onto", icon="INFO")
        else:
            layout.label(text=f"Target: {target.name}", icon="OBJECT_DATA")
            if in_material:
                mats = D.target_materials(target, create=False)
                shared = [m.name for m in mats if m.users > 1]
                if not mats:
                    layout.label(text="No material yet, one will be added", icon="INFO")
                elif shared:
                    layout.label(text=f"Shared material: {shared[0]}", icon="ERROR")
                    layout.label(text="Meshes using it show the sticker inside the box too")


class CSSTICKER_PT_active(_Base, bpy.types.Panel):
    bl_label = "Active Sticker"
    bl_parent_id = "CSSTICKER_PT_main"

    @classmethod
    def poll(cls, context):
        return utils.is_sticker(context.active_object)

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        layout.label(text=obj.name, icon="OBJECT_DATA")

        row = layout.row(align=True)
        row.label(text="Rotate")
        row.operator("cs_sticker.rotate", text="-15°").angle = -math.radians(15)
        row.operator("cs_sticker.rotate", text="+15°").angle = math.radians(15)
        row.operator("cs_sticker.rotate", text="90°").angle = math.radians(90)
        layout.prop(obj, "scale", text="Scale")

        if utils.is_decal(obj):
            self._draw_decal(context, obj)
            return

        col = layout.column(align=True)
        sub = obj.modifiers.get(P.MOD_SUBDIV)
        sw = obj.modifiers.get(P.MOD_SHRINKWRAP)
        if sub:
            col.prop(sub, "levels", text="Subdivisions")
        if sw:
            col.prop(sw, "target", text="Surface")
            col.prop(sw, "offset")
            col.prop(sw, "project_limit")
        row = layout.row(align=True)
        row.operator("cs_sticker.retarget", icon="SNAP_FACE")
        row.operator("cs_sticker.make_unique", icon="DUPLICATE")

        _draw_group_inputs(layout, M.sticker_group_node(obj.active_material))

    def _draw_decal(self, context, obj):
        layout = self.layout
        tree = P.decal_group(obj)
        mats = D.materials_with(tree) if tree is not None else []
        col = layout.column(align=True)
        if mats:
            for mat in mats:
                col.label(text=f"In material: {mat.name}", icon="MATERIAL")
        else:
            col.label(text="In no material, retarget it to a mesh", icon="ERROR")
        row = layout.row(align=True)
        row.operator("cs_sticker.retarget", icon="SNAP_FACE")
        row.operator("cs_sticker.remove_decal", icon="TRASH")
        _draw_group_inputs(layout, D.sticker_group_node(tree))


HIDDEN_INPUTS = ("Normal Color", "Holo Mask", "Use Wear Mask", "Scratches", "Wear Mask")


def _draw_group_inputs(layout, grp):
    """Tweakable values of a sticker's finish group."""
    if grp is None:
        return
    box = layout.box()
    box.label(text=grp.label or "Material", icon="NODE_MATERIAL")
    col = box.column(align=True)
    col.use_property_split = True
    col.use_property_decorate = False
    for sock in grp.inputs:
        # Only plain values the user can tweak; texture-driven ones are linked.
        if sock.is_linked or not hasattr(sock, "default_value") or sock.type == "SHADER":
            continue
        if sock.name in HIDDEN_INPUTS or sock.name.startswith("Decal") or sock.type == "VECTOR":
            continue
        col.prop(sock, "default_value", text=sock.name)


classes = (
    CSSTICKER_PT_main, CSSTICKER_PT_library, CSSTICKER_PT_preview,
    CSSTICKER_PT_place, CSSTICKER_PT_active,
)
