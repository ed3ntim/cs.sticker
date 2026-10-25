# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""User interface: sidebar panels and the sticker list."""

if "panels" in locals():
    import importlib

    for _mod in (lists, panels):  # noqa: F821
        importlib.reload(_mod)

import bpy  # noqa: E402

from . import lists, panels  # noqa: E402

classes = lists.classes + panels.classes


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
