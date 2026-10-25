# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Add-on preferences: user sticker library path."""

import bpy
from bpy.props import BoolProperty, StringProperty

from .utils import ADDON_ID


def _on_path_change(self, context):
    from .library import registry
    registry.refresh(context)


class CSSTICKER_AP_preferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    user_path: StringProperty(
        name="User Sticker Folder",
        description="Folder with additional stickers: Source2Viewer exports (PNG + optional .vmat), "
                    "drop folders with sticker.json, or a catalog.json. "
                    "First-level sub-folders become collections",
        subtype="DIR_PATH",
        update=_on_path_change,
    )
    include_incomplete: BoolProperty(
        name="List Incomplete Stickers", default=True,
        description="Also list stickers whose required textures are missing (shown with a warning icon)",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "user_path")
        row = layout.row(align=True)
        row.operator("cs_sticker.refresh_library", icon="FILE_REFRESH")
        row.operator("cs_sticker.open_user_folder", icon="FILEBROWSER")
        layout.prop(self, "include_incomplete")
        col = layout.column(align=True)
        col.label(text="Folder layout examples:", icon="INFO")
        col.label(text="  <folder>/<Capsule>/name.vmat + exported PNGs")
        col.label(text="  <folder>/<Capsule>/name_color.png, name_normal.png, ...")
        col.label(text="  <folder>/<Capsule>/<Sticker>/sticker.json")


def register():
    bpy.utils.register_class(CSSTICKER_AP_preferences)


def unregister():
    bpy.utils.unregister_class(CSSTICKER_AP_preferences)
