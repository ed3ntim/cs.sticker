# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Add-on preferences: user sticker library path, uninstall."""

import bpy
from bpy.props import BoolProperty, StringProperty

from .utils import ADDON_ID


def install_location(context):
    """Where the add-on is installed: ("EXTENSION", repo_index, pkg_id),
    ("SYSTEM", repo_index, pkg_id) for a read-only system repo, or
    ("LEGACY", None, module) for an add-on outside the extension system."""
    parts = ADDON_ID.split(".")
    if len(parts) == 3 and parts[0] == "bl_ext":
        for i, repo in enumerate(context.preferences.extensions.repos):
            if repo.module == parts[1]:
                kind = "SYSTEM" if getattr(repo, "source", "") == "SYSTEM" else "EXTENSION"
                return kind, i, parts[2]
        return None
    return "LEGACY", None, ADDON_ID


def _uninstall(location):
    """Run Blender's uninstall once our operator has returned: the add-on
    unregisters itself, so it must not happen inside its own operator."""
    kind, repo_index, pkg = location
    wm = bpy.context.window_manager
    window = wm.windows[0] if wm.windows else None
    with bpy.context.temp_override(window=window):
        if kind == "EXTENSION":
            bpy.ops.extensions.package_uninstall(repo_index=repo_index, pkg_id=pkg)
        else:
            bpy.ops.preferences.addon_remove(module=pkg)
    return None  # one-shot timer


class CSSTICKER_OT_uninstall(bpy.types.Operator):
    """Disable cs.sticker and delete it from disk. Stickers already placed
    in your files stay as they are"""
    bl_idname = "cs_sticker.uninstall"
    bl_label = "Uninstall cs.sticker"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        loc = install_location(context)
        return loc is not None and loc[0] != "SYSTEM"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self, event, title="Uninstall cs.sticker?",
            message="The add-on is disabled and its files are deleted.",
            confirm_text="Uninstall", icon="WARNING")

    def execute(self, context):
        location = install_location(context)
        bpy.app.timers.register(lambda: _uninstall(location), first_interval=0.1)
        return {"FINISHED"}


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

        layout.separator()
        row = layout.row()
        row.alert = True
        row.operator("cs_sticker.uninstall", icon="TRASH")
        loc = install_location(context)
        if loc is not None and loc[0] == "SYSTEM":
            layout.label(text="Installed in a system repository, remove it there.", icon="INFO")


def register():
    bpy.utils.register_class(CSSTICKER_OT_uninstall)
    bpy.utils.register_class(CSSTICKER_AP_preferences)


def unregister():
    bpy.utils.unregister_class(CSSTICKER_AP_preferences)
    bpy.utils.unregister_class(CSSTICKER_OT_uninstall)
