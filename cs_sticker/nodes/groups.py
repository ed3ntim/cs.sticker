# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Reusable shader node groups, one per CS2 sticker finish, plus helper
groups for wear/alpha clipping, holo spectrum lookup and lenticular frames.

Groups take *texture samples* as inputs (Base Color, Alpha, Normal Color,
Holo Mask, ...) instead of containing Image Texture nodes themselves, so a
single group serves every sticker of that finish. The material builder
(material.py) creates the Image Texture nodes and wires them in.

Shading model (approximating csgo_sticker.vfx):

* Paper        matte print, light clear coat option
* Glitter      micro-flakes perturb the normal, metallic in mask. Flakes come
               from the CS2 flake normal texture when wired, else voronoi
* Holo         mask R = strength, G/B = spectrum offset, A = multiplier;
               spectrum lookup shifts with view angle ("tilt")
* Foil         metallic where mask, embossed via normal map
* Gold         foil with gold tint multiplied into the (optionally
               desaturated) base, like CS2's legacy tint multiply
* Lenticular   CS2: holo-style spectrum lookup through the mask (the spectrum
               holds the alternate images); fallback: horizontal frame
               strip picked by view angle. Lens coat with ridges
* Embroidered  rough fabric with sheen and stitched thread relief

Every finish group exposes the wear inputs (see _build_wear) and Alpha Clip.
"""

import bpy

from .builder import GroupBuilder, principled, set_bsdf

# Bump when group contents change; outdated groups are replaced (old ones
# are renamed, so existing materials keep working until re-spawned).
GROUP_VERSION = 5
VERSION_KEY = "cs_sticker_version"

PREFIX = "CS2 "
FLAT_NORMAL = (0.5, 0.5, 1.0, 1.0)


def group_name(finish_id):
    return f"{PREFIX}Sticker {finish_id.title()}"


# ---------------------------------------------------------------------------
# Helper groups
# ---------------------------------------------------------------------------

def _wear_sockets(b):
    """Wear inputs shared by the Wear & Clip group and every finish group."""
    return {
        "Wear": b.input("Wear", default=0.0, lo=0.0, hi=1.0, factor=True,
                        description="Scraped-off amount, like the in-game sticker wear"),
        "Wear Scale": b.input("Wear Scale", default=12.0, lo=0.0, hi=1000.0,
                              description="Noise scale of the wear pattern (stickers without wear mask)"),
        "Wear Seed": b.input("Wear Seed", default=0.0,
                             description="Varies the scratch / noise pattern. Set per sticker on spawn"),
        "Wear Mask": b.input("Wear Mask", default=0.0, lo=0.0, hi=1.0, factor=True,
                             description="CS2 wear mask: low values wear off first"),
        "Use Wear Mask": b.input("Use Wear Mask", default=0.0, lo=0.0, hi=1.0, factor=True),
        "Wear Bias": b.input("Wear Bias", default=1.0, lo=0.001, hi=4.0,
                             description="CS2 g_vWearBias: higher = the sticker resists wear longer"),
        "Scratches": b.input("Scratches", default=0.5, lo=0.0, hi=1.0, factor=True),
        "Wear Scratches": b.input("Wear Scratches", default=1.0, lo=0.0, hi=1.0, factor=True,
                                  description="CS2 g_fWearScratches: how much the scratch texture breaks up the wear edge"),
        "Alpha Clip": b.input("Alpha Clip", default=0.5, lo=0.0, hi=1.0, factor=True,
                              description="Alpha threshold for hard clipping. 0 = soft alpha"),
    }


def _build_wear(tree):
    """Alpha + wear -> clipped alpha. Outputs Alpha, Intact.

    CS2 stickers carry their own wear mask: the gray value is the order in
    which areas scrape off (background low, logo high). A pixel survives
    while mask + scratch offset > Wear / Wear Bias. Stickers without a mask
    fall back to seeded noise."""
    b = GroupBuilder(tree)
    alpha = b.input("Alpha", default=1.0, lo=0.0, hi=1.0, factor=True)
    s = _wear_sockets(b)
    clip, wear, scale, seed = s["Alpha Clip"], s["Wear"], s["Wear Scale"], s["Wear Seed"]
    out_alpha = b.output("Alpha", "FLOAT")
    out_intact = b.output("Intact", "FLOAT")

    b.column(-900)
    coord = b.node("ShaderNodeTexCoord", y=200)
    noise = b.node("ShaderNodeTexNoise", x=-700, y=200, noise_dimensions="4D")
    b.link((coord, "UV"), (noise, "Vector"))
    b.set_or_link(noise, "Scale", scale)
    b.set_or_link(noise, "W", seed)
    b.set_or_link(noise, "Detail", 6.0)
    b.set_or_link(noise, "Roughness", 0.6)

    # Remap wear 0..1 into the useful noise range, narrow soft edge.
    b.column(-500)
    center = b.math("MULTIPLY_ADD", wear, 0.8, y=0)
    center.node.inputs[2].default_value = 0.1
    lo = b.math("SUBTRACT", center, 0.04, y=-150)
    hi = b.math("ADD", center, 0.04, y=-300)
    b.column(-300)
    intact_noise = b.map_range((noise, "Fac"), lo, hi, 0.0, 1.0, interpolation="SMOOTHSTEP")

    # Wear mask path: threshold = wear / bias, scratches shift the edge.
    b.column(-500)
    threshold = b.math("DIVIDE", wear, s["Wear Bias"], y=-450)
    scratch = b.math("SUBTRACT", s["Scratches"], 0.5, y=-600)
    scratch = b.math("MULTIPLY", scratch, s["Wear Scratches"], x=-350, y=-600)
    durability = b.math("MULTIPLY_ADD", scratch, 0.35, x=-200, y=-600)
    b.links.new(s["Wear Mask"], durability.node.inputs[2])
    # Small seeded jitter so two copies of a sticker do not wear identically.
    jitter = b.math("MULTIPLY_ADD", (noise, "Fac"), 0.1, x=-350, y=-750)
    jitter.node.inputs[2].default_value = -0.05
    durability = b.math("ADD", durability, jitter, x=-200, y=-750)
    t_lo = b.math("SUBTRACT", threshold, 0.015, x=-350, y=-450)
    t_hi = b.math("ADD", threshold, 0.015, x=-350, y=-350)
    intact_mask = b.map_range(durability, t_lo, t_hi, 0.0, 1.0, x=-50, y=-450,
                              interpolation="SMOOTHSTEP")
    intact = b.mix("FLOAT", s["Use Wear Mask"], intact_noise, intact_mask, x=-150, y=0)
    # Wear exactly 0 must leave the sticker untouched.
    no_wear = b.math("SUBTRACT", 1.0, b.math("CEIL", wear, x=-300, y=-200), x=-150, y=-200)
    intact = b.math("MAXIMUM", intact, no_wear, x=0, y=0)

    worn_alpha = b.math("MULTIPLY", alpha, intact, x=150, y=0)
    hard = b.math("GREATER_THAN", worn_alpha, clip, x=300, y=-100)
    use_clip = b.math("CEIL", clip, x=300, y=-250)
    final = b.mix("FLOAT", use_clip, worn_alpha, hard, x=500, y=0)
    b.links.new(final, out_alpha)
    b.links.new(intact, out_intact)


def _build_holo_coords(tree):
    """Holo mask + view angle -> spectrum lookup vector."""
    b = GroupBuilder(tree)
    mask = b.input("Holo Mask", "COLOR", default=(1.0, 0.0, 0.0, 1.0))
    tilt_strength = b.input("Tilt Strength", default=1.0, lo=-10.0, hi=10.0,
                            description="How fast the spectrum shifts with viewing angle")
    scale = b.input("Spectrum Scale", default=1.0, lo=-100.0, hi=100.0)
    offset = b.input("Spectrum Offset", default=0.0)
    out = b.output("Vector", "VECTOR")

    b.column(-900)
    geo = b.node("ShaderNodeNewGeometry", y=200)
    tangent = b.node("ShaderNodeTangent", y=-50, direction_type="UV_MAP")
    _, g, bl = b.separate_color(mask, x=-900, y=-300)

    b.column(-650)
    facing = b.math("SUBTRACT", 1.0, b.vmath("DOT_PRODUCT", (geo, "Normal"), (geo, "Incoming"), y=250),
                    x=-450, y=250)
    side = b.vmath("DOT_PRODUCT", (geo, "Incoming"), (tangent, "Tangent"), y=0)
    b.column(-250)
    tilt = b.math("ADD", b.math("MULTIPLY", side, 0.5, y=0), b.math("MULTIPLY", facing, 0.5, y=200), x=-100)
    tilt = b.math("MULTIPLY", tilt, tilt_strength, x=50)
    u = b.math("ADD", g, tilt, x=200)
    u = b.math("MULTIPLY_ADD", u, scale, x=350)
    b.links.new(offset, u.node.inputs[2])
    b.links.new(b.combine(u, bl, 0.0, x=550), out)


def _build_holo_spectrum(tree):
    """Procedural rainbow used when no holospectrum texture exists."""
    b = GroupBuilder(tree)
    vec = b.input("Vector", "VECTOR", hide_value=True)
    out = b.output("Color", "COLOR")
    x, _, _ = b.separate(vec, x=-900)
    u = b.math("FRACT", x, x=-650)
    ramp = b.node("ShaderNodeValToRGB", x=-450)
    elems = ramp.color_ramp.elements
    colors = [(1, 0.15, 0.15), (1, 0.85, 0.2), (0.25, 1, 0.35), (0.2, 0.85, 1),
              (0.35, 0.3, 1), (1, 0.3, 0.9), (1, 0.15, 0.15)]
    elems[0].position, elems[0].color = 0.0, (*colors[0], 1)
    elems[1].position, elems[1].color = 1.0, (*colors[-1], 1)
    for i, c in enumerate(colors[1:-1], start=1):
        e = elems.new(i / (len(colors) - 1))
        e.color = (*c, 1)
    b.links.new(u, ramp.inputs["Fac"])
    b.links.new(ramp.outputs["Color"], out)


def _build_lenticular_coords(tree):
    """UV of the active frame in a horizontal frame strip, picked by view angle."""
    b = GroupBuilder(tree)
    frames = b.input("Frames", default=2.0, lo=1.0, hi=64.0,
                     description="Number of frames packed side by side in the base texture")
    sens = b.input("Sensitivity", default=1.5, lo=0.0, hi=20.0,
                   description="How quickly frames change with viewing angle")
    offset = b.input("Frame Offset", default=0.0, lo=-1.0, hi=1.0,
                     description="Shifts which frame is visible head-on")
    out = b.output("Vector", "VECTOR")

    b.column(-900)
    coord = b.node("ShaderNodeTexCoord", y=250)
    geo = b.node("ShaderNodeNewGeometry", y=0)
    tangent = b.node("ShaderNodeTangent", y=-250, direction_type="UV_MAP")
    side = b.vmath("DOT_PRODUCT", (geo, "Incoming"), (tangent, "Tangent"), x=-650, y=0)
    # t in [0, 1): 0.5 head-on, sensitivity spreads it around the center.
    t = b.math("MULTIPLY_ADD", side, b.math("MULTIPLY", sens, 0.5, x=-650, y=-200), x=-450)
    b.links.new(b.math("ADD", offset, 0.5, x=-650, y=-350), t.node.inputs[2])
    t = b.math("MINIMUM", b.math("MAXIMUM", t, 0.0, x=-300), 0.9999, x=-150)
    idx = b.math("FLOOR", b.math("MULTIPLY", t, frames, x=0), x=150)
    u, v, _ = b.separate((coord, "UV"), x=150, y=250)
    u = b.math("DIVIDE", b.math("ADD", u, idx, x=300), frames, x=450)
    b.links.new(b.combine(u, v, 0.0, x=650), out)


# ---------------------------------------------------------------------------
# Finish groups
# ---------------------------------------------------------------------------

def _common_inputs(b, normal_strength=1.0):
    base = b.input("Base Color", "COLOR", default=(0.8, 0.8, 0.8, 1.0))
    alpha = b.input("Alpha", default=1.0, lo=0.0, hi=1.0, factor=True)
    ncol = b.input("Normal Color", "COLOR", default=FLAT_NORMAL)
    nstr = b.input("Normal Strength", default=normal_strength, lo=0.0, hi=10.0)
    return base, alpha, ncol, nstr


def _wear_inputs(b):
    return _wear_sockets(b)


def _normal_map(b, ncol, nstr, x=-300, y=-450):
    nm = b.node("ShaderNodeNormalMap", x, y)
    b.set_or_link(nm, "Color", ncol)
    b.set_or_link(nm, "Strength", nstr)
    return nm.outputs["Normal"]


def _wear_alpha(b, alpha, wear, x=200, y=-700):
    node = b.subgroup(ensure_group("WEAR"), dict(wear, Alpha=alpha), x=x, y=y)
    return node.outputs["Alpha"], node.outputs["Intact"]


def _finish(b, bsdf):
    out = b.output("Shader")
    b.links.new(bsdf.outputs[0], out)


def _build_paper(tree):
    b = GroupBuilder(tree)
    base, alpha, ncol, nstr = _common_inputs(b, 0.5)
    rough = b.input("Roughness", default=0.55, lo=0.0, hi=1.0, factor=True)
    gloss = b.input("Gloss", default=0.1, lo=0.0, hi=1.0, factor=True,
                    description="Clear laminate on top of the print")
    glow = b.input("Emission Mask", default=0.0, lo=0.0, hi=1.0, factor=True,
                   description="Self-illuminated areas (CS2 glow stickers)")
    glow_str = b.input("Emission Strength", default=2.0, lo=0.0, hi=100.0)
    wear = _wear_inputs(b)
    bsdf = principled(b)
    a, _ = _wear_alpha(b, alpha, wear)
    set_bsdf(b, bsdf, Base_Color=base, Roughness=rough, Alpha=a,
             Normal=_normal_map(b, ncol, nstr), Specular_IOR_Level=0.4,
             Coat_Weight=gloss, Coat_Roughness=0.15, Emission_Color=base,
             Emission_Strength=b.math("MULTIPLY", glow, glow_str, x=-300, y=-200))
    _finish(b, bsdf)


def _build_glitter(tree):
    b = GroupBuilder(tree)
    base, alpha, ncol, nstr = _common_inputs(b, 0.5)
    mask = b.input("Glitter Mask", default=1.0, lo=0.0, hi=1.0, factor=True)
    gscale = b.input("Glitter Scale", default=450.0, lo=1.0, hi=10000.0)
    gstr = b.input("Glitter Strength", default=0.6, lo=0.0, hi=2.0)
    gmetal = b.input("Glitter Metallic", default=0.9, lo=0.0, hi=1.0, factor=True)
    grough = b.input("Glitter Roughness", default=0.2, lo=0.0, hi=1.0, factor=True)
    rough = b.input("Roughness", default=0.5, lo=0.0, hi=1.0, factor=True)
    flake_col = b.input("Flake Normal", "COLOR", default=FLAT_NORMAL,
                        description="Tiled CS2 flake normal (squares_glitter_normal)")
    use_tex = b.input("Use Flake Texture", default=0.0, lo=0.0, hi=1.0, factor=True,
                      description="1 = flakes from Flake Normal, 0 = procedural voronoi flakes")
    wear = _wear_inputs(b)

    coord = b.node("ShaderNodeTexCoord", x=-900, y=-200)
    vor = b.node("ShaderNodeTexVoronoi", x=-700, y=-200, feature="F1")
    b.link((coord, "UV"), (vor, "Vector"))
    b.set_or_link(vor, "Scale", gscale)
    # Random per-flake color -> random tilt in [-1, 1] * strength.
    flake = b.vmath("MULTIPLY_ADD", (vor, "Color"), (2.0, 2.0, 2.0), x=-500, y=-200)
    flake.node.inputs[2].default_value = (-1.0, -1.0, -1.0)
    flake = b.vmath("SCALE", flake, x=-300, y=-200, scale=gstr)
    # Texture flakes: tilt = flake normal minus the unperturbed normal.
    geo = b.node("ShaderNodeNewGeometry", x=-500, y=-650)
    tex_flake = b.vmath("SUBTRACT", _normal_map(b, flake_col, gstr, x=-500, y=-800),
                        (geo, "Normal"), x=-300, y=-700)
    flake = b.mix("VECTOR", use_tex, flake, tex_flake, x=-100, y=-150)
    nrm = _normal_map(b, ncol, nstr, x=-300, y=-450)
    tilted = b.vmath("NORMALIZE", b.vmath("ADD", nrm, flake, x=-100, y=-300), x=50, y=-300)
    normal = b.mix("VECTOR", mask, nrm, tilted, x=250, y=-300)

    bsdf = principled(b)
    a, _ = _wear_alpha(b, alpha, wear)
    set_bsdf(b, bsdf, Base_Color=base, Alpha=a, Normal=normal,
             Metallic=b.math("MULTIPLY", mask, gmetal, x=250, y=100),
             Roughness=b.mix("FLOAT", mask, rough, grough, x=250, y=-50))
    _finish(b, bsdf)


def _build_holo(tree):
    b = GroupBuilder(tree)
    base, alpha, ncol, nstr = _common_inputs(b, 0.5)
    mask = b.input("Holo Mask", "COLOR", default=(1.0, 0.0, 0.0, 1.0),
                   description="R = holo strength, G/B = spectrum offset")
    mask_a = b.input("Holo Mask Alpha", default=1.0, lo=0.0, hi=1.0, factor=True)
    spectrum = b.input("Spectrum Color", "COLOR", default=(1.0, 1.0, 1.0, 1.0))
    hstr = b.input("Holo Strength", default=1.0, lo=0.0, hi=2.0, factor=True)
    hmetal = b.input("Holo Metallic", default=0.7, lo=0.0, hi=1.0, factor=True)
    rough = b.input("Roughness", default=0.4, lo=0.0, hi=1.0, factor=True)
    hrough = b.input("Holo Roughness", default=0.15, lo=0.0, hi=1.0, factor=True)
    emit = b.input("Holo Emission", default=0.0, lo=0.0, hi=10.0,
                   description="Extra glow of the spectrum (stylized look)")
    wear = _wear_inputs(b)

    r, _, _ = b.separate_color(mask, x=-900, y=200)
    strength = b.math("MULTIPLY", b.math("MULTIPLY", r, mask_a, x=-700, y=200), hstr, x=-550, y=200, clamp=True)
    color = b.mix("RGBA", strength, base, spectrum, x=-300, y=300)
    bsdf = principled(b)
    a, intact = _wear_alpha(b, alpha, wear)
    set_bsdf(b, bsdf, Base_Color=color, Alpha=a, Normal=_normal_map(b, ncol, nstr),
             Metallic=b.math("MULTIPLY", strength, hmetal, x=-300, y=100),
             Roughness=b.mix("FLOAT", strength, rough, hrough, x=-300, y=-50),
             Emission_Color=spectrum,
             Emission_Strength=b.math("MULTIPLY", strength, emit, x=-300, y=-200))
    _finish(b, bsdf)


def _build_foil(tree, gold=False):
    b = GroupBuilder(tree)
    base, alpha, ncol, nstr = _common_inputs(b, 1.0)
    mask = b.input("Metal Mask", default=1.0, lo=0.0, hi=1.0, factor=True,
                   description="Where the foil is metallic (1 = everywhere)")
    if gold:
        tint = b.input("Gold Tint", "COLOR", default=(1.0, 0.71, 0.29, 1.0))
        amount = b.input("Tint Amount", default=0.85, lo=0.0, hi=1.0, factor=True)
    else:
        tint = b.input("Foil Tint", "COLOR", default=(1.0, 1.0, 1.0, 1.0))
        amount = 1.0
    saturation = b.input("Tint Saturation", default=1.0, lo=0.0, hi=1.0, factor=True,
                         description="Base saturation before the tint is multiplied in "
                                     "(CS2 gold signatures: about 0.1)")
    metal = b.input("Metallic", default=1.0, lo=0.0, hi=1.0, factor=True)
    rough = b.input("Roughness", default=0.22 if gold else 0.25, lo=0.0, hi=1.0, factor=True)
    wear = _wear_inputs(b)

    gray = b.node("ShaderNodeRGBToBW", -900, 450)
    b.link(base, gray.inputs[0])
    desat = b.mix("RGBA", saturation, gray.outputs[0], base, x=-700, y=450)
    product = b.mix("RGBA", 1.0, desat, tint, x=-600, y=350, blend="MULTIPLY")
    tinted = b.mix("RGBA", amount, base, product, x=-500, y=300)
    color = b.mix("RGBA", mask, base, tinted, x=-300, y=300)
    bsdf = principled(b)
    a, _ = _wear_alpha(b, alpha, wear)
    set_bsdf(b, bsdf, Base_Color=color, Alpha=a, Normal=_normal_map(b, ncol, nstr),
             Metallic=b.math("MULTIPLY", mask, metal, x=-300, y=100),
             Roughness=b.mix("FLOAT", mask, 0.5, rough, x=-300, y=-50))
    _finish(b, bsdf)


def _build_gold(tree):
    _build_foil(tree, gold=True)


def _build_lenticular(tree):
    """Two modes, chosen by what the material wires in:

    * CS2 (holo mask + spectrum linked): like Holo, the mask addresses the
      alternate images stored in the spectrum texture and the view angle
      shifts the lookup, so the picture flips when the weapon is turned.
    * Frame strip (no mask, Holo Mask stays black): the base texture already
      holds the frame picked by "CS2 Lenticular Coords".
    Both get a glossy lens coat with fine ridges."""
    b = GroupBuilder(tree)
    base, alpha, ncol, nstr = _common_inputs(b, 0.5)
    mask = b.input("Holo Mask", "COLOR", default=(0.0, 0.0, 0.0, 1.0),
                   description="R = how much of the spectrum image shows, G/B = lookup")
    mask_a = b.input("Holo Mask Alpha", default=1.0, lo=0.0, hi=1.0, factor=True)
    spectrum = b.input("Spectrum Color", "COLOR", default=(1.0, 1.0, 1.0, 1.0))
    hstr = b.input("Holo Strength", default=1.0, lo=0.0, hi=2.0, factor=True)
    rough = b.input("Roughness", default=0.35, lo=0.0, hi=1.0, factor=True)
    lens = b.input("Lens Gloss", default=1.0, lo=0.0, hi=1.0, factor=True,
                   description="Clear coat of the lens sheet")
    density = b.input("Ridge Density", default=150.0, lo=0.0, hi=5000.0)
    depth = b.input("Ridge Depth", default=0.1, lo=0.0, hi=1.0)
    wear = _wear_inputs(b)

    r, _, _ = b.separate_color(mask, x=-900, y=200)
    strength = b.math("MULTIPLY", b.math("MULTIPLY", r, mask_a, x=-700, y=200), hstr, x=-550, y=200, clamp=True)
    color = b.mix("RGBA", strength, base, spectrum, x=-300, y=300)

    coord = b.node("ShaderNodeTexCoord", x=-900, y=-600)
    wave = b.node("ShaderNodeTexWave", x=-700, y=-600, wave_type="BANDS", bands_direction="X")
    b.link((coord, "UV"), (wave, "Vector"))
    b.set_or_link(wave, "Scale", density)
    nrm = _normal_map(b, ncol, nstr)
    bump = b.node("ShaderNodeBump", x=-100, y=-600)
    b.set_or_link(bump, "Strength", depth)
    b.set_or_link(bump, "Distance", 0.01)
    b.link((wave, "Fac"), (bump, "Height"))
    b.links.new(nrm, bump.inputs["Normal"])

    bsdf = principled(b)
    a, _ = _wear_alpha(b, alpha, wear)
    set_bsdf(b, bsdf, Base_Color=color, Alpha=a, Roughness=rough, Normal=nrm,
             Coat_Weight=lens, Coat_Roughness=0.05, Coat_Normal=bump.outputs["Normal"])
    _finish(b, bsdf)


def _build_embroidered(tree):
    b = GroupBuilder(tree)
    base, alpha, ncol, nstr = _common_inputs(b, 1.0)
    rough = b.input("Roughness", default=0.8, lo=0.0, hi=1.0, factor=True)
    sheen = b.input("Sheen", default=0.6, lo=0.0, hi=1.0, factor=True,
                    description="Fabric sheen at grazing angles, tinted by the thread color")
    density = b.input("Thread Density", default=120.0, lo=0.0, hi=5000.0)
    depth = b.input("Thread Depth", default=0.4, lo=0.0, hi=1.0)
    shade = b.input("Thread Shading", default=0.35, lo=0.0, hi=1.0, factor=True,
                    description="Darkening in the grooves between threads")
    wear = _wear_inputs(b)

    coord = b.node("ShaderNodeTexCoord", x=-900, y=-600)
    wave = b.node("ShaderNodeTexWave", x=-700, y=-600, wave_type="BANDS",
                  bands_direction="DIAGONAL", wave_profile="SIN")
    b.link((coord, "UV"), (wave, "Vector"))
    b.set_or_link(wave, "Scale", density)
    b.set_or_link(wave, "Distortion", 2.0)
    b.set_or_link(wave, "Detail", 3.0)
    groove = b.map_range((wave, "Fac"), 0.0, 1.0, b.math("SUBTRACT", 1.0, shade, x=-700, y=100), 1.0,
                         x=-500, y=100)
    color = b.mix("RGBA", 1.0, base, groove, x=-300, y=300, blend="MULTIPLY")

    nrm = _normal_map(b, ncol, nstr)
    bump = b.node("ShaderNodeBump", x=-100, y=-600)
    b.set_or_link(bump, "Strength", depth)
    b.set_or_link(bump, "Distance", 0.02)
    b.link((wave, "Fac"), (bump, "Height"))
    b.links.new(nrm, bump.inputs["Normal"])

    bsdf = principled(b)
    a, _ = _wear_alpha(b, alpha, wear)
    set_bsdf(b, bsdf, Base_Color=color, Alpha=a, Roughness=rough, Normal=bump.outputs["Normal"],
             Sheen_Weight=sheen, Sheen_Roughness=0.5, Sheen_Tint=base, Specular_IOR_Level=0.2)
    _finish(b, bsdf)


_BUILDERS = {
    # helper groups
    "WEAR": (f"{PREFIX}Wear & Clip", _build_wear),
    "HOLO_COORDS": (f"{PREFIX}Holo Coords", _build_holo_coords),
    "HOLO_SPECTRUM": (f"{PREFIX}Holo Spectrum", _build_holo_spectrum),
    "LENTICULAR_COORDS": (f"{PREFIX}Lenticular Coords", _build_lenticular_coords),
    # finish groups
    "PAPER": (group_name("PAPER"), _build_paper),
    "GLITTER": (group_name("GLITTER"), _build_glitter),
    "HOLO": (group_name("HOLO"), _build_holo),
    "FOIL": (group_name("FOIL"), _build_foil),
    "GOLD": (group_name("GOLD"), _build_gold),
    "LENTICULAR": (group_name("LENTICULAR"), _build_lenticular),
    "EMBROIDERED": (group_name("EMBROIDERED"), _build_embroidered),
}

FINISH_GROUP_KEYS = ("PAPER", "GLITTER", "HOLO", "FOIL", "GOLD", "LENTICULAR", "EMBROIDERED")


def ensure_group(key):
    """Return the node group for ``key``, building or upgrading it if needed."""
    name, build = _BUILDERS[key]
    tree = bpy.data.node_groups.get(name)
    if tree is not None and tree.get(VERSION_KEY) == GROUP_VERSION:
        return tree
    if tree is not None:
        tree.name = f"{name} (v{tree.get(VERSION_KEY, 0)})"
    tree = bpy.data.node_groups.new(name, "ShaderNodeTree")
    tree[VERSION_KEY] = GROUP_VERSION
    build(tree)
    return tree


def ensure_all():
    return [ensure_group(k) for k in _BUILDERS]
