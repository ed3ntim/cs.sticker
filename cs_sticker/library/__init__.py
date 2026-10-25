# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Sticker database. finishes/vmat/catalog are pure Python; registry holds
the Blender-side state."""

if "registry" in locals():
    import importlib

    for _mod in (finishes, vmat, catalog, registry):  # noqa: F821
        importlib.reload(_mod)

from . import finishes, vmat, catalog, registry  # noqa: E402


def register():
    registry.register()


def unregister():
    registry.unregister()
