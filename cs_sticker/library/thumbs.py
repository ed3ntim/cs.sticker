# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Library thumbnails that look like the sticker, not like its color map.

CS2 color maps are square RGB images; the shape lives in the wear mask and
the finish in further maps. A thumbnail cuts the base out with that mask and
adds a cheap hint of the finish (holo spectrum, metal sheen, glitter).

Thumbnails are cached as PNG files. Building one needs bpy.data images,
which is not allowed while panels draw, so the registry queues missing
thumbnails and builds them from a timer (see registry.preview_icon).
"""

import hashlib
import zlib
import os
import tempfile

import bpy
import numpy as np

from .. import utils
from . import finishes as F

SIZE = 256
THUMB_VERSION = 1  # bump when the look changes, invalidates the cache


def cache_dir():
    path = ""
    getter = getattr(bpy.utils, "extension_path_user", None)
    if getter is not None and utils.ADDON_ID.startswith("bl_ext."):
        try:
            path = getter(utils.ADDON_ID, path="thumbs", create=True)
        except (ValueError, RuntimeError, OSError):
            path = ""
    if not path:
        path = os.path.join(tempfile.gettempdir(), "cs_sticker_thumbs")
    os.makedirs(path, exist_ok=True)
    return path


def cache_path(sticker):
    """Cache file for a sticker; the key changes when its maps change."""
    parts = [sticker.id, sticker.finish, str(THUMB_VERSION)]
    for role in sorted(sticker.textures):
        path = sticker.textures[role]
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            stamp = 0
        parts.append(f"{role}={path}@{stamp}")
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return os.path.join(cache_dir(), f"{digest}.png")


def _read(path, size=SIZE, data=False):
    """Image file -> float array (h, w, 4), resampled to ``size``."""
    if not path or not os.path.isfile(path):
        return None
    try:
        img = bpy.data.images.load(path, check_existing=False)
    except RuntimeError:
        return None
    try:
        if data:
            img.colorspace_settings.name = "Non-Color"
        w, h = size if isinstance(size, tuple) else (size, size)
        if tuple(img.size) != (w, h):
            img.scale(w, h)
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        return px.reshape(h, w, 4)
    finally:
        bpy.data.images.remove(img)


def _diagonal(n):
    y, x = np.mgrid[0:n, 0:n].astype(np.float32) / (n - 1)
    return x, y


def compose(sticker, size=SIZE):
    """RGBA float array (size, size, 4) for the sticker, rows bottom-up."""
    tex = sticker.textures
    base = _read(tex.get(F.ROLE_BASE), size)
    if base is None:
        return None
    rgb = base[..., :3].copy()
    mask = _read(tex.get(F.ROLE_WEARMASK), size, data=True)
    alpha = np.clip(mask[..., 0] * 128.0, 0.0, 1.0) if mask is not None else base[..., 3]
    x, y = _diagonal(size)
    finish = sticker.finish

    if finish in ("HOLO", "LENTICULAR"):
        holo = _read(tex.get(F.ROLE_HOLOMASK), size, data=True)
        if holo is not None:
            strength = holo[..., 0:1] * 0.75
            u = np.mod(holo[..., 1] + 0.35 * (x + y), 1.0)
            v = holo[..., 2]
            spec = _read(tex.get(F.ROLE_HOLOSPECTRUM), (256, 64))
            if spec is not None:
                ui = np.clip((u * 255).astype(int), 0, 255)
                vi = np.clip((v * 63).astype(int), 0, 63)
                color = spec[vi, ui, :3]
            else:  # procedural rainbow
                phase = u[..., None] * 6.2832 + np.array([0.0, 2.094, 4.189], dtype=np.float32)
                color = 0.5 + 0.5 * np.cos(phase)
            rgb = rgb * (1.0 - strength) + color * strength

    elif finish in ("FOIL", "GOLD"):
        metal = _read(tex.get(F.ROLE_METALNESS), size, data=True)
        m = metal[..., 0:1] if metal is not None else np.ones_like(rgb[..., :1])
        band = np.exp(-(((x - 0.6 * y) - 0.25) / 0.16) ** 2)[..., None]
        sheen = 0.8 + 0.7 * band
        rgb = rgb * (1.0 - m) + np.clip(rgb * sheen, 0.0, 1.0) * m

    elif finish == "GLITTER":
        glit = _read(tex.get(F.ROLE_GLITTER), size, data=True)
        g = glit[..., 0] if glit is not None else np.ones_like(alpha)
        rng = np.random.default_rng(zlib.crc32(sticker.id.encode("utf-8")))
        spark = (rng.random(alpha.shape) > 0.97).astype(np.float32) * g
        rgb = np.clip(rgb + spark[..., None] * 0.7, 0.0, 1.0)

    out = np.empty((size, size, 4), dtype=np.float32)
    out[..., :3] = rgb
    out[..., 3] = alpha
    return out


def build(sticker, path=None, size=SIZE):
    """Compose and write the cached thumbnail. Returns its path or ""."""
    pixels = compose(sticker, size)
    if pixels is None:
        return ""
    path = path or cache_path(sticker)
    img = bpy.data.images.new("cs_sticker_thumb", size, size, alpha=True)
    try:
        img.pixels.foreach_set(pixels.ravel())
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)
    return path
