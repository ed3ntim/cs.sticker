# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Assemble a sticker material: Image Texture nodes for each available map,
wired into the finish node group from groups.py."""

import os
import zlib

import bpy

from .. import utils
from ..library import finishes as F
from . import groups
from .builder import find_socket

STEEP_FACES_LABEL = "Steep Faces"
# Facing (dot of face normal and projection axis) below which the sticker
# fades out. Only near-vertical walls: with fine subdivision a sticker
# bridging a step looks right, hiding it leaves visible gaps.
STEEP_FROM, STEEP_TO = 0.08, 0.2
# Point attribute written by the "CS Clip" modifier: 1 where the projection
# missed the target (the sticker would float), 0 on the surface.
UNPROJECTED_ATTRIBUTE = "cs_unprojected"

# UV repeats of the CS2 flake normal across a sticker (estimate, not taken
# from the shader).
FLAKE_TILING = 8.0

MISSING_IMAGE_NAME = "CS2 Missing Texture"
MAT_PREFIX = "CS2 "


def _missing_image():
    """Magenta placeholder so missing textures are obvious in the viewport."""
    img = bpy.data.images.get(MISSING_IMAGE_NAME)
    if img is None:
        img = bpy.data.images.new(MISSING_IMAGE_NAME, 64, 64, alpha=True)
        img.generated_color = (1.0, 0.0, 1.0, 1.0)
    return img


def load_image(path, data=False):
    """Load (or reuse) an image. Data maps are Non-Color with channel-packed
    alpha so the holo mask alpha does not darken its RGB channels.
    Returns None when the file is missing or unreadable."""
    if not path or not os.path.isfile(path):
        return None
    try:
        img = bpy.data.images.load(path, check_existing=True)
    except RuntimeError:
        return None
    if data:
        try:
            img.colorspace_settings.name = "Non-Color"
        except TypeError:
            img.colorspace_settings.is_data = True
        img.alpha_mode = "CHANNEL_PACKED"
    return img


def image_size(path):
    """(width, height) of an image file, loading it through Blender."""
    img = load_image(path)
    if img is None or not img.size[0] or not img.size[1]:
        return 1, 1
    return img.size[0], img.size[1]


def _configure_material(mat):
    """Alpha-clipped, double-sided sticker material settings."""
    # EEVEE (4.2+): dithered render method handles clipped alpha correctly.
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    elif hasattr(mat, "blend_method"):
        mat.blend_method = "CLIP"
    mat.use_backface_culling = False
    if hasattr(mat, "use_transparency_overlap"):
        mat.use_transparency_overlap = False
    # Stickers are thin decals: no displacement, bump only.
    if hasattr(mat, "displacement_method"):
        mat.displacement_method = "BUMP"


def build_material(sticker, unique=True):
    """Create the material for ``sticker``. Returns (material, warnings).

    With ``unique=False`` an existing material of the same sticker is reused.
    Missing textures never raise: the base map falls back to a magenta
    placeholder and optional maps are simply left out, each with a warning.
    """
    warnings = []
    name = f"{MAT_PREFIX}{sticker.name}"
    if not unique:
        for mat in bpy.data.materials:
            if mat.get(utils.PROP_STICKER_ID) == sticker.id:
                return mat, warnings

    mat = bpy.data.materials.new(name)
    mat[utils.PROP_STICKER_ID] = sticker.id
    if not getattr(mat, "use_nodes", True):
        mat.use_nodes = True  # always on (and deprecated) in Blender 5.x
    _configure_material(mat)
    tree = mat.node_tree
    nodes, links = tree.nodes, tree.links
    nodes.clear()

    finish = sticker.finish if sticker.finish in groups.FINISH_GROUP_KEYS else F.DEFAULT_FINISH
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)
    grp = nodes.new("ShaderNodeGroup")
    grp.node_tree = groups.ensure_group(finish)
    grp.name = utils.STICKER_NODE_NAME
    grp.label = f"CS2 Sticker ({F.FINISHES[finish].label})"
    grp.location = (150, 0)
    grp.width = 260
    links.new(grp.outputs["Shader"], out.inputs["Surface"])

    for role in F.missing_roles(finish, {r for r, p in sticker.textures.items() if p and os.path.isfile(p)}):
        warnings.append(f"{sticker.name}: required {role} texture missing for {finish.title()} finish")

    def tex_node(role, y, vector=None):
        path = sticker.textures.get(role, "")
        img = load_image(path, data=role in F.DATA_ROLES)
        if img is None:
            if path:
                warnings.append(f"{sticker.name}: {role} texture not found ({path})")
            if role != F.ROLE_BASE:
                return None
            img = _missing_image()
        n = nodes.new("ShaderNodeTexImage")
        n.image = img
        n.label = role.title()
        n.location = (-450, y)
        n.interpolation = "Linear"
        if role in (F.ROLE_BASE, F.ROLE_WEARMASK):
            n.extension = "CLIP"
        else:
            n.extension = "REPEAT" if role == F.ROLE_SCRATCHES else "EXTEND"
        if vector is not None:
            links.new(vector, n.inputs["Vector"])
        return n

    def wire(src, input_name):
        """Link into the group input if this finish exposes it."""
        try:
            links.new(src, find_socket(grp.inputs, input_name))
        except KeyError:
            pass

    # Lenticular without a holo mask: base and normal sample the active
    # frame of a frame strip. With a mask (CS2) it uses the holo pipeline.
    lenticular_strip = finish == "LENTICULAR" and F.ROLE_HOLOMASK not in sticker.textures
    uv = None
    if lenticular_strip:
        coords = nodes.new("ShaderNodeGroup")
        coords.node_tree = groups.ensure_group("LENTICULAR_COORDS")
        coords.location = (-750, 200)
        frames = sticker.params.get("frames", 2)
        try:
            coords.inputs["Frames"].default_value = max(1.0, float(frames))
        except (TypeError, ValueError):
            warnings.append(f"{sticker.name}: invalid frames value '{frames}'")
        uv = coords.outputs["Vector"]

    base = tex_node(F.ROLE_BASE, 300, uv)
    wire(base.outputs["Color"], "Base Color")
    wearmask = tex_node(F.ROLE_WEARMASK, 600, uv) if F.ROLE_WEARMASK in sticker.textures else None
    if wearmask:
        # CS2: shape = wear mask > ~0.8 % (inside values are small but > 0).
        shape = nodes.new("ShaderNodeMath")
        shape.operation = "MULTIPLY"
        shape.use_clamp = True
        shape.inputs[1].default_value = 128.0
        shape.label = "Sticker Shape"
        shape.location = (-150, 450)
        links.new(wearmask.outputs["Color"], shape.inputs[0])
        wire(_steep_face_cutoff(nodes, links, shape.outputs[0]), "Alpha")
        # Gray value = wear order: each CS2 sticker wears its own way.
        wire(wearmask.outputs["Color"], "Wear Mask")
        _set_input(grp, "Use Wear Mask", 1.0)
        scratches = tex_node(F.ROLE_SCRATCHES, 900) if F.ROLE_SCRATCHES in sticker.textures else None
        if scratches:
            wire(scratches.outputs["Color"], "Scratches")
    else:
        wire(_steep_face_cutoff(nodes, links, base.outputs["Alpha"]), "Alpha")

    normal = tex_node(F.ROLE_NORMAL, 0, uv)
    if normal:
        wire(normal.outputs["Color"], "Normal Color")

    rough = tex_node(F.ROLE_ROUGHNESS, -300) if F.ROLE_ROUGHNESS in sticker.textures else None
    if rough:
        wire(rough.outputs["Color"], "Roughness")

    if finish in ("FOIL", "GOLD") and F.ROLE_METALNESS in sticker.textures:
        metal = tex_node(F.ROLE_METALNESS, -600)
        if metal:
            wire(metal.outputs["Color"], "Metal Mask")

    if F.ROLE_EMISSION in sticker.textures:
        glow = tex_node(F.ROLE_EMISSION, -900)
        if glow:
            wire(glow.outputs["Color"], "Emission Mask")

    if finish == "GLITTER" and F.ROLE_GLITTER in sticker.textures:
        glit = tex_node(F.ROLE_GLITTER, -300)
        if glit:
            wire(glit.outputs["Color"], "Glitter Mask")
    if finish == "GLITTER" and F.ROLE_FLAKES in sticker.textures:
        _wire_flakes(nodes, links, tex_node, wire, grp)

    if finish == "HOLO" or (finish == "LENTICULAR" and not lenticular_strip):
        _wire_holo(sticker, nodes, links, tex_node, wire)

    _apply_params(sticker, grp)
    mat.diffuse_color = (0.8, 0.8, 0.8, 1.0)
    return mat, warnings


def _wire_flakes(nodes, links, tex_node, wire, grp):
    """Tiled CS2 flake normal -> Flake Normal (procedural flakes otherwise)."""
    coord = nodes.new("ShaderNodeTexCoord")
    coord.location = (-950, -900)
    tiling = nodes.new("ShaderNodeMapping")
    tiling.label = "Flake Tiling"
    tiling.location = (-750, -900)
    tiling.inputs["Scale"].default_value = (FLAKE_TILING,) * 3
    links.new(coord.outputs["UV"], tiling.inputs["Vector"])
    flakes = tex_node(F.ROLE_FLAKES, -900, tiling.outputs["Vector"])
    if flakes is None:
        nodes.remove(tiling)
        nodes.remove(coord)
        return
    flakes.extension = "REPEAT"
    wire(flakes.outputs["Color"], "Flake Normal")
    _set_input(grp, "Use Flake Texture", 1.0)


def _wire_holo(sticker, nodes, links, tex_node, wire):
    """holomask -> Holo Coords -> spectrum (texture or procedural) -> group."""
    coords = nodes.new("ShaderNodeGroup")
    coords.node_tree = groups.ensure_group("HOLO_COORDS")
    coords.location = (-750, -500)
    mask = tex_node(F.ROLE_HOLOMASK, -300)
    if mask:
        links.new(mask.outputs["Color"], coords.inputs["Holo Mask"])
        wire(mask.outputs["Color"], "Holo Mask")
        wire(mask.outputs["Alpha"], "Holo Mask Alpha")

    spec = tex_node(F.ROLE_HOLOSPECTRUM, -650, coords.outputs["Vector"])
    if spec:
        spec.extension = "REPEAT"
        wire(spec.outputs["Color"], "Spectrum Color")
    else:
        proc = nodes.new("ShaderNodeGroup")
        proc.node_tree = groups.ensure_group("HOLO_SPECTRUM")
        proc.location = (-450, -650)
        links.new(coords.outputs["Vector"], proc.inputs["Vector"])
        wire(proc.outputs["Color"], "Spectrum Color")


def _steep_face_cutoff(nodes, links, alpha):
    """Hide the sticker on faces that stand steep to its projection
    direction. Shrinkwrap pulls the plane over steps and pins of the target,
    which leaves stretched, streaky walls; projected decals in CS2 fade
    there as well. Returns the masked alpha socket."""
    def node(kind, x, y, **props):
        n = nodes.new(kind)
        n.location = (x, y)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    geo = node("ShaderNodeNewGeometry", -1100, 900)
    facing = node("ShaderNodeVectorTransform", -1100, 700, vector_type="VECTOR",
                  convert_from="OBJECT", convert_to="WORLD")
    facing.inputs["Vector"].default_value = (0.0, 0.0, 1.0)
    unit = node("ShaderNodeVectorMath", -900, 700, operation="NORMALIZE")
    links.new(facing.outputs["Vector"], unit.inputs[0])
    dot = node("ShaderNodeVectorMath", -700, 800, operation="DOT_PRODUCT")
    links.new(geo.outputs["True Normal"], dot.inputs[0])
    links.new(unit.outputs["Vector"], dot.inputs[1])
    ramp = node("ShaderNodeMapRange", -500, 800, clamp=True, label=STEEP_FACES_LABEL)
    links.new(dot.outputs["Value"], ramp.inputs["Value"])
    ramp.inputs["From Min"].default_value = STEEP_FROM
    ramp.inputs["From Max"].default_value = STEEP_TO
    mul = node("ShaderNodeMath", -300, 600, operation="MULTIPLY")
    links.new(alpha, mul.inputs[0])
    links.new(ramp.outputs["Result"], mul.inputs[1])
    # Hide what the projection missed (attribute is 0 / absent otherwise).
    missed = node("ShaderNodeAttribute", -700, 1000, attribute_type="GEOMETRY",
                  attribute_name=UNPROJECTED_ATTRIBUTE, label="Off Surface")
    keep = node("ShaderNodeMath", -500, 1000, operation="SUBTRACT", use_clamp=True)
    keep.inputs[0].default_value = 1.0
    links.new(missed.outputs["Fac"], keep.inputs[1])
    final = node("ShaderNodeMath", -150, 700, operation="MULTIPLY")
    links.new(mul.outputs[0], final.inputs[0])
    links.new(keep.outputs[0], final.inputs[1])
    return final.outputs[0]


def sticker_seed(sticker_id):
    """Stable per-sticker wear seed (0..99.9), so every sticker gets its own
    wear / scratch pattern without manual tweaking."""
    return (zlib.crc32(sticker_id.encode("utf-8")) % 1000) / 10.0


def _set_input(grp, key, value):
    sock = grp.inputs.get(key)
    if sock is None or sock.is_linked or not hasattr(sock, "default_value"):
        return False
    try:
        sock.default_value = value
    except (TypeError, ValueError):
        return False
    return True


def _apply_params(sticker, grp):
    """Catalog ``params`` whose key matches a group input set its default,
    e.g. {"Holo Strength": 0.8}. Other keys (vmat values) are ignored."""
    _set_input(grp, "Wear Seed", sticker_seed(sticker.id))
    for key, value in sticker.params.items():
        _set_input(grp, key, value)


def sticker_group_node(mat):
    """The finish group node of a sticker material (or None)."""
    if mat is None or not mat.node_tree:
        return None
    return mat.node_tree.nodes.get(utils.STICKER_NODE_NAME)
