# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Library operators: refresh, open the user folder, add a folder."""

import os
import shutil

import bpy
from bpy.props import StringProperty

from .. import utils
from ..library import registry


class CSSTICKER_OT_refresh_library(bpy.types.Operator):
    """Rescan the core set and the user sticker folder"""
    bl_idname = "cs_sticker.refresh_library"
    bl_label = "Refresh Library"

    def execute(self, context):
        cat = registry.refresh(context)
        n_warn = len(cat.report.warnings)
        msg = f"{len(cat.stickers)} stickers loaded"
        if n_warn:
            msg += f", {n_warn} warning(s) (see Library > Load Warnings)"
        self.report({"WARNING"} if n_warn else {"INFO"}, msg)
        return {"FINISHED"}


class CSSTICKER_OT_open_user_folder(bpy.types.Operator):
    """Open the user sticker folder in the system file browser"""
    bl_idname = "cs_sticker.open_user_folder"
    bl_label = "Open Folder"

    @classmethod
    def poll(cls, context):
        return bool(utils.user_library_dir())

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=utils.user_library_dir())
        return {"FINISHED"}


class CSSTICKER_OT_add_folder(bpy.types.Operator):
    """Copy a folder of exported stickers (PNG / .vmat / sticker.json) into the
    user sticker folder and refresh. The folder name becomes the collection"""
    bl_idname = "cs_sticker.add_folder"
    bl_label = "Add Sticker Folder"

    directory: StringProperty(subtype="DIR_PATH")
    filter_folder: bpy.props.BoolProperty(default=True, options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return bool(utils.user_library_dir())

    @classmethod
    def description(cls, context, props):
        if not utils.user_library_dir():
            return "Set a User Sticker Folder in the add-on preferences first"
        return cls.__doc__

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        src = os.path.normpath(bpy.path.abspath(self.directory))
        root = utils.user_library_dir()
        if not os.path.isdir(src):
            self.report({"ERROR"}, f"Not a folder: {src}")
            return {"CANCELLED"}
        if os.path.normcase(os.path.abspath(src)).startswith(os.path.normcase(os.path.abspath(root))):
            # Already inside the library: a refresh is all that's needed.
            registry.refresh(context)
            self.report({"INFO"}, "Folder is already in the library, refreshed")
            return {"FINISHED"}
        dst = os.path.join(root, os.path.basename(src))
        try:
            shutil.copytree(src, dst, dirs_exist_ok=True)
        except OSError as exc:
            self.report({"ERROR"}, f"Copy failed: {exc}")
            return {"CANCELLED"}
        cat = registry.refresh(context)
        self.report({"INFO"}, f"Added '{os.path.basename(src)}', {len(cat.stickers)} stickers in library")
        return {"FINISHED"}


classes = (CSSTICKER_OT_refresh_library, CSSTICKER_OT_open_user_folder, CSSTICKER_OT_add_folder)
