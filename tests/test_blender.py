# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Integration tests inside Blender: registration, node groups, materials,
spawning and placement math. Run through tests/run_tests.py."""

import json
import math
import os
import tempfile
import unittest

import bpy
from mathutils import Vector

import cs_sticker
from cs_sticker import utils
from cs_sticker.library import finishes as F
from cs_sticker.library import registry
from cs_sticker.nodes import groups, material
from cs_sticker.ops import placement as P


def reset_scene():
    # Not read_factory_settings: that would also reset preferences and
    # disable the add-on under test.
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials,
                 bpy.data.node_groups, bpy.data.images, bpy.data.collections):
        for block in list(coll):
            coll.remove(block)
    scene = bpy.context.scene
    scene.cursor.location = (0, 0, 0)
    scene.cs_sticker_place.attach = "PARENT"
    registry.refresh(bpy.context)


def add_cube():
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 0))
    cube = bpy.context.active_object
    cube.select_set(True)
    return cube


def select_sticker(sticker_id):
    state = bpy.context.window_manager.cs_sticker
    for i, item in enumerate(state.items):
        if item.sticker_id == sticker_id:
            state.index = i
            return
    raise AssertionError(f"{sticker_id} not in list")


class TestRegistration(unittest.TestCase):
    def test_registered(self):
        self.assertTrue(hasattr(bpy.types.WindowManager, "cs_sticker"))
        self.assertTrue(hasattr(bpy.types.Scene, "cs_sticker_place"))
        for op in ("spawn", "place_interactive", "refresh_library", "add_folder",
                   "rotate", "make_unique", "retarget"):
            self.assertTrue(hasattr(bpy.ops.cs_sticker, op), op)
        self.assertIsNotNone(utils.get_prefs(), "add-on preferences not available")

    def test_icons_exist(self):
        icons = bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items.keys()
        for f in F.FINISHES.values():
            self.assertIn(f.icon, icons, f.id)

    def test_reregister(self):
        cs_sticker.unregister()
        cs_sticker.register()
        registry.refresh(bpy.context)
        self.assertGreater(len(bpy.context.window_manager.cs_sticker.items), 0)


class TestNodeGroups(unittest.TestCase):
    def setUp(self):
        reset_scene()

    def test_all_groups_build(self):
        trees = groups.ensure_all()
        self.assertEqual(len(trees), 11)
        for key in groups.FINISH_GROUP_KEYS:
            tree = groups.ensure_group(key)
            names = [s.name for s in tree.interface.items_tree if s.item_type == "SOCKET"]
            for common in ("Base Color", "Alpha", "Normal Color", "Wear", "Alpha Clip", "Shader"):
                self.assertIn(common, names, f"{key}: {common}")
            bsdf = [n for n in tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"]
            self.assertEqual(len(bsdf), 1, key)
            self.assertTrue(bsdf[0].inputs["Alpha"].is_linked, f"{key}: alpha not wired")
            self.assertTrue(bsdf[0].inputs["Normal"].is_linked, f"{key}: normal not wired")

    def test_groups_are_reused(self):
        a = groups.ensure_group("HOLO")
        b = groups.ensure_group("HOLO")
        self.assertEqual(a, b)
        self.assertEqual(len([g for g in bpy.data.node_groups if g.name == groups.group_name("HOLO")]), 1)

    def test_outdated_group_replaced(self):
        old = groups.ensure_group("PAPER")
        old[groups.VERSION_KEY] = 0
        new = groups.ensure_group("PAPER")
        self.assertNotEqual(old, new)
        self.assertEqual(new.name, groups.group_name("PAPER"))
        self.assertTrue(old.name.endswith("(v0)"))


class TestMaterials(unittest.TestCase):
    def setUp(self):
        reset_scene()

    def test_material_per_finish(self):
        cat = registry.get_catalog()
        for s in cat.filter(collection="Demo Capsule"):
            mat, warnings = material.build_material(s)
            self.assertEqual(warnings, [], s.name)
            grp = material.sticker_group_node(mat)
            self.assertIsNotNone(grp, s.name)
            self.assertTrue(grp.inputs["Base Color"].is_linked)
            self.assertTrue(grp.inputs["Alpha"].is_linked)
            if F.ROLE_NORMAL in s.textures:
                self.assertTrue(grp.inputs["Normal Color"].is_linked, s.name)
            if s.finish == "HOLO":
                self.assertTrue(grp.inputs["Spectrum Color"].is_linked)
                self.assertTrue(grp.inputs["Holo Mask"].is_linked)
            if s.finish == "GLITTER":
                self.assertTrue(grp.inputs["Glitter Mask"].is_linked)
            imgs = [n.image for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeTexImage"]
            for img in imgs:
                if img.filepath.endswith(("normal.png", "holomask.png", "glitter.png")):
                    self.assertEqual(img.colorspace_settings.name, "Non-Color", img.name)

    def test_lenticular_frames(self):
        s = registry.get_catalog().get("demo_lenticular_eye")
        mat, _ = material.build_material(s)
        coords = [n for n in mat.node_tree.nodes
                  if n.bl_idname == "ShaderNodeGroup" and n.node_tree.name.endswith("Lenticular Coords")]
        self.assertEqual(len(coords), 1)
        self.assertEqual(coords[0].inputs["Frames"].default_value, 2.0)
        self.assertAlmostEqual(P.sticker_aspect(s), 1.0)

    def test_lenticular_cs2_mode(self):
        # CS2 lenticular = holo-style lookup: mask + spectrum, no frame strip.
        from cs_sticker.library.catalog import Sticker
        tex = os.path.join(utils.CORE_LIBRARY_DIR, "textures")
        s = Sticker(id="lenti", name="Lenti", collection="X", finish="LENTICULAR", textures={
            "base": os.path.join(tex, "demo_holo_rings_color.png"),
            "holomask": os.path.join(tex, "demo_holo_rings_holomask.png"),
            "holospectrum": os.path.join(tex, "demo_holo_rings_holospectrum.png"),
        })
        mat, warnings = material.build_material(s)
        self.assertEqual(warnings, [])
        trees = [n.node_tree.name for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeGroup"]
        self.assertIn("CS2 Holo Coords", trees)
        self.assertNotIn("CS2 Lenticular Coords", trees)
        grp = material.sticker_group_node(mat)
        self.assertTrue(grp.inputs["Spectrum Color"].is_linked)
        self.assertTrue(grp.inputs["Holo Mask"].is_linked)
        self.assertAlmostEqual(P.sticker_aspect(s), 1.0)

    def test_emission_mask(self):
        from cs_sticker.library.catalog import Sticker
        tex = os.path.join(utils.CORE_LIBRARY_DIR, "textures")
        s = Sticker(id="glow", name="Glow", collection="X", finish="PAPER", textures={
            "base": os.path.join(tex, "demo_paper_star_color.png"),
            "emission": os.path.join(tex, "demo_glitter_heart_glitter.png"),
        })
        mat, warnings = material.build_material(s)
        self.assertEqual(warnings, [])
        self.assertTrue(material.sticker_group_node(mat).inputs["Emission Mask"].is_linked)

    def test_missing_textures_fallback(self):
        from cs_sticker.library.catalog import Sticker
        s = Sticker(id="ghost", name="Ghost", collection="X", finish="HOLO",
                    textures={"base": "C:/nope/base.png", "holomask": "C:/nope/mask.png"})
        mat, warnings = material.build_material(s)
        self.assertTrue(any("required" in w for w in warnings))
        self.assertTrue(any("not found" in w for w in warnings))
        imgs = [n.image.name for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeTexImage"]
        self.assertEqual(imgs, [material.MISSING_IMAGE_NAME])

    def test_shared_material(self):
        s = registry.get_catalog().get("demo_paper_star")
        a, _ = material.build_material(s, unique=False)
        b, _ = material.build_material(s, unique=False)
        c, _ = material.build_material(s, unique=True)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


class TestPlacement(unittest.TestCase):
    def setUp(self):
        reset_scene()

    def test_orientation_matrix(self):
        m = P.orientation_matrix(Vector((1, 2, 3)), Vector((1, 0, 0)))
        self.assertAlmostEqual((m.to_3x3() @ Vector((0, 0, 1)) - Vector((1, 0, 0))).length, 0, 5)
        self.assertAlmostEqual((m.to_3x3() @ Vector((0, 1, 0)) - Vector((0, 0, 1))).length, 0, 5)
        self.assertAlmostEqual((m.translation - Vector((1, 2, 3))).length, 0, 5)
        # Floor: normal parallel to world up must not degenerate.
        m = P.orientation_matrix(Vector(), Vector((0, 0, 1)), math.radians(90))
        self.assertAlmostEqual(abs(m.to_3x3().determinant()), 1.0, 5)

    def test_spawn_surface(self):
        cube = add_cube()
        bpy.context.scene.cursor.location = (3, 0.2, 0.1)  # beside the +X face
        for s in registry.get_catalog().filter(collection="Demo Capsule"):
            select_sticker(s.id)
            cube.select_set(True)
            bpy.context.view_layer.objects.active = cube
            result = bpy.ops.cs_sticker.spawn(mode="SURFACE")
            self.assertEqual(result, {"FINISHED"}, s.name)
            obj = bpy.context.active_object
            self.assertTrue(utils.is_sticker(obj))
            self.assertEqual(obj[utils.PROP_STICKER_FINISH], s.finish)
            self.assertEqual([m.type for m in obj.modifiers], ["SUBSURF", "SHRINKWRAP"])
            self.assertEqual(obj.modifiers[1].target, cube)
            self.assertEqual(obj.parent, cube)
            loc = obj.matrix_world.translation
            self.assertAlmostEqual(loc.x, 1.0, 4, s.name)
            normal = obj.matrix_world.to_3x3() @ Vector((0, 0, 1))
            self.assertAlmostEqual(normal.normalized().x, 1.0, 4)
            # Evaluated mesh lies on the cube face.
            dg = bpy.context.evaluated_depsgraph_get()
            ev = obj.evaluated_get(dg)
            xs = [(ev.matrix_world @ v.co).x for v in ev.data.vertices]
            self.assertGreater(len(xs), 4)
            for x in xs:
                self.assertAlmostEqual(x, 1.0 + bpy.context.scene.cs_sticker_place.offset, 3)
        self.assertEqual(len(bpy.data.collections[utils.STICKER_COLLECTION_NAME].objects), 7)

    def test_spawn_requires_target(self):
        select_sticker("demo_paper_star")
        with self.assertRaises(RuntimeError):
            bpy.ops.cs_sticker.spawn(mode="SURFACE")

    def test_manual_and_constraint(self):
        cube = add_cube()
        bpy.context.scene.cs_sticker_place.attach = "CONSTRAINT"
        select_sticker("demo_foil_shield")
        self.assertEqual(bpy.ops.cs_sticker.spawn(mode="MANUAL"), {"FINISHED"})
        manual = bpy.context.active_object
        self.assertIsNone(manual.parent)
        self.assertEqual(manual.modifiers[P.MOD_SHRINKWRAP].target, cube)

        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube
        bpy.context.scene.cursor.location = (0, 0, 5)
        self.assertEqual(bpy.ops.cs_sticker.spawn(mode="SURFACE"), {"FINISHED"})
        obj = bpy.context.active_object
        self.assertEqual(obj.constraints[0].type, "CHILD_OF")
        self.assertAlmostEqual(obj.matrix_world.translation.z, 1.0, 4)

        # Constraint keeps the sticker on the moving surface.
        cube.location.x += 2
        bpy.context.view_layer.update()
        self.assertAlmostEqual(obj.matrix_world.translation.x, 2.0, 4)

    def test_raycast_skips_stickers(self):
        cube = add_cube()
        hit = P.raycast_surfaces(bpy.context, Vector((0, 0, 10)), Vector((0, 0, -1)), [cube])
        self.assertIsNotNone(hit)
        self.assertAlmostEqual(hit[1].z, 1.0, 4)
        self.assertAlmostEqual(hit[2].z, 1.0, 4)
        select_sticker("demo_paper_star")
        bpy.ops.cs_sticker.spawn(mode="MANUAL")
        self.assertNotIn(bpy.context.active_object, P.surface_candidates(bpy.context))

    def test_rotate_operator(self):
        add_cube()
        select_sticker("demo_paper_star")
        bpy.ops.cs_sticker.spawn(mode="MANUAL")
        obj = bpy.context.active_object
        before = obj.matrix_world.copy()
        bpy.ops.cs_sticker.rotate(angle=math.radians(90))
        x_after = obj.matrix_world.to_3x3() @ Vector((1, 0, 0))
        y_before = before.to_3x3() @ Vector((0, 1, 0))
        self.assertAlmostEqual((x_after - y_before).length, 0, 4)


class TestUserLibrary(unittest.TestCase):
    def test_user_path_and_render(self):
        reset_scene()
        prefs = utils.get_prefs()
        with tempfile.TemporaryDirectory() as root:
            cap = os.path.join(root, "My Capsule")
            os.makedirs(cap)
            # Copy a demo texture under an exported-looking name.
            src = os.path.join(utils.CORE_LIBRARY_DIR, "textures", "demo_paper_star_color.png")
            with open(src, "rb") as a, open(os.path.join(cap, "lucky_star_color_png_0a1b2c3d.png"), "wb") as b:
                b.write(a.read())
            prefs.user_path = root  # triggers refresh
            items = [i for i in bpy.context.window_manager.cs_sticker.items if i.source == "USER"]
            self.assertEqual([(i.name, i.collection) for i in items], [("Lucky Star", "My Capsule")])

            # Filters
            state = bpy.context.window_manager.cs_sticker
            state.filter_collection = "My Capsule"
            self.assertEqual(registry.selected_sticker(bpy.context).name, "Lucky Star")
            state.filter_collection = "ALL"
            state.search = "zzz"
            self.assertEqual(len(state.items), 0)
            state.search = "star"
            self.assertEqual(sorted(i.name for i in state.items), ["Demo Star", "Lucky Star"])
            state.search = ""
            prefs.user_path = ""
        self.assertFalse(any(i.source == "USER" for i in bpy.context.window_manager.cs_sticker.items))

    def test_list_is_capped(self):
        reset_scene()
        prefs = utils.get_prefs()
        src = os.path.join(utils.CORE_LIBRARY_DIR, "textures", "demo_paper_star_color.png")
        with tempfile.TemporaryDirectory() as root:
            n = registry.MAX_LIST_ITEMS + 50
            entries = [{"name": f"Bulk {i:04d}", "collection": "Bulk", "textures": {"base": src}}
                       for i in range(n)]
            with open(os.path.join(root, "catalog.json"), "w") as fh:
                json.dump({"stickers": entries}, fh)
            prefs.user_path = root
            state = bpy.context.window_manager.cs_sticker
            self.assertEqual(len(state.items), registry.MAX_LIST_ITEMS)
            self.assertEqual(registry.match_count(), n + 7)  # + core demo set
            state.search = "bulk 0049"
            self.assertEqual([i.name for i in state.items], ["Bulk 0049"])
            state.search = ""
            prefs.user_path = ""


if __name__ == "__main__":
    unittest.main()
