# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Small shared helpers: add-on id, paths, preference access, logging."""

import logging
import os

import bpy

# Package name as Blender sees it ("cs_sticker" for legacy installs,
# "bl_ext.<repo>.cs_sticker" for extensions). Used as AddonPreferences id.
ADDON_ID = __package__

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_LIBRARY_DIR = os.path.join(ADDON_DIR, "stickers", "core")
# Only present in personal builds (tools/build_zip.py --with-stickers).
BUNDLED_LIBRARY_DIR = os.path.join(ADDON_DIR, "stickers", "bundled")

# Custom property keys stored on spawned sticker objects.
PROP_STICKER_ID = "cs_sticker_id"
PROP_STICKER_FINISH = "cs_sticker_finish"

# Name of the material node that hosts the finish node group.
STICKER_NODE_NAME = "CS2_STICKER"

STICKER_COLLECTION_NAME = "CS Stickers"

log = logging.getLogger("cs_sticker")


def get_prefs():
    """Return the add-on preferences or None (e.g. when run from tests)."""
    addon = bpy.context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None


def user_library_dir():
    """Absolute user sticker path from the preferences, or '' if unset/invalid."""
    prefs = get_prefs()
    if prefs is None or not prefs.user_path:
        return ""
    path = bpy.path.abspath(prefs.user_path)
    return path if os.path.isdir(path) else ""


def is_sticker(obj):
    return obj is not None and PROP_STICKER_ID in obj


def sticker_collection(context):
    """Get (or create) the collection that holds all spawned stickers."""
    coll = bpy.data.collections.get(STICKER_COLLECTION_NAME)
    if coll is None:
        coll = bpy.data.collections.new(STICKER_COLLECTION_NAME)
    # Link to the scene root only if the user has not nested it elsewhere.
    if coll not in context.scene.collection.children_recursive:
        context.scene.collection.children.link(coll)
    return coll
