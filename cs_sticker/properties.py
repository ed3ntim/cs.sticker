# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Property groups.

* ``WindowManager.cs_sticker``  runtime library state (list mirror, filters,
  selection). Not saved in .blend files, rebuilt from the catalog.
* ``Scene.cs_sticker_place``    placement settings, saved with the file.
"""

import math

import bpy
from bpy.props import (
    BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
    IntProperty, PointerProperty, StringProperty,
)

from .library import finishes as F

FINISH_FILTER_ITEMS = [("ALL", "All Finishes", "Show every finish type", "NONE", 0)] + [
    (f.id, f.label, f.description, f.icon, i + 1) for i, f in enumerate(F.FINISHES.values())
]

# Dynamic enum items must stay referenced from Python, otherwise Blender may
# read freed strings. The registry refreshes this list.
_collection_items = [("ALL", "All Collections", "")]


def set_collection_items(names):
    _collection_items[:] = [("ALL", "All Collections", "")] + [
        (n, n, f"Only stickers from {n}") for n in names
    ]


def _collection_enum(self, context):
    return _collection_items


def _on_filter_change(self, context):
    from .library import registry
    registry.on_filter_changed(self)


def _on_select(self, context):
    from .library import registry
    registry.on_selection_changed(self, context)


class CSSTICKER_PG_item(bpy.types.PropertyGroup):
    """Mirror of one catalog entry, displayed by the UIList."""
    # ``name`` (built in) holds the display name.
    sticker_id: StringProperty()
    collection: StringProperty()
    finish: StringProperty()
    source: StringProperty()
    has_missing: BoolProperty(description="Required textures are missing")


class CSSTICKER_PG_state(bpy.types.PropertyGroup):
    items: CollectionProperty(type=CSSTICKER_PG_item)
    index: IntProperty(name="Sticker", default=0, update=_on_select)

    search: StringProperty(
        name="Search", description="Filter by name, collection, finish or tag (all words must match)",
        options={"TEXTEDIT_UPDATE"}, update=_on_filter_change,
    )
    filter_collection: EnumProperty(
        name="Collection", description="Filter by collection / capsule",
        items=_collection_enum, update=_on_filter_change,
    )
    filter_finish: EnumProperty(
        name="Finish", description="Filter by finish type",
        items=FINISH_FILTER_ITEMS, default="ALL", update=_on_filter_change,
    )
    show_warnings: BoolProperty(name="Show Load Warnings", default=False)


ATTACH_ITEMS = [
    ("PARENT", "Parent", "Parent the sticker to the surface (keeps transform)"),
    ("CONSTRAINT", "Child Of", "Follow the surface through a Child Of constraint"),
    ("NONE", "None", "Leave the sticker unattached"),
]


SIZE_MODE_ITEMS = [
    ("RELATIVE", "Relative", "Sticker width as a percentage of the target's longest side. "
                             "Works for any scene scale (meters, Source units, ...)"),
    ("ABSOLUTE", "Absolute", "Sticker width in scene units"),
]


class CSSTICKER_PG_placement(bpy.types.PropertyGroup):
    size_mode: EnumProperty(name="Size Mode", items=SIZE_MODE_ITEMS, default="RELATIVE")
    size_relative: FloatProperty(
        name="Size", description="Sticker width as a percentage of the target's longest side. "
                                 "6.5 % matches CS2 stickers on rifles",
        default=6.5, min=0.01, soft_max=30.0, max=100.0, subtype="PERCENTAGE",
    )
    size: FloatProperty(
        name="Size", description="Sticker width in scene units (also used without a target)",
        default=0.1, min=0.0001, soft_max=10.0, unit="LENGTH",
    )
    rotation: FloatProperty(
        name="Rotation", description="Rotation around the surface normal",
        default=0.0, min=-2 * math.pi, max=2 * math.pi, subtype="ANGLE",
    )
    subdiv_levels: IntProperty(
        name="Subdivisions", description="Simple subdivision levels so the plane can bend to the surface",
        default=7, min=0, max=8,
    )
    offset_factor: FloatProperty(
        name="Offset", description="Distance above the surface as a percentage of the sticker width "
                                   "(prevents z-fighting). Increase it if parts of the sticker sink "
                                   "into curved, low-poly surfaces",
        default=1.0, min=0.0, soft_max=2.0, precision=2, subtype="PERCENTAGE",
    )
    project_limit: FloatProperty(
        name="Project Limit", description="Maximum projection distance as a factor of the sticker size "
                                          "(stops stickers wrapping onto far-away faces). 0 = unlimited",
        default=0.5, min=0.0, soft_max=4.0,
    )
    attach: EnumProperty(name="Attach", items=ATTACH_ITEMS, default="PARENT")
    align_up: BoolProperty(
        name="Keep Upright", default=True,
        description="Align the sticker's top edge with world up where possible",
    )
    unique_material: BoolProperty(
        name="Unique Material", default=True,
        description="Give each spawned sticker its own material (independent wear/strength)",
    )


classes = (CSSTICKER_PG_item, CSSTICKER_PG_state, CSSTICKER_PG_placement)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.cs_sticker = PointerProperty(type=CSSTICKER_PG_state)
    bpy.types.Scene.cs_sticker_place = PointerProperty(type=CSSTICKER_PG_placement)


def unregister():
    del bpy.types.Scene.cs_sticker_place
    del bpy.types.WindowManager.cs_sticker
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
