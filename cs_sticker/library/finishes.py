# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Finish types and texture roles. Pure Python (no bpy), shared by the
catalog, the material builder and the UI."""

from dataclasses import dataclass

# Texture roles a sticker can provide. Keys are used in catalog JSON files.
ROLE_BASE = "base"                # color + alpha (CS2: TextureColor)
ROLE_NORMAL = "normal"            # tangent-space normal map
ROLE_HOLOMASK = "holomask"        # R strength, G/B spectrum offset, A multiplier
ROLE_HOLOSPECTRUM = "holospectrum"  # holo warp / spectrum gradient
ROLE_GLITTER = "glitter"          # glitter mask (where flakes appear)
ROLE_ROUGHNESS = "roughness"
ROLE_METALNESS = "metalness"      # foil / metal mask
ROLE_EMISSION = "emission"        # self-illumination mask (CS2 g_bSelfIllum)
# CS2 TextureWearMaskSticker0: grayscale, 0 outside the sticker, inside the
# value is the wear order (low parts scrape off first). CS2 color maps are
# RGB, so this is also where the sticker shape (alpha) comes from.
ROLE_WEARMASK = "wearmask"
# CS2 TextureStickerScratches: shared scratch pattern (R) that breaks up the
# wear edge. Usually the engine default, which is kept (unlike other defaults).
ROLE_SCRATCHES = "scratches"
# CS2 TextureGlitterNormalSticker0: tiling flake normal map shared by all
# glitter stickers (engine default squares_glitter_normal, kept like scratches).
ROLE_FLAKES = "flakes"

ALL_ROLES = (
    ROLE_BASE, ROLE_NORMAL, ROLE_HOLOMASK, ROLE_HOLOSPECTRUM,
    ROLE_GLITTER, ROLE_ROUGHNESS, ROLE_METALNESS, ROLE_EMISSION, ROLE_WEARMASK,
    ROLE_SCRATCHES, ROLE_FLAKES,
)

# Roles whose pixels are data, not color (loaded as Non-Color).
DATA_ROLES = frozenset({
    ROLE_NORMAL, ROLE_HOLOMASK, ROLE_GLITTER, ROLE_ROUGHNESS, ROLE_METALNESS, ROLE_EMISSION,
    ROLE_WEARMASK, ROLE_SCRATCHES, ROLE_FLAKES,
})


@dataclass(frozen=True)
class Finish:
    id: str
    label: str
    description: str
    required: tuple  # roles without which the finish cannot look right
    optional: tuple  # roles that are used when present
    icon: str


FINISHES = {
    f.id: f for f in (
        Finish("PAPER", "Paper", "Matte printed sticker",
               (ROLE_BASE,), (ROLE_NORMAL, ROLE_ROUGHNESS, ROLE_EMISSION), "FILE_IMAGE"),
        Finish("GLITTER", "Glitter", "Sparkling metallic flakes",
               (ROLE_BASE,), (ROLE_GLITTER, ROLE_NORMAL, ROLE_FLAKES), "LIGHT_SUN"),
        Finish("HOLO", "Holo", "View-dependent holographic spectrum",
               (ROLE_BASE, ROLE_HOLOMASK), (ROLE_HOLOSPECTRUM, ROLE_NORMAL), "SHADING_RENDERED"),
        Finish("FOIL", "Foil", "Embossed metallic foil",
               (ROLE_BASE, ROLE_NORMAL), (ROLE_METALNESS, ROLE_ROUGHNESS), "MATSHADERBALL"),
        Finish("GOLD", "Gold", "Embossed gold foil",
               (ROLE_BASE, ROLE_NORMAL), (ROLE_METALNESS, ROLE_ROUGHNESS), "SOLO_ON"),
        Finish("LENTICULAR", "Lenticular", "Image changes with viewing angle",
               (ROLE_BASE,), (ROLE_NORMAL,), "IMAGE_REFERENCE"),
        Finish("EMBROIDERED", "Embroidered", "Stitched fabric patch",
               (ROLE_BASE,), (ROLE_NORMAL,), "OUTLINER_DATA_LATTICE"),
    )
}

DEFAULT_FINISH = "PAPER"

# Words in file names / vmat keys that hint at a finish (checked in order).
FINISH_KEYWORDS = (
    ("LENTICULAR", ("lenticular", "lenti")),
    ("EMBROIDERED", ("embroidered", "embroidery", "embroid", "patch", "stitch")),
    ("HOLO", ("holo", "holographic")),
    ("GLITTER", ("glitter",)),
    ("GOLD", ("gold",)),
    ("FOIL", ("foil", "chrome")),
    ("PAPER", ("paper",)),
)


def normalize_finish(value):
    """Map free text ("holo", "Holo", "HOLO") to a finish id, or None."""
    if not value:
        return None
    text = str(value).strip().upper()
    if text in FINISHES:
        return text
    low = text.lower()
    for finish_id, words in FINISH_KEYWORDS:
        if any(w in low for w in words):
            return finish_id
    return None


def finish_from_tokens(name_tokens):
    """Finish named by an exact token ("crown_foil" -> FOIL), else None.
    Exact match on purpose: "golden_eagle" is not a gold sticker."""
    tokens = set(name_tokens)
    for finish_id, words in FINISH_KEYWORDS:
        if tokens.intersection(words):
            return finish_id
    return None


def guess_finish(name_tokens, roles):
    """Guess a finish from name tokens first, then from available maps."""
    by_name = finish_from_tokens(name_tokens)
    if by_name:
        return by_name
    if ROLE_HOLOMASK in roles:
        return "HOLO"
    if ROLE_GLITTER in roles:
        return "GLITTER"
    if ROLE_NORMAL in roles:
        return "FOIL"
    return DEFAULT_FINISH


def missing_roles(finish_id, roles):
    """Required roles of a finish that are not available."""
    finish = FINISHES.get(finish_id, FINISHES[DEFAULT_FINISH])
    return [r for r in finish.required if r not in roles]
