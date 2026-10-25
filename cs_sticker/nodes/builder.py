# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Thin helpers around the node API that keep the group builders readable
and survive socket layout differences between Blender versions.

Multi-type nodes (Mix, Vector Math, Map Range) have several sockets with the
same name of which only some are enabled for the current data type, so
sockets are always looked up by name among the *enabled* ones.
"""

import bpy


def _available(sock):
    return getattr(sock, "enabled", True) and not getattr(sock, "is_unavailable", False)


def find_socket(sockets, key):
    """Socket by index, identifier or name (enabled sockets preferred)."""
    if isinstance(key, int):
        return sockets[key]
    for s in sockets:
        if s.identifier == key and _available(s):
            return s
    for s in sockets:
        if s.name == key and _available(s):
            return s
    for s in sockets:
        if s.name == key:
            return s
    raise KeyError(f"socket '{key}' not found on {sockets[0].node.bl_idname if len(sockets) else '?'}")


class GroupBuilder:
    """Builds the contents of one shader node group."""

    def __init__(self, tree):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links
        self.gin = self.nodes.new("NodeGroupInput")
        self.gout = self.nodes.new("NodeGroupOutput")
        self.gin.location = (-1200, 0)
        self.gout.location = (900, 0)
        self._x = -900

    # -- interface -----------------------------------------------------------

    def input(self, name, kind="FLOAT", default=None, lo=None, hi=None, factor=False,
              hide_value=False, description=""):
        socket_type = {
            "FLOAT": "NodeSocketFloat", "COLOR": "NodeSocketColor",
            "VECTOR": "NodeSocketVector", "INT": "NodeSocketInt",
            "SHADER": "NodeSocketShader",
        }[kind]
        sock = self.tree.interface.new_socket(name=name, in_out="INPUT", socket_type=socket_type)
        if description:
            sock.description = description
        if kind == "FLOAT" and factor:
            try:
                sock.subtype = "FACTOR"
            except (AttributeError, TypeError):
                pass
        if default is not None and hasattr(sock, "default_value"):
            sock.default_value = default
        if lo is not None and hasattr(sock, "min_value"):
            sock.min_value = lo
        if hi is not None and hasattr(sock, "max_value"):
            sock.max_value = hi
        if hide_value:
            sock.hide_value = True
        return self.gin.outputs[name]

    def output(self, name, kind="SHADER"):
        socket_type = {
            "FLOAT": "NodeSocketFloat", "COLOR": "NodeSocketColor",
            "VECTOR": "NodeSocketVector", "SHADER": "NodeSocketShader",
        }[kind]
        self.tree.interface.new_socket(name=name, in_out="OUTPUT", socket_type=socket_type)
        return self.gout.inputs[name]

    # -- nodes -----------------------------------------------------------------

    def node(self, bl_idname, x=None, y=0, label="", **props):
        n = self.nodes.new(bl_idname)
        for key, value in props.items():
            setattr(n, key, value)
        n.location = (self._x if x is None else x, y)
        if label:
            n.label = label
        return n

    def link(self, src, dst):
        """Link sockets; ``src``/``dst`` may be sockets or (node, key) tuples."""
        if isinstance(src, tuple):
            src = find_socket(src[0].outputs, src[1])
        if isinstance(dst, tuple):
            dst = find_socket(dst[0].inputs, dst[1])
        self.links.new(src, dst)

    def set_or_link(self, node, key, value):
        """Link ``value`` if it is a socket or a (node, output key) tuple,
        otherwise set it as the socket's default value."""
        sock = find_socket(node.inputs, key)
        if isinstance(value, tuple) and value and isinstance(value[0], bpy.types.Node):
            value = find_socket(value[0].outputs, value[1])
        if isinstance(value, bpy.types.NodeSocket):
            self.links.new(value, sock)
        elif value is not None:
            sock.default_value = value
        return sock

    # Shorthands that return the *output socket* of a new node.

    def math(self, op, a, b=None, x=None, y=0, clamp=False):
        n = self.node("ShaderNodeMath", x, y, operation=op, use_clamp=clamp)
        self.set_or_link(n, 0, a)
        if b is not None:
            self.set_or_link(n, 1, b)
        return n.outputs[0]

    def vmath(self, op, a, b=None, x=None, y=0, scale=None):
        n = self.node("ShaderNodeVectorMath", x, y, operation=op)
        self.set_or_link(n, 0, a)
        if b is not None:
            self.set_or_link(n, 1, b)
        if scale is not None:
            self.set_or_link(n, "Scale", scale)
        out = "Value" if op in ("DOT_PRODUCT", "DISTANCE", "LENGTH") else "Vector"
        return find_socket(n.outputs, out)

    def mix(self, data_type, fac, a, b, x=None, y=0, blend="MIX", clamp=True):
        n = self.node("ShaderNodeMix", x, y, data_type=data_type)
        if data_type == "RGBA":
            n.blend_type = blend
            n.clamp_result = clamp
        n.clamp_factor = True
        self.set_or_link(n, "Factor", fac)
        self.set_or_link(n, "A", a)
        self.set_or_link(n, "B", b)
        return find_socket(n.outputs, "Result")

    def map_range(self, value, from_min, from_max, to_min=0.0, to_max=1.0, x=None, y=0,
                  interpolation="LINEAR"):
        n = self.node("ShaderNodeMapRange", x, y, interpolation_type=interpolation, clamp=True)
        for key, v in (("Value", value), ("From Min", from_min), ("From Max", from_max),
                       ("To Min", to_min), ("To Max", to_max)):
            self.set_or_link(n, key, v)
        return find_socket(n.outputs, "Result")

    def separate(self, vector, x=None, y=0):
        n = self.node("ShaderNodeSeparateXYZ", x, y)
        self.set_or_link(n, 0, vector)
        return n.outputs["X"], n.outputs["Y"], n.outputs["Z"]

    def combine(self, vx=0.0, vy=0.0, vz=0.0, x=None, y=0):
        n = self.node("ShaderNodeCombineXYZ", x, y)
        for i, v in enumerate((vx, vy, vz)):
            self.set_or_link(n, i, v)
        return n.outputs[0]

    def separate_color(self, color, x=None, y=0):
        n = self.node("ShaderNodeSeparateColor", x, y)
        self.set_or_link(n, 0, color)
        return n.outputs[0], n.outputs[1], n.outputs[2]

    def subgroup(self, tree, inputs, x=None, y=0):
        """Instance another node group and wire ``inputs`` (name -> value)."""
        n = self.node("ShaderNodeGroup", x, y)
        n.node_tree = tree
        for key, value in inputs.items():
            self.set_or_link(n, key, value)
        return n

    def column(self, x):
        """Move the default x position for following nodes."""
        self._x = x


def principled(b, x=500, y=0):
    """Principled BSDF with sane sticker defaults."""
    n = b.node("ShaderNodeBsdfPrincipled", x, y)
    if hasattr(n, "distribution"):
        n.distribution = "MULTI_GGX"
    return n


def set_bsdf(b, bsdf, **values):
    """Set/link Principled inputs by readable keyword (underscores = spaces).
    Unknown sockets are skipped, so newer/older Blender versions still work."""
    for key, value in values.items():
        name = key.replace("_", " ")
        try:
            b.set_or_link(bsdf, name, value)
        except KeyError:
            pass
