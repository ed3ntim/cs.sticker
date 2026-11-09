# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""In-material stickers (nodes/decal.py): projector, target materials,
live axes, cleanup and an actual render of the projection."""

import math
import os
import tempfile
import unittest

import bpy
from mathutils import Matrix, Vector

from cs_sticker import utils
from cs_sticker.library import registry
from cs_sticker.nodes import decal as D
from cs_sticker.nodes import groups
from cs_sticker.ops import placement as P
from cs_sticker.ops import sticker_ops

from test_blender import add_cube, reset_scene, select_sticker


def spawn_decal(sticker_id="demo_paper_star", target=None):
    """Spawn into the material of ``target`` (default: a new cube) at +X."""
    if target is None:
        target = add_cube()
    bpy.context.scene.cs_sticker_place.method = "MATERIAL"
    bpy.context.scene.cursor.location = (3.0, 0.0, 0.0)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    select_sticker(sticker_id)
    result = bpy.ops.cs_sticker.spawn(mode="SURFACE")
    assert result == {"FINISHED"}, result
    return bpy.context.active_object, target


def surface_source(mat):
    """Node feeding the active Material Output."""
    out = [n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL"][0]
    return out.inputs["Surface"].links[0].from_node


class TestDecal(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.addCleanup(setattr, bpy.context.scene.cs_sticker_place, "method", "MESH")

    def test_spawn_into_material(self):
        obj, cube = spawn_decal()
        self.assertEqual(obj.type, "EMPTY")
        self.assertTrue(utils.is_decal(obj))
        self.assertEqual(obj.parent, cube)
        tree = P.decal_group(obj)
        self.assertTrue(D.is_decal_group(tree))
        self.assertEqual(D.projector_of(tree), obj)
        # Cube had no material: one was added and holds the sticker.
        self.assertEqual(len(cube.data.materials), 1)
        mat = cube.data.materials[0]
        node = surface_source(mat)
        self.assertEqual(node.node_tree, tree)
        self.assertEqual(node.inputs[0].links[0].from_node.bl_idname, "ShaderNodeBsdfPrincipled")
        # Facing the +X face, box centered on it.
        z = obj.matrix_world.to_3x3() @ Vector((0, 0, 1))
        self.assertAlmostEqual(z.normalized().x, 1.0, places=4)
        self.assertAlmostEqual(obj.matrix_world.translation.x, 1.0, places=4)
        width = P.sticker_width(bpy.context.scene.cs_sticker_place, cube)
        self.assertAlmostEqual(obj.matrix_world.to_scale().x, width / 2.0, places=5)
        self.assertEqual(P.decal_target(obj), cube)

    def test_existing_material_kept(self):
        cube = add_cube()
        mat = bpy.data.materials.new("Paint")
        if not getattr(mat, "use_nodes", True):
            mat.use_nodes = True  # Blender 4.x
        cube.data.materials.append(mat)
        bsdf = [n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"][0]
        obj, _ = spawn_decal(target=cube)
        self.assertEqual(list(cube.data.materials), [mat])
        node = surface_source(mat)
        self.assertEqual(node.inputs[0].links[0].from_node, bsdf)

    def test_material_without_nodes_keeps_color(self):
        mat = bpy.data.materials.new("Flat")
        if hasattr(mat, "use_nodes"):
            mat.use_nodes = False
        if getattr(mat, "use_nodes", True):
            self.skipTest("materials always use nodes in this Blender version")
        mat.diffuse_color = (0.9, 0.1, 0.1, 1.0)
        cube = add_cube()
        cube.data.materials.append(mat)
        spawn_decal(target=cube)
        bsdf = surface_source(mat).inputs[0].links[0].from_node
        self.assertEqual(bsdf.bl_idname, "ShaderNodeBsdfPrincipled")
        self.assertAlmostEqual(bsdf.inputs["Base Color"].default_value[0], 0.9, places=4)

    def test_finishes_wire_the_decal_frame(self):
        for sticker in registry.get_catalog().filter(collection="Demo Capsule"):
            obj, _ = spawn_decal(sticker.id)
            tree = P.decal_group(obj)
            grp = D.sticker_group_node(tree)
            self.assertIsNotNone(grp, sticker.name)
            for name in ("Decal UV", "Decal Tangent", "Base Color", "Alpha"):
                self.assertTrue(grp.inputs[name].is_linked, f"{sticker.name}: {name}")
            mix = tree.nodes["DECAL_MIX"]
            self.assertEqual(mix.inputs[0].links[0].from_socket.name, "Alpha")
            for n in tree.nodes:
                if n.bl_idname == "ShaderNodeTexImage":
                    self.assertTrue(n.inputs["Vector"].is_linked, f"{sticker.name}: {n.label} on mesh UV")
            reset_scene()

    def test_axes_follow_projector(self):
        obj, _ = spawn_decal()
        obj.parent = None
        obj.matrix_world = Matrix.LocRotScale((0, 0, 0), Matrix.Rotation(math.radians(90), 3, "Z")
                                              .to_quaternion(), (0.5, 0.25, 0.1))
        bpy.context.view_layer.update()
        tree = P.decal_group(obj)
        ax = Vector([s.default_value for s in tree.nodes["AXIS_X"].inputs[:3]]).normalized()
        az = Vector([s.default_value for s in tree.nodes["AXIS_Z"].inputs[:3]]).normalized()
        self.assertAlmostEqual(ax.y, 1.0, places=4)
        self.assertAlmostEqual(az.z, 1.0, places=4)

    def test_chain_and_remove(self):
        a, cube = spawn_decal()
        b, _ = spawn_decal("demo_holo_rings", target=cube)
        mat = cube.data.materials[0]
        tree_a, tree_b = P.decal_group(a), P.decal_group(b)
        self.assertEqual(surface_source(mat).node_tree, tree_b)
        self.assertEqual(surface_source(mat).inputs[0].links[0].from_node.node_tree, tree_a)
        bpy.context.view_layer.objects.active = a
        for o in bpy.context.selected_objects:
            o.select_set(False)
        a.select_set(True)
        self.assertEqual(bpy.ops.cs_sticker.remove_decal(), {"FINISHED"})
        self.assertEqual(surface_source(mat).node_tree, tree_b)
        self.assertEqual(surface_source(mat).inputs[0].links[0].from_node.bl_idname,
                         "ShaderNodeBsdfPrincipled")

    def test_deleted_projector_cleans_up(self):
        obj, cube = spawn_decal()
        name = P.decal_group(obj).name
        bpy.data.objects.remove(obj, do_unlink=True)
        sticker_ops.sync()
        self.assertIsNone(bpy.data.node_groups.get(name))
        mat = cube.data.materials[0]
        self.assertEqual(surface_source(mat).bl_idname, "ShaderNodeBsdfPrincipled")

    def test_unlinked_projector_cleans_up(self):
        # bpy.ops.object.delete only unlinks while the node still uses it.
        obj, cube = spawn_decal()
        name = P.decal_group(obj).name
        for coll in list(obj.users_collection):
            coll.objects.unlink(obj)
        sticker_ops.sync()
        self.assertIsNone(bpy.data.node_groups.get(name))

    def test_duplicate_gets_own_group(self):
        obj, cube = spawn_decal()
        dup = obj.copy()
        obj.users_collection[0].objects.link(dup)
        self.assertTrue(sticker_ops.own_group(dup))
        tree, copy = P.decal_group(obj), P.decal_group(dup)
        self.assertNotEqual(tree, copy)
        self.assertEqual(D.projector_of(copy), dup)
        for fc in copy.animation_data.drivers:
            self.assertEqual(fc.driver.variables[0].targets[0].id, dup)
        self.assertEqual(D.materials_with(copy), D.materials_with(tree))
        self.assertFalse(sticker_ops.own_group(dup))

    def test_retarget(self):
        obj, cube = spawn_decal()
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(5, 0, 0))
        other = bpy.context.active_object
        for o in bpy.context.selected_objects:
            o.select_set(False)
        other.select_set(True)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        self.assertEqual(bpy.ops.cs_sticker.retarget(), {"FINISHED"})
        tree = P.decal_group(obj)
        self.assertEqual(D.materials_with(tree), [other.data.materials[0]])
        self.assertEqual(D.layer_nodes(cube.data.materials[0]), [])
        self.assertEqual(obj.parent, other)

    def test_rotate_keeps_box(self):
        obj, _ = spawn_decal()
        scale = obj.matrix_world.to_scale()
        bpy.context.view_layer.objects.active = obj
        bpy.ops.cs_sticker.rotate(angle=math.radians(90))
        new = obj.matrix_world.to_scale()
        for a, b in zip(scale, new):
            self.assertAlmostEqual(a, b, places=5)

    def test_mesh_mode_groups_unchanged(self):
        # Unlinked decal inputs: the group must not switch to decal mode.
        tree = groups.ensure_group("PAPER")
        names = [s.name for s in tree.interface.items_tree if s.item_type == "SOCKET"]
        self.assertIn("Decal Tangent", names)
        self.assertIn("Alpha", [s.name for s in tree.interface.items_tree
                                if s.item_type == "SOCKET" and s.in_out == "OUTPUT"])


class TestDecalRender(unittest.TestCase):
    """Render the +X face of a cube head-on, with and without the sticker."""

    def setUp(self):
        reset_scene()
        self.addCleanup(setattr, bpy.context.scene.cs_sticker_place, "method", "MESH")

    def _render(self, path):
        scene = bpy.context.scene
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 4
        scene.cycles.device = "CPU"
        scene.render.resolution_x = scene.render.resolution_y = 48
        scene.render.resolution_percentage = 100
        scene.render.filepath = path
        scene.render.image_settings.file_format = "PNG"
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(path)
        px = list(img.pixels)
        w = img.size[0]
        bpy.data.images.remove(img)
        return lambda x, y: px[(y * w + x) * 4:(y * w + x) * 4 + 3]

    def test_sticker_visible_in_center_only(self):
        scene = bpy.context.scene
        cube = add_cube()
        mat = bpy.data.materials.new("Paint")
        cube.data.materials.append(mat)
        world = bpy.data.worlds.new("W")
        scene.world = world
        world.color = (1, 1, 1)
        cam_data = bpy.data.cameras.new("Cam")
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = 1.0
        cam = bpy.data.objects.new("Cam", cam_data)
        scene.collection.objects.link(cam)
        cam.location = (5, 0, 0)
        cam.rotation_euler = (math.radians(90), 0, math.radians(90))
        scene.camera = cam
        settings = scene.cs_sticker_place
        settings.size_mode = "ABSOLUTE"
        settings.size = 0.5
        settings.project_limit = 10.0  # box reaches through the cube: facing mask must hide the back
        self.addCleanup(settings.property_unset, "project_limit")

        tmp = tempfile.mkdtemp()
        before = self._render(os.path.join(tmp, "before.png"))
        obj, _ = spawn_decal(target=cube)
        after = self._render(os.path.join(tmp, "after.png"))

        def diff(x, y):
            return sum(abs(a - b) for a, b in zip(before(x, y), after(x, y)))

        # Sticker 0.5 wide in a 1.0 view: center changes, corners do not.
        self.assertGreater(max(diff(x, y) for x in range(20, 28) for y in range(20, 28)), 0.1)
        for x, y in ((1, 1), (46, 1), (1, 46), (46, 46)):
            self.assertLess(diff(x, y), 0.05, (x, y))

        # The back (-X) face shares the material but must stay clean.
        cam.location = (-5, 0, 0)
        cam.rotation_euler = (math.radians(90), 0, math.radians(-90))
        back_before_mat = self._render(os.path.join(tmp, "back.png"))
        D.detach(P.decal_group(obj))
        back_clean = self._render(os.path.join(tmp, "back_clean.png"))
        worst = max(sum(abs(a - b) for a, b in zip(back_before_mat(x, y), back_clean(x, y)))
                    for x in range(0, 48, 4) for y in range(0, 48, 4))
        self.assertLess(worst, 0.05)
