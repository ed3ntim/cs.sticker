# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Stickers inside the material of another mesh ("In Material" placement).

cs.weapon draws stickers into the weapon material through the weapon's
sticker UV map, like CS2. Arbitrary meshes have no such UV map, so here a
projector (an Empty, display type Cube) carries the sticker like a decal:

* Texture Coordinate > Object with the projector gives every surface point
  in the projector's space. The box is -1..1 on all axes (scale x/y = half
  the sticker size, z = half the projection depth), so the sticker UV is
  ``xy * 0.5 + 0.5`` and points with |z| > 1 are outside.
* Faces turned away from the projector (or standing steep to it) are
  masked like the steep-face cutoff of mesh stickers, so the sticker does
  not show on the back side of thin parts.
* The projector's world X and Z axes come in through drivers on its
  matrix_world. X is the decal tangent the finish groups use for normal
  maps and view-angle effects (the target's own UV has nothing to do with
  the sticker), Z is the projection direction for the facing mask.

All of it lives in one node group per sticker ("CS2 Decal <name>", Shader
in, Shader out). The target material gets one group node between its
shader and the Material Output; several stickers chain. Moving, rotating
or scaling the projector updates the sticker live, nothing is rebuilt.
"""

import bpy

from .. import utils
from . import material as M

DECAL_PREFIX = "CS2 Decal "
PROP_DECAL = "cs_sticker_decal"  # on decal node groups
COORDS_NODE = "DECAL_COORDS"
AXIS_NODES = {"AXIS_X": 0, "AXIS_Z": 2}  # node name -> matrix_world column
FALLBACK_MATERIAL = "CS2 Surface"


# ---------------------------------------------------------------------------
# Decal node group
# ---------------------------------------------------------------------------

def _node(tree, kind, x, y, name="", label="", **props):
    n = tree.nodes.new(kind)
    n.location = (x, y)
    if name:
        n.name = name
    if label:
        n.label = label
    for key, value in props.items():
        setattr(n, key, value)
    return n


def _math(tree, op, a, b, x, y, clamp=False):
    n = _node(tree, "ShaderNodeMath", x, y, operation=op, use_clamp=clamp)
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = float(v)
        else:
            tree.links.new(v, n.inputs[i])
    return n.outputs[0]


def _axis_node(tree, name, column, projector, x, y):
    """Combine XYZ whose inputs follow one world axis of ``projector``."""
    comb = _node(tree, "ShaderNodeCombineXYZ", x, y, name=name, label=name.replace("_", " ").title())
    for i in range(3):
        drv = comb.inputs[i].driver_add("default_value").driver
        drv.type = "AVERAGE"  # no Python expression, works without auto-run
        var = drv.variables.new()
        var.name = "axis"
        var.type = "SINGLE_PROP"
        var.targets[0].id_type = "OBJECT"
        var.targets[0].id = projector
        var.targets[0].data_path = f"matrix_world[{column}][{i}]"
    return comb


def build_group(sticker, projector):
    """Create the decal node group of ``sticker`` projected by ``projector``.
    Returns (group, warnings)."""
    warnings = []
    tree = bpy.data.node_groups.new(f"{DECAL_PREFIX}{sticker.name}", "ShaderNodeTree")
    tree[PROP_DECAL] = True
    tree[utils.PROP_STICKER_ID] = sticker.id
    iface = tree.interface
    iface.new_socket("Shader", in_out="INPUT", socket_type="NodeSocketShader")
    iface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    links = tree.links
    gin = _node(tree, "NodeGroupInput", -2200, 600)
    gout = _node(tree, "NodeGroupOutput", 900, 0)

    coords = _node(tree, "ShaderNodeTexCoord", -2200, 200, name=COORDS_NODE, label="Projector")
    coords.object = projector
    sep = _node(tree, "ShaderNodeSeparateXYZ", -2000, 200)
    links.new(coords.outputs["Object"], sep.inputs[0])
    u = _math(tree, "MULTIPLY_ADD", sep.outputs["X"], 0.5, -1800, 300)
    u.node.inputs[2].default_value = 0.5
    v = _math(tree, "MULTIPLY_ADD", sep.outputs["Y"], 0.5, -1800, 150)
    v.node.inputs[2].default_value = 0.5
    uv = _node(tree, "ShaderNodeCombineXYZ", -1600, 250, name="DECAL_UV", label="Sticker UV")
    links.new(u, uv.inputs[0])
    links.new(v, uv.inputs[1])
    # Inside the projection depth: |z| < 1.
    depth = _math(tree, "LESS_THAN", _math(tree, "ABSOLUTE", sep.outputs["Z"], None, -1800, 0),
                  1.0, -1600, 0)

    axis_x = _axis_node(tree, "AXIS_X", AXIS_NODES["AXIS_X"], projector, -2000, -300)
    axis_z = _axis_node(tree, "AXIS_Z", AXIS_NODES["AXIS_Z"], projector, -2000, -500)
    tangent = _node(tree, "ShaderNodeVectorMath", -1800, -300, operation="NORMALIZE")
    links.new(axis_x.outputs[0], tangent.inputs[0])
    facing_dir = _node(tree, "ShaderNodeVectorMath", -1800, -500, operation="NORMALIZE")
    links.new(axis_z.outputs[0], facing_dir.inputs[0])
    geo = _node(tree, "ShaderNodeNewGeometry", -1800, -700)
    dot = _node(tree, "ShaderNodeVectorMath", -1600, -550, operation="DOT_PRODUCT")
    links.new(geo.outputs["True Normal"], dot.inputs[0])
    links.new(facing_dir.outputs["Vector"], dot.inputs[1])
    facing = _node(tree, "ShaderNodeMapRange", -1400, -550, clamp=True, label=M.STEEP_FACES_LABEL)
    links.new(dot.outputs["Value"], facing.inputs["Value"])
    facing.inputs["From Min"].default_value = M.STEEP_FROM
    facing.inputs["From Max"].default_value = M.STEEP_TO
    coverage = _math(tree, "MULTIPLY", depth, facing.outputs["Result"], -1200, -300)
    coverage.node.label = "Projection Mask"

    def mask(_nodes, _links, alpha):
        return _math(tree, "MULTIPLY", alpha, coverage, -100, 600)

    grp = M.add_sticker_nodes(tree, sticker, warnings, mask=mask, vector=uv.outputs[0],
                              tangent=tangent.outputs["Vector"], origin=(-300, 0))
    mix = _node(tree, "ShaderNodeMixShader", 650, 0, name="DECAL_MIX")
    links.new(grp.outputs["Alpha"], mix.inputs[0])
    links.new(gin.outputs[0], mix.inputs[1])
    links.new(grp.outputs["Shader"], mix.inputs[2])
    links.new(mix.outputs[0], gout.inputs[0])
    return tree, warnings


def projector_of(tree):
    """Projector object of a decal group (None if gone)."""
    coords = tree.nodes.get(COORDS_NODE) if tree is not None else None
    return coords.object if coords is not None else None


def set_projector(tree, projector):
    """Point a decal group (coordinates and axis drivers) at ``projector``."""
    coords = tree.nodes.get(COORDS_NODE)
    if coords is not None:
        coords.object = projector
    anim = tree.animation_data
    for fc in (anim.drivers if anim else ()):
        for var in fc.driver.variables:
            var.targets[0].id = projector


def sticker_group_node(tree):
    """Finish group node inside a decal group (or None)."""
    return tree.nodes.get(utils.STICKER_NODE_NAME) if tree is not None else None


def is_decal_group(tree):
    return tree is not None and bool(tree.get(PROP_DECAL))


# ---------------------------------------------------------------------------
# Target materials
# ---------------------------------------------------------------------------

def _output(tree):
    outs = [n for n in tree.nodes if n.type == "OUTPUT_MATERIAL"]
    for n in outs:
        if n.is_active_output:
            return n
    return outs[0] if outs else None


def _fallback_material():
    mat = bpy.data.materials.new(FALLBACK_MATERIAL)
    if not getattr(mat, "use_nodes", True):
        mat.use_nodes = True
    return mat


def target_materials(target, create=True):
    """Materials the sticker goes into: every material of ``target``. A mesh
    without material gets a plain one (``create``)."""
    mats = []
    for slot in target.material_slots:
        if slot.material is not None and slot.material not in mats:
            mats.append(slot.material)
    if not mats and create and target.type == "MESH":
        mat = _fallback_material()
        if len(target.material_slots):
            target.material_slots[0].material = mat
        else:
            target.data.materials.append(mat)
        mats.append(mat)
    return mats


def layer_nodes(mat, tree=None):
    """Decal group nodes in ``mat`` (only those of ``tree`` if given)."""
    nt = mat.node_tree if mat is not None else None
    if nt is None:
        return []
    return [n for n in nt.nodes if n.type == "GROUP" and n.node_tree is not None
            and is_decal_group(n.node_tree) and (tree is None or n.node_tree == tree)]


def insert(mat, tree, label=""):
    """Put the decal group between the material's shader and its output.
    Returns the group node (existing one if already there)."""
    if not getattr(mat, "use_nodes", True):
        # Blender 4.x material without nodes: keep its color in the BSDF.
        mat.use_nodes = True
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                n.inputs["Base Color"].default_value = mat.diffuse_color
    nt = mat.node_tree
    existing = layer_nodes(mat, tree)
    if existing:
        return existing[0]
    out = _output(nt)
    if out is None:
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        out.location = (300, 0)
    surface = out.inputs["Surface"]
    src = surface.links[0].from_socket if surface.is_linked else None
    if src is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (out.location.x - 400, out.location.y)
        src = bsdf.outputs[0]
    node = nt.nodes.new("ShaderNodeGroup")
    node.node_tree = tree
    node.label = label or tree.name
    node.width = 220
    node.location = (out.location.x, out.location.y)
    out.location = (out.location.x + 280, out.location.y)
    nt.links.new(src, node.inputs[0])
    nt.links.new(node.outputs[0], surface)
    return node


def _bypass(nt, node):
    src = node.inputs[0].links[0].from_socket if node.inputs[0].is_linked else None
    targets = [link.to_socket for link in node.outputs[0].links]
    nt.nodes.remove(node)
    if src is not None:
        for sock in targets:
            nt.links.new(src, sock)


def detach(tree, materials=None):
    """Take the decal group out of ``materials`` (default: all materials)."""
    for mat in (materials if materials is not None else bpy.data.materials):
        for node in layer_nodes(mat, tree):
            _bypass(mat.node_tree, node)


def materials_with(tree):
    return [m for m in bpy.data.materials if layer_nodes(m, tree)]


def attach(tree, target, label=""):
    """Insert the decal group into every material of ``target``."""
    mats = target_materials(target)
    for mat in mats:
        insert(mat, tree, label)
    return mats


def remove(tree):
    """Detach the decal group everywhere and delete it."""
    detach(tree)
    bpy.data.node_groups.remove(tree)


def remove_orphans():
    """Remove decal groups whose projector is gone (deleted Empty).
    Returns the number removed."""
    removed = 0
    for tree in [t for t in bpy.data.node_groups if is_decal_group(t)]:
        projector = projector_of(tree)
        # The node keeps a deleted object alive, so check for a scene.
        if projector is None or not projector.users_scene:
            remove(tree)
            removed += 1
    return removed
