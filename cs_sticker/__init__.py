# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""cs.sticker - spawn CS2 stickers onto mesh surfaces.

Works both as a Blender 4.5+ extension (blender_manifest.toml) and as a
legacy add-on (bl_info). Sub-packages:

    library/  sticker database: finish definitions, .vmat parsing, catalog
    nodes/    node group builders and material assembly per finish type
    ops/      operators: spawning, interactive placement, library actions
    ui/       sidebar panels and the sticker list
"""

bl_info = {
    "name": "cs.sticker",
    "author": "ed3n",
    "version": (1, 4, 0),
    "blender": (4, 5, 0),
    "location": "3D Viewport > Sidebar > cs.sticker",
    "description": "Spawn CS2 stickers onto mesh surfaces with finish-accurate "
                   "materials (Paper, Glitter, Holo, Foil, Gold, Lenticular, Embroidered)",
    "category": "Object",
    "support": "COMMUNITY",
}

# Support "Reload Scripts": re-import submodules if already loaded.
if "bpy" in locals():
    import importlib

    for _mod in (utils, preferences, properties, library, nodes, ops, ui):  # noqa: F821
        importlib.reload(_mod)

import bpy  # noqa: E402

from . import utils, preferences, properties, library, nodes, ops, ui  # noqa: E402

# Registration order matters: property groups before anything that points to them.
_modules = (preferences, properties, library, ops, ui)


def register():
    for mod in _modules:
        mod.register()


def unregister():
    for mod in reversed(_modules):
        mod.unregister()
