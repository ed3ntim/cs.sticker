# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Blender glue for the catalog: the shared Catalog instance, preview icons
and syncing the WindowManager list mirror."""

import os
import time

import bpy
import bpy.utils.previews
from bpy.app.handlers import persistent

from .. import properties, utils
from . import catalog as C
from . import thumbs

_catalog = C.Catalog()
_previews = None  # bpy.utils.previews collection, keyed by sticker id
_thumb_queue = []  # stickers whose composed thumbnail is not cached yet
_THUMB_PREFIX = "thumb:"
_loaded = False

# The UI list mirrors only the filtered result: a full CS2 library has
# 11k+ stickers and filling a CollectionProperty that large takes seconds.
MAX_LIST_ITEMS = 500
_match_count = 0  # stickers matching the current filter (may exceed the list)


def get_catalog():
    return _catalog


def refresh(context=None):
    """Reload core + bundled + user stickers and rebuild the UI list."""
    global _loaded
    context = context or bpy.context
    _catalog.load(utils.CORE_LIBRARY_DIR, utils.user_library_dir(), utils.BUNDLED_LIBRARY_DIR)
    _loaded = True
    properties.set_collection_items(_catalog.collections())
    _clear_previews()
    wm = context.window_manager
    if wm is not None:
        sync_items(wm.cs_sticker)
    for msg in _catalog.report.warnings:
        utils.log.warning(msg)
    return _catalog


def _filtered(state):
    prefs = utils.get_prefs()
    include_incomplete = prefs.include_incomplete if prefs else True
    collection = "" if state.filter_collection == "ALL" else state.filter_collection
    finish = "" if state.filter_finish == "ALL" else state.filter_finish
    for s in _catalog.filter(state.search, collection, finish):
        missing = bool(s.missing_required())
        if missing and not include_incomplete:
            continue
        yield s, missing


def match_count():
    return _match_count


def sync_items(state):
    """Copy the filtered catalog entries (at most MAX_LIST_ITEMS) into the
    CollectionProperty shown by the UIList."""
    global _match_count
    selected = selected_id(state)
    state.items.clear()
    _match_count = 0
    for s, missing in _filtered(state):
        _match_count += 1
        if _match_count > MAX_LIST_ITEMS:
            continue
        item = state.items.add()
        item.name = s.name
        item.sticker_id = s.id
        item.collection = s.collection
        item.finish = s.finish
        item.source = s.source
        item.has_missing = missing

    # Restore previous selection if it still exists.
    for i, item in enumerate(state.items):
        if item.sticker_id == selected:
            state["index"] = i  # bypass update callback
            break
    else:
        state["index"] = 0
    # The collection enum may now point to a removed name.
    if state.get("filter_collection", 0) >= len(properties._collection_items):
        state["filter_collection"] = 0


def selected_id(state):
    if 0 <= state.index < len(state.items):
        return state.items[state.index].sticker_id
    return ""


def selected_sticker(context):
    return _catalog.get(selected_id(context.window_manager.cs_sticker))


def on_filter_changed(state):
    """Search / collection / finish changed: rebuild the filtered list."""
    sync_items(state)


def on_selection_changed(state, context):
    # Previews load lazily; touching the icon here starts loading early.
    s = _catalog.get(selected_id(state))
    if s:
        preview_icon(s)


# ---------------------------------------------------------------------------
# Previews
# ---------------------------------------------------------------------------

def _clear_previews():
    global _previews
    _thumb_queue.clear()
    if _previews is not None:
        _previews.clear()


def _load_preview(key, path):
    if key not in _previews:
        try:
            _previews.load(key, path, "IMAGE")
        except (OSError, KeyError, RuntimeError):
            return 0
    return _previews[key].icon_id


def preview_icon(sticker):
    """icon_id for a sticker (0 if unavailable).

    Prefers the composed thumbnail (cut out, finish hint). While that is not
    cached yet, the plain base texture is shown and the thumbnail is queued:
    building it creates images, which draw callbacks may not do."""
    if _previews is None or sticker is None or not sticker.base_path:
        return 0
    key = _THUMB_PREFIX + sticker.id
    if key in _previews:
        return _previews[key].icon_id
    path = thumbs.cache_path(sticker)
    if os.path.isfile(path):
        return _load_preview(key, path)
    if sticker not in _thumb_queue:
        _thumb_queue.append(sticker)
        if not bpy.app.timers.is_registered(_build_thumbs):
            bpy.app.timers.register(_build_thumbs, first_interval=0.05)
    return _load_preview(sticker.id, sticker.base_path)


def _build_thumbs():
    """Timer: build queued thumbnails for ~50 ms per tick."""
    start = time.perf_counter()
    while _thumb_queue and time.perf_counter() - start < 0.05:
        sticker = _thumb_queue.pop(0)
        try:
            thumbs.build(sticker)
        except Exception as exc:  # a broken texture must not stop the queue
            utils.log.warning("cs.sticker: thumbnail for %s failed: %s", sticker.id, exc)
    for window in getattr(bpy.context.window_manager, "windows", []):
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()
    return 0.02 if _thumb_queue else None


# ---------------------------------------------------------------------------
# Handlers / registration
# ---------------------------------------------------------------------------

@persistent
def _on_load_post(_dummy):
    # The WindowManager is replaced when a file is loaded: refill the list
    # from the catalog in memory, no need to rescan the disk.
    if _loaded:
        sync_items(bpy.context.window_manager.cs_sticker)
    else:
        refresh(bpy.context)


def _deferred_refresh():
    try:
        refresh(bpy.context)
    except Exception as exc:  # never let a timer raise
        utils.log.error("cs.sticker: library refresh failed: %s", exc)
    return None


def register():
    global _previews
    _previews = bpy.utils.previews.new()
    bpy.app.handlers.load_post.append(_on_load_post)
    # bpy.context is restricted during register(); refresh right after.
    bpy.app.timers.register(_deferred_refresh, first_interval=0.1)


def unregister():
    global _previews
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    for timer in (_deferred_refresh, _build_thumbs):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
    _thumb_queue.clear()
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None
