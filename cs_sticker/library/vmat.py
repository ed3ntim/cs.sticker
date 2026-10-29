# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Tolerant parser for Source 2 material files (.vmat) as exported by
Source2Viewer, plus texture-role detection from file names.

Valve does not publish the csgo_sticker.vfx parameter list, and exports come
in two syntaxes (legacy KeyValues ``Key "Value"`` and KV3 ``Key = "Value"``).
Instead of a strict grammar we collect every key/value pair and classify
texture keys by keyword. Pure Python (no bpy).
"""

import os
import re
from dataclasses import dataclass, field

from . import finishes as F

IMAGE_EXTENSIONS = (".png", ".tga", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".webp")

# key  "value"  |  key = "value"  |  key = 1.0  |  key 1
_PAIR_RE = re.compile(
    r'^\s*"?([A-Za-z_][\w.]*)"?\s*=?\s*(?:"([^"]*)"|([-+\w.\[\], ]+?))\s*,?\s*$'
)

# Keyword -> role. Order matters: more specific words first, so that
# "holomask" is not caught by "mask" and "holospectrum" not by "holo".
_ROLE_KEYWORDS = (
    (F.ROLE_WEARMASK, ("wearmask", "wear_mask")),
    (F.ROLE_SCRATCHES, ("stickerscratches", "scratches")),
    (F.ROLE_FLAKES, ("glitternormal",)),
    (F.ROLE_HOLOSPECTRUM, ("holospectrum", "holo_spectrum", "spectrum", "holowarp", "holo_warp", "warp")),
    (F.ROLE_HOLOMASK, ("holomask", "holo_mask", "holo")),
    (F.ROLE_GLITTER, ("glittermask", "glitter_mask", "glitter", "sparkle")),
    (F.ROLE_NORMAL, ("normalmap", "normal", "nrm", "bump")),
    (F.ROLE_ROUGHNESS, ("roughness", "rough", "gloss")),
    (F.ROLE_METALNESS, ("metalness", "metallic", "metal", "foilmask", "foil_mask")),
    (F.ROLE_BASE, ("color", "colour", "albedo", "basecolor", "base", "diffuse")),
)

# Keys that look like a role but are something else (backing AO).
_IGNORED_KEY_WORDS = ("ambientocclusion", "backing")

# Shared by all sticker layers, so it has no "Sticker0" suffix.
_LAYER_INDEPENDENT_ROLES = (F.ROLE_SCRATCHES,)

# CS2 sticker layer keys end with this (TextureColorSticker0, ...).
STICKER_LAYER_SUFFIX = "sticker0"

# Single tokens in exported file names that identify a role.
_ROLE_TOKENS = {
    "color": F.ROLE_BASE, "colour": F.ROLE_BASE, "albedo": F.ROLE_BASE,
    "basecolor": F.ROLE_BASE, "diffuse": F.ROLE_BASE, "base": F.ROLE_BASE,
    "normal": F.ROLE_NORMAL, "normalmap": F.ROLE_NORMAL, "nrm": F.ROLE_NORMAL,
    "holomask": F.ROLE_HOLOMASK,
    "holospectrum": F.ROLE_HOLOSPECTRUM, "spectrum": F.ROLE_HOLOSPECTRUM,
    "holowarp": F.ROLE_HOLOSPECTRUM, "warp": F.ROLE_HOLOSPECTRUM,
    "glitter": F.ROLE_GLITTER, "glittermask": F.ROLE_GLITTER,
    "roughness": F.ROLE_ROUGHNESS, "rough": F.ROLE_ROUGHNESS,
    "metalness": F.ROLE_METALNESS, "metal": F.ROLE_METALNESS,
}

# Tokens Source2Viewer appends to exported file names (source format, hash).
_NOISE_TOKENS = {"png", "psd", "tga", "jpg", "vtex", "c", "tex"}
_HASH_RE = re.compile(r"^[0-9a-f]{6,}$")


def tokenize(stem):
    return [t for t in re.split(r"[_\-\s.]+", stem.lower()) if t]


def role_from_key(key):
    """Classify a vmat key (e.g. 'TextureHoloMask', 'g_tColor') or None."""
    low = key.lower()
    # Strip common Source 2 prefixes so "g_tColor" -> "color".
    for prefix in ("g_t", "texture", "tex"):
        if low.startswith(prefix):
            low = low[len(prefix):]
            break
    low = low.strip("_")
    if any(w in low for w in _IGNORED_KEY_WORDS):
        return None
    for role, words in _ROLE_KEYWORDS:
        if any(w in low for w in words):
            return role
    return None


def split_texture_name(filename):
    """Split an exported texture file name into (sticker_stem, role).

    'crown_foil_normal_png_4f2a9c1b.png' -> ('crown_foil', 'normal')
    'howling_dawn.png'                   -> ('howling_dawn', 'base')
    """
    stem = os.path.splitext(os.path.basename(filename))[0]
    tokens = tokenize(stem)
    # Search from the right: the role token comes after the sticker name.
    for i in range(len(tokens) - 1, 0, -1):
        role = _ROLE_TOKENS.get(tokens[i])
        if role and all(t in _NOISE_TOKENS or _HASH_RE.match(t) for t in tokens[i + 1:]):
            return "_".join(tokens[:i]), role
    while len(tokens) > 1 and (tokens[-1] in _NOISE_TOKENS or _HASH_RE.match(tokens[-1])):
        tokens.pop()
    return "_".join(tokens), F.ROLE_BASE


@dataclass
class VmatInfo:
    path: str
    shader: str = ""
    params: dict = field(default_factory=dict)    # every scalar key/value
    textures: dict = field(default_factory=dict)  # role -> raw referenced path
    finish: str = ""


def _is_default_texture(value, role):
    """Engine defaults (flat normal, default masks) carry no sticker data.
    The default holo spectrum, scratches and glitter flakes are the
    exception: stickers use them as they are."""
    low = value.replace("\\", "/").lower()
    if not low.startswith("materials/default/"):
        return False
    return role not in (F.ROLE_HOLOSPECTRUM, F.ROLE_SCRATCHES, F.ROLE_FLAKES)


def parse_vmat_text(text, path=""):
    """Parse vmat source text into a VmatInfo (never raises on bad input).

    CS2 weapon stickers (csgo_weapon_sticker.vfx) describe two layers: the
    backing material (TextureColor, TextureNormal, ...) and the sticker
    itself (TextureColorSticker0, TextureHoloMaskSticker0, ...). When
    ``*Sticker0`` keys exist, only those are used.
    """
    info = VmatInfo(path=path)
    pairs = []
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line or line in ("{", "}", "[", "]"):
            continue
        m = _PAIR_RE.match(line)
        if not m:
            continue
        key = m.group(1)
        value = m.group(2) if m.group(2) is not None else (m.group(3) or "").strip()
        info.params.setdefault(key, value)
        if key.lower() == "shader":
            info.shader = value
        elif value.lower().endswith(IMAGE_EXTENSIONS + (".vtex", ".psd")):
            pairs.append((key, value))

    layered = any(k.lower().endswith(STICKER_LAYER_SUFFIX) for k, _ in pairs)
    for key, value in pairs:
        if layered and not key.lower().endswith(STICKER_LAYER_SUFFIX):
            role = role_from_key(key)
            if role not in _LAYER_INDEPENDENT_ROLES:
                continue
        else:
            role = role_from_key(key[: -len(STICKER_LAYER_SUFFIX)] if layered else key)
        if role and role not in info.textures and not _is_default_texture(value, role):
            info.textures[role] = value
    # Self-illuminated CS2 stickers store their glow mask in the normal slot.
    if _flag(info, "g_bSelfIllumSticker0") and F.ROLE_NORMAL in info.textures:
        info.textures[F.ROLE_EMISSION] = info.textures.pop(F.ROLE_NORMAL)
    info.finish = _finish_from_params(info)
    # Every CS2 sticker references the flake normal, only glitter shows it.
    if info.finish != "GLITTER":
        info.textures.pop(F.ROLE_FLAKES, None)
    return info


def _flag(info, key):
    return info.params.get(key, "0").strip() not in ("0", "", "0.0")


def _floats(value):
    try:
        return [float(v) for v in value.strip("[] ").replace(",", " ").split()]
    except ValueError:
        return []


def group_params(info):
    """CS2 material values that map onto finish group inputs (per sticker
    wear behaviour). Keys are group input names."""
    out = {}
    bias = _floats(info.params.get("g_vWearBiasSticker0", ""))
    if bias:
        out["Wear Bias"] = min(4.0, max(0.001, bias[0]))
    scratches = _floats(info.params.get("g_fWearScratchesSticker0", ""))
    if scratches:
        out["Wear Scratches"] = min(1.0, max(0.0, scratches[0]))
    out.update(_legacy_tint(info))
    return out


def _legacy_tint(info):
    """CS2 gold signatures reuse the plain sticker texture: the shader
    desaturates it (g_flTintSaturateSticker0) and multiplies a boosted tint
    (g_vColorTintSticker0 * g_flColorBoostSticker0) into it. The boost only
    brings the dark tint to full brightness, so the tint is normalized to
    its brightest channel. Keys for both the gold and the foil group."""
    if info.params.get("g_bLegacyTintMultiplySticker0", "0").strip() != "1":
        return {}
    tint = _floats(info.params.get("g_vColorTintSticker0", ""))[:3]
    if len(tint) < 3 or max(tint) <= 0 or min(tint) >= 0.999:
        return {}
    peak = max(tint)
    color = [round(min(1.0, max(0.0, v / peak)), 4) for v in tint] + [1.0]
    sat = _floats(info.params.get("g_flTintSaturateSticker0", ""))
    return {
        "Gold Tint": color,
        "Foil Tint": color,
        "Tint Amount": 1.0,
        "Tint Saturation": min(1.0, max(0.0, sat[0])) if sat else 1.0,
    }


# CS2 csgo_weapon_sticker.vfx feature switches -> finish.
_CS2_FLAGS = (
    ("g_bHolographicSticker0", "HOLO"),
    ("g_bGlitterSticker0", "GLITTER"),
    ("g_bMetallicSticker0", "FOIL"),
)
# Finishes that only the name reveals (no dedicated shader switch).
_NAME_ONLY = ("LENTICULAR", "EMBROIDERED", "GOLD")


def _finish_from_params(info):
    tokens = tokenize(os.path.splitext(os.path.basename(info.path))[0])
    # 1) Name-only finishes win ("..._gold" is also g_bMetallic).
    by_name = F.finish_from_tokens(tokens)
    if by_name in _NAME_ONLY:
        return by_name
    # 2) CS2 shader switches.
    for key, finish in _CS2_FLAGS:
        if _flag(info, key):
            return finish
    # 3) Legacy feature flags such as F_HOLO 1 / F_FOIL 1.
    for key, value in info.params.items():
        if key.upper().startswith("F_") and value.strip() not in ("0", "", "0.0"):
            finish = F.normalize_finish(key[2:])
            if finish:
                return finish
    # 4) Shader name, e.g. "csgo_sticker_holo.vfx".
    finish = F.normalize_finish(os.path.basename(info.shader).replace("sticker", ""))
    if finish:
        return finish
    # 5) Material file name, then available maps.
    return F.guess_finish(tokens, info.textures.keys())


def parse_vmat(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse_vmat_text(fh.read(), path)


def _match_in_dir(folder, stem):
    """Image in ``folder`` named ``stem`` (any image extension) or, failing
    that, ``stem`` + "_<suffix>" as Source2Viewer writes decompiled
    textures ("default_holospectrum_tga_e12c79bd.png")."""
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return ""
    images = [n for n in names if n.lower().endswith(IMAGE_EXTENSIONS)]
    for name in images:
        if os.path.splitext(name)[0].lower() == stem:
            return os.path.join(folder, name)
    for name in images:
        if os.path.splitext(name)[0].lower().startswith(stem + "_"):
            return os.path.join(folder, name)
    return ""


def resolve_texture(vmat_path, reference, search_dirs=()):
    """Find the exported image for a texture reference in a vmat.

    The vmat stores game paths like 'stickers/alyx/health.png' or
    'materials/default/stickers/default_holospectrum.tga'. Source2Viewer
    writes the textures of a decompiled vmat flat next to it (by file name),
    and separately decompiled textures keep the tree layout with a
    '_<ext>_<hash>' suffix. We try, in order: the file name next to the vmat,
    the tree path below each parent folder, then the search dirs.
    """
    ref = reference.replace("\\", "/")
    ref_dir, ref_name = os.path.split(ref)
    ref_stem = os.path.splitext(ref_name)[0].lower()
    vmat_dir = os.path.dirname(os.path.abspath(vmat_path))

    found = _match_in_dir(vmat_dir, ref_stem)
    if found:
        return found
    # Tree layout below the vmat folder or any of its parents.
    probe = vmat_dir
    for _ in range(8):
        found = _match_in_dir(os.path.normpath(os.path.join(probe, ref_dir)), ref_stem)
        if found:
            return found
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    for folder in search_dirs:
        found = _match_in_dir(folder, ref_stem)
        if found:
            return found
    return ""
