# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Node group builders and material assembly. Nothing to register: groups
are created on demand in bpy.data when a sticker is spawned."""

if "groups" in locals():
    import importlib

    for _mod in (builder, groups, material):  # noqa: F821
        importlib.reload(_mod)

from . import builder, groups, material  # noqa: E402
