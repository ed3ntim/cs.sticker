# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Small shared helpers: add-on id, paths, preference access, logging."""

import logging
import os

import bpy

# Package name as Blender sees it ("cs_sticker" for legacy installs,
# "bl_ext.<repo>.cs_sticker" for extensions). Used as AddonPreferences id.
ADDON_ID = __package__
# Name of the module towards a host add-on (cs.blend), whatever the package path.
MODULE_ID = "cs_sticker"

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_LIBRARY_DIR = os.path.join(ADDON_DIR, "stickers", "core")
# Only present in personal builds (tools/build_zip.py --with-stickers).
BUNDLED_LIBRARY_DIR = os.path.join(ADDON_DIR, "stickers", "bundled")

# Custom property keys stored on spawned sticker objects.
PROP_STICKER_ID = "cs_sticker_id"
PROP_STICKER_FINISH = "cs_sticker_finish"
PROP_COLLECTION = "cs_sticker_collection"  # on the per-scene sticker collections
# In-material stickers (nodes/decal.py): the projector Empty holds its
# decal node group here.
PROP_DECAL_GROUP = "cs_sticker_decal_group"

# Name of the material node that hosts the finish node group.
STICKER_NODE_NAME = "CS2_STICKER"

STICKER_COLLECTION_NAME = "CS Stickers"

log = logging.getLogger("cs_sticker")


# CS2 wear masks: 0 outside the shape, inside > 0. Some masks (Katowice
# 2019, #14) have 4/255 outside instead. The shape is mask > floor + ~0.4 %.
MASK_SHAPE_GAIN = 128.0
MASK_FLOOR_MAX = 8.0 / 255.0


def mask_floor(red):
    """Background level of a wear mask: median of the four 4x4 corners of
    the red channel (2D numpy array). Masks whose shape reaches the corners
    have no background there, so levels above MASK_FLOOR_MAX count as 0."""
    import numpy as np
    k = 4
    corners = np.concatenate([red[:k, :k].ravel(), red[:k, -k:].ravel(),
                              red[-k:, :k].ravel(), red[-k:, -k:].ravel()])
    floor = float(np.median(corners)) if corners.size else 0.0
    return floor if 0.0 < floor <= MASK_FLOOR_MAX else 0.0


# Host add-on (cs.blend) when registered as its sub-module, else None.
# The host provides settings(module_id) and user_path(module_id, sub, create).
_host = None


def set_host(host):
    global _host
    _host = host


def get_host():
    return _host


def prefs():
    """The settings (preferences.CSSTICKER_PG_settings) or None, e.g. while
    not registered. Standalone they hang off the add-on preferences, in host
    mode the host keeps them."""
    if _host is not None:
        return _host.settings(MODULE_ID)
    addon = bpy.context.preferences.addons.get(ADDON_ID)
    return getattr(addon.preferences, "settings", None) if addon else None


# Name before 2.1, kept for scripts written against it.
get_prefs = prefs


def user_path(sub="", create=True):
    """Folder for the add-on's own user data (caches), or '' if there is
    none (legacy install without host)."""
    try:
        if _host is not None:
            return _host.user_path(MODULE_ID, sub, create=create) or ""
        getter = getattr(bpy.utils, "extension_path_user", None)
        if getter is not None and ADDON_ID.startswith("bl_ext."):
            return getter(ADDON_ID, path=sub, create=create)
    except (ValueError, RuntimeError, OSError):
        pass
    return ""


def user_library_dir():
    """Absolute user sticker path from the settings, or '' if unset/invalid."""
    settings = prefs()
    if settings is None or not settings.user_path:
        return ""
    path = bpy.path.abspath(settings.user_path)
    return path if os.path.isdir(path) else ""


def is_sticker(obj):
    return obj is not None and PROP_STICKER_ID in obj


def is_decal(obj):
    """Sticker drawn in the material of another mesh (projector Empty)."""
    return is_sticker(obj) and obj.get(PROP_DECAL_GROUP) is not None


def sticker_collection(context):
    """Get (or create) the collection that holds the stickers of this scene.

    Every scene gets its own: a collection linked into two scenes shows
    the same objects in both. Older files match by name."""
    scene = context.scene
    for coll in scene.collection.children_recursive:
        if PROP_COLLECTION in coll or coll.name == STICKER_COLLECTION_NAME:
            return coll
    coll = bpy.data.collections.new(STICKER_COLLECTION_NAME)
    coll[PROP_COLLECTION] = True
    scene.collection.children.link(coll)
    return coll
