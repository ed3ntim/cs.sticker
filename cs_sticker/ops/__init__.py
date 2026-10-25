# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Operators."""

if "spawn" in locals():
    import importlib

    for _mod in (placement, spawn, interactive, library_ops, sticker_ops):  # noqa: F821
        importlib.reload(_mod)

import bpy  # noqa: E402

from . import placement, spawn, interactive, library_ops, sticker_ops  # noqa: E402

classes = spawn.classes + interactive.classes + library_ops.classes + sticker_ops.classes


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
