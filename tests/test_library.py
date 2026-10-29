# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Unit tests for the pure-Python sticker library (vmat parsing, catalog)."""

import json
import os
import tempfile
import unittest

from cs_sticker.library import catalog as C
from cs_sticker.library import finishes as F
from cs_sticker.library import vmat as V

LEGACY_VMAT = """// THIS FILE IS AUTO-GENERATED
Layer0
{
    shader "csgo_sticker.vfx"
    //---- Holo ----
    F_HOLO 1
    g_flHoloStrength "0.800"
    TextureColor "materials/models/weapons/customization/stickers/test/rings_color.png"
    TextureHoloMask "materials/models/weapons/customization/stickers/test/rings_holomask.png"
    TextureHoloSpectrum "materials/default/holo_spectrum.png"
}
"""

KV3_VMAT = """<!-- kv3 encoding:text:version{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d} -->
{
    shader = "csgo_sticker.vfx"
    g_tColor = "materials/stickers/x/crown_foil_color.vtex"
    g_tNormal = "materials/stickers/x/crown_foil_normal.vtex"
}
"""


# Trimmed copy of a real CS2 export (stickers/alyx/big_hugs_holo.vmat).
CS2_HOLO_VMAT = """"Layer0"
{
	"shader"	"csgo_weapon_sticker.vfx"
	"g_bGlitterSticker0"	"0"
	"g_bHolographicSticker0"	"1"
	"g_bMetallicSticker0"	"0"
	"g_vColorTint"	"[1.000000 1.000000 1.000000 0.000000]"
	"TextureColor"	"materials/default/stickers/sticker_default_backing.psd"
	"TextureGlitterNormalSticker0"	"materials/default/stickers/squares_glitter_normal.tga"
	"TextureHoloSpectrumSticker0"	"stickers/krakow2017/spectrum.png"
	"TextureNormal"	"materials/default/default_normal.tga"
	"TextureNormalSticker0"	"materials/default/default_normal.tga"
	"TextureRoughnessSticker0"	"[0.454902 0.454902 0.454902 1.000000]"
	"TextureHoloMaskSticker0"	"stickers/alyx/big_hugs_holomask.png"
	"TextureGlitterMaskSticker0"	"stickers/alyx/big_hugs_holomask_4b0b7b4e_glittermask.png"
	"TextureColorSticker0"	"stickers/alyx/big_hugs_holoback.png"
	"TextureWearMaskSticker0"	"stickers/alyx/big_hugs_holoback_d0af2572-A.png"
	"Compiled Textures"
	{
		"g_tColor"	"materials/default/stickers/sticker_default_backing_psd_a83fef52.vtex"
		"g_tSticker0"	"stickers/alyx/big_hugs_holoback_psd_d0af2572.vtex"
	}
}
"""


def cs2_vmat(flags="", textures=""):
    """Minimal CS2 sticker vmat with the given extra lines."""
    return ('"Layer0"\n{\n\t"shader"\t"csgo_weapon_sticker.vfx"\n'
            '\t"TextureColor"\t"materials/default/stickers/sticker_default_backing.psd"\n'
            + flags + textures + "}\n")


def touch(path, data=b"\x89PNG"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


class TestRoleDetection(unittest.TestCase):
    def test_role_from_key(self):
        self.assertEqual(V.role_from_key("TextureColor"), F.ROLE_BASE)
        self.assertEqual(V.role_from_key("g_tColor"), F.ROLE_BASE)
        self.assertEqual(V.role_from_key("TextureNormal"), F.ROLE_NORMAL)
        self.assertEqual(V.role_from_key("TextureHoloMask"), F.ROLE_HOLOMASK)
        self.assertEqual(V.role_from_key("TextureHoloSpectrum"), F.ROLE_HOLOSPECTRUM)
        self.assertEqual(V.role_from_key("g_tHoloWarp"), F.ROLE_HOLOSPECTRUM)
        self.assertEqual(V.role_from_key("TextureGlitterMask"), F.ROLE_GLITTER)
        self.assertEqual(V.role_from_key("TextureGlitterNormal"), F.ROLE_FLAKES)
        self.assertIsNone(V.role_from_key("g_flSomething"))

    def test_split_texture_name(self):
        self.assertEqual(V.split_texture_name("crown_foil_normal_png_4f2a9c1b.png"), ("crown_foil", "normal"))
        self.assertEqual(V.split_texture_name("crown_foil_color.png"), ("crown_foil", "base"))
        self.assertEqual(V.split_texture_name("howling_dawn.png"), ("howling_dawn", "base"))
        self.assertEqual(V.split_texture_name("howling_dawn_png_9a8b7c6d.png"), ("howling_dawn", "base"))
        self.assertEqual(V.split_texture_name("rings_holomask.tga"), ("rings", "holomask"))
        # A role word inside the name is not a role suffix.
        self.assertEqual(V.split_texture_name("normal_guy_sticker.png"), ("normal_guy_sticker", "base"))


class TestFinishes(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(F.normalize_finish("holo"), "HOLO")
        self.assertEqual(F.normalize_finish("Gold"), "GOLD")
        self.assertEqual(F.normalize_finish("Embroidery"), "EMBROIDERED")
        self.assertIsNone(F.normalize_finish("plastic"))
        self.assertIsNone(F.normalize_finish(""))

    def test_guess(self):
        self.assertEqual(F.guess_finish(["crown", "foil"], {"base"}), "FOIL")
        self.assertEqual(F.guess_finish(["rings"], {"base", "holomask"}), "HOLO")
        self.assertEqual(F.guess_finish(["thing"], {"base", "normal"}), "FOIL")
        self.assertEqual(F.guess_finish(["thing"], {"base"}), "PAPER")

    def test_missing_roles(self):
        self.assertEqual(F.missing_roles("HOLO", {"base"}), ["holomask"])
        self.assertEqual(F.missing_roles("PAPER", {"base"}), [])


class TestVmat(unittest.TestCase):
    def test_legacy(self):
        info = V.parse_vmat_text(LEGACY_VMAT, "rings.vmat")
        self.assertEqual(info.shader, "csgo_sticker.vfx")
        self.assertEqual(info.finish, "HOLO")
        self.assertEqual(set(info.textures), {"base", "holomask", "holospectrum"})
        self.assertEqual(info.params["g_flHoloStrength"], "0.800")

    def test_kv3(self):
        info = V.parse_vmat_text(KV3_VMAT, "crown_foil.vmat")
        self.assertEqual(set(info.textures), {"base", "normal"})
        self.assertEqual(info.finish, "FOIL")

    def test_cs2_layered(self):
        info = V.parse_vmat_text(CS2_HOLO_VMAT, "stickers/alyx/big_hugs_holo.vmat")
        self.assertEqual(info.finish, "HOLO")
        # Backing (TextureColor) and engine defaults are ignored.
        self.assertEqual(info.textures, {
            "base": "stickers/alyx/big_hugs_holoback.png",
            "holomask": "stickers/alyx/big_hugs_holomask.png",
            "glitter": "stickers/alyx/big_hugs_holomask_4b0b7b4e_glittermask.png",
            "holospectrum": "stickers/krakow2017/spectrum.png",
            "wearmask": "stickers/alyx/big_hugs_holoback_d0af2572-A.png",
        })

    def test_cs2_default_spectrum_kept(self):
        text = cs2_vmat('\t"g_bHolographicSticker0"\t"1"\n',
                        '\t"TextureHoloSpectrumSticker0"\t"materials/default/stickers/default_holospectrum.tga"\n'
                        '\t"TextureColorSticker0"\t"stickers/x/a.png"\n')
        info = V.parse_vmat_text(text, "a_holo.vmat")
        self.assertEqual(info.textures["holospectrum"], "materials/default/stickers/default_holospectrum.tga")

    def test_cs2_glitter_flakes_kept(self):
        # The shared flake normal is an engine default, but glitter uses it.
        flakes = '\t"TextureGlitterNormalSticker0"\t"materials/default/stickers/squares_glitter_normal.tga"\n'
        color = '\t"TextureColorSticker0"\t"stickers/x/a.png"\n'
        info = V.parse_vmat_text(cs2_vmat('\t"g_bGlitterSticker0"\t"1"\n', flakes + color), "a_glitter.vmat")
        self.assertEqual(info.finish, "GLITTER")
        self.assertEqual(info.textures["flakes"], "materials/default/stickers/squares_glitter_normal.tga")
        # Other finishes reference it too but do not use it.
        info = V.parse_vmat_text(cs2_vmat('\t"g_bHolographicSticker0"\t"1"\n', flakes + color), "a_holo.vmat")
        self.assertNotIn("flakes", info.textures)

    def test_cs2_finishes(self):
        metal = '\t"g_bMetallicSticker0"\t"1"\n'
        holo = '\t"g_bHolographicSticker0"\t"1"\n'
        color = '\t"TextureColorSticker0"\t"stickers/x/a.png"\n'
        cases = [
            ("health_foil.vmat", metal, "FOIL"),
            ("last_vance_gold.vmat", metal, "GOLD"),             # name beats g_bMetallic
            ("lenticular_burnout.vmat", holo, "LENTICULAR"),     # name beats g_bHolographic
            ("3dm_embroidered.vmat", "", "EMBROIDERED"),
            ("astr_glitter.vmat", '\t"g_bGlitterSticker0"\t"1"\n', "GLITTER"),
            ("golden_eagle.vmat", "", "PAPER"),                  # exact tokens only
        ]
        for name, flags, finish in cases:
            self.assertEqual(V.parse_vmat_text(cs2_vmat(flags, color), name).finish, finish, name)

    def test_cs2_self_illum(self):
        text = cs2_vmat('\t"g_bSelfIllumSticker0"\t"1"\n',
                        '\t"TextureNormalSticker0"\t"stickers/aus2025/3dm_selfillum_mask.png"\n'
                        '\t"TextureColorSticker0"\t"stickers/aus2025/3dm_paper_color.png"\n')
        info = V.parse_vmat_text(text, "3dm.vmat")
        self.assertEqual(info.textures["emission"], "stickers/aus2025/3dm_selfillum_mask.png")
        self.assertNotIn("normal", info.textures)
        self.assertEqual(info.finish, "PAPER")

    def test_cs2_wear(self):
        # Per-sticker wear: own mask, bias and scratch amount, shared
        # default scratch texture (no Sticker0 suffix, engine default kept).
        text = cs2_vmat('\t"g_vWearBiasSticker0"\t"[2.040000 -1.805000 0.000000 0.000000]"\n'
                        '\t"g_fWearScratchesSticker0"\t"0.858"\n',
                        '\t"TextureColorSticker0"\t"stickers/x/a.png"\n'
                        '\t"TextureWearMaskSticker0"\t"stickers/x/a_1234abcd-A.png"\n'
                        '\t"TextureStickerScratches"\t"materials/default/stickers/sticker_default_scratches.psd"\n')
        info = V.parse_vmat_text(text, "a.vmat")
        self.assertEqual(info.textures["wearmask"], "stickers/x/a_1234abcd-A.png")
        self.assertEqual(info.textures["scratches"], "materials/default/stickers/sticker_default_scratches.psd")
        self.assertEqual(V.group_params(info), {"Wear Bias": 2.04, "Wear Scratches": 0.858})

    def test_wear_params_clamped_and_optional(self):
        text = cs2_vmat('\t"g_vWearBiasSticker0"\t"[0.000000 1.000000 0.000000 0.000000]"\n'
                        '\t"g_fWearScratchesSticker0"\t"garbage"\n')
        self.assertEqual(V.group_params(V.parse_vmat_text(text, "a.vmat")), {"Wear Bias": 0.001})
        self.assertEqual(V.group_params(V.parse_vmat_text(LEGACY_VMAT, "a.vmat")), {})

    def test_legacy_gold_tint(self):
        # Gold signatures: plain texture + desaturate + boosted tint multiply.
        text = cs2_vmat('\t"g_bLegacyTintMultiplySticker0"\t"1"\n'
                        '\t"g_vColorTintSticker0"\t"[0.266667 0.180392 0.000000 0.000000]"\n'
                        '\t"g_flTintSaturateSticker0"\t"0.1"\n'
                        '\t"g_flColorBoostSticker0"\t"32"\n')
        params = V.group_params(V.parse_vmat_text(text, "sig_x_gold.vmat"))
        self.assertEqual(params["Gold Tint"], [1.0, 0.6765, 0.0, 1.0])
        self.assertEqual(params["Foil Tint"], params["Gold Tint"])
        self.assertEqual(params["Tint Amount"], 1.0)
        self.assertAlmostEqual(params["Tint Saturation"], 0.1)
        # Flag off or white tint: nothing to tint.
        off = text.replace('"g_bLegacyTintMultiplySticker0"\t"1"', '"g_bLegacyTintMultiplySticker0"\t"0"')
        self.assertNotIn("Gold Tint", V.group_params(V.parse_vmat_text(off, "a.vmat")))
        white = text.replace("[0.266667 0.180392 0.000000", "[1.000000 1.000000 1.000000")
        self.assertNotIn("Gold Tint", V.group_params(V.parse_vmat_text(white, "a.vmat")))

    def test_resolve_cs2_layout(self):
        with tempfile.TemporaryDirectory() as root:
            alyx = os.path.join(root, "stickers", "alyx")
            touch(os.path.join(alyx, "health.png"))
            touch(os.path.join(alyx, "health_normal.png"))
            touch(os.path.join(root, "stickers", "krakow2017", "spectrum.png"))
            touch(os.path.join(root, "materials", "default", "stickers", "default_holospectrum_tga_e12c79bd.png"))
            vm = os.path.join(alyx, "health_foil.vmat")
            touch(vm, b"")

            def rel(ref):
                return os.path.relpath(V.resolve_texture(vm, ref), root).replace(os.sep, "/")
            self.assertEqual(rel("stickers/alyx/health.png"), "stickers/alyx/health.png")
            self.assertEqual(rel("items/assets/stickers/alyx/health_normal.png"), "stickers/alyx/health_normal.png")
            self.assertEqual(rel("stickers/krakow2017/spectrum.png"), "stickers/krakow2017/spectrum.png")
            self.assertEqual(rel("materials/default/stickers/default_holospectrum.tga"),
                             "materials/default/stickers/default_holospectrum_tga_e12c79bd.png")

    def test_garbage_does_not_raise(self):
        info = V.parse_vmat_text("{{{ \x00 nonsense = = \n }", "x.vmat")
        self.assertEqual(info.textures, {})

    def test_resolve_tree_and_flat(self):
        with tempfile.TemporaryDirectory() as root:
            # Tree layout: materials/... below the export root.
            tree_tex = os.path.join(root, "materials", "s", "a_color.png")
            touch(tree_tex)
            vmat_path = os.path.join(root, "materials", "s", "a.vmat")
            touch(vmat_path, b"")
            self.assertEqual(os.path.normcase(V.resolve_texture(vmat_path, "materials/s/a_color.png")),
                             os.path.normcase(tree_tex))
            # Flat layout with hash suffix and .vtex reference.
            flat = os.path.join(root, "flat")
            touch(os.path.join(flat, "b_normal_png_1234abcd.png"))
            touch(os.path.join(flat, "b.vmat"), b"")
            got = V.resolve_texture(os.path.join(flat, "b.vmat"), "materials/x/b_normal.vtex")
            self.assertTrue(got.endswith("b_normal_png_1234abcd.png"))
            self.assertEqual(V.resolve_texture(os.path.join(flat, "b.vmat"), "nope.png"), "")


class TestCatalog(unittest.TestCase):
    def test_core_catalog_complete(self):
        core = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "cs_sticker", "stickers", "core")
        cat = C.Catalog().load(core)
        self.assertEqual(cat.report.warnings, [])
        self.assertEqual({s.finish for s in cat.stickers}, set(F.FINISHES))
        for s in cat.stickers:
            self.assertEqual(s.missing_required(), [], s.name)
            self.assertEqual(s.source, C.SOURCE_CORE)

    def test_user_scan(self):
        with tempfile.TemporaryDirectory() as root:
            cap = os.path.join(root, "Copenhagen 2024")
            # vmat + textures
            os.makedirs(cap)
            with open(os.path.join(cap, "rings.vmat"), "w") as fh:
                fh.write(LEGACY_VMAT)
            touch(os.path.join(cap, "rings_color_png_aa11bb22.png"))
            touch(os.path.join(cap, "rings_holomask_png_cc33dd44.png"))
            # Source2Viewer duplicate next to the vmat is not a second sticker
            touch(os.path.join(cap, "rings_psd_1a2b3c4d.png"))
            # loose PNG group without vmat (own folder of the same collection)
            loose = os.path.join(cap, "loose")
            touch(os.path.join(loose, "crown_foil_color.png"))
            touch(os.path.join(loose, "crown_foil_normal.png"))
            # orphan map is ignored
            touch(os.path.join(loose, "orphan_normal.png"))
            # drop folder with sticker.json in another collection
            drop = os.path.join(root, "Custom", "My Sticker")
            touch(os.path.join(drop, "art.png"))
            with open(os.path.join(drop, "sticker.json"), "w") as fh:
                json.dump({"name": "My Sticker", "finish": "gold",
                           "textures": {"base": "art.png", "normal": "missing.png"}}, fh)

            cat = C.Catalog().load(os.path.join(root, "no_core"), root)
            by_name = {s.name: s for s in cat.stickers}
            self.assertIn("Rings", by_name)
            self.assertEqual(by_name["Rings"].finish, "HOLO")
            self.assertEqual(by_name["Rings"].collection, "Copenhagen 2024")
            self.assertIn("holomask", by_name["Rings"].textures)
            self.assertNotIn("holospectrum", by_name["Rings"].textures)  # not exported

            self.assertEqual(by_name["Crown Foil"].finish, "FOIL")
            self.assertEqual(set(by_name["Crown Foil"].textures), {"base", "normal"})
            self.assertNotIn("Orphan", by_name)
            self.assertEqual(len([s for s in cat.stickers if s.name.startswith("Rings")]), 1)

            mine = by_name["My Sticker"]
            self.assertEqual((mine.finish, mine.collection), ("GOLD", "Custom"))
            self.assertEqual(mine.missing_files(), ["normal"])
            self.assertEqual(mine.missing_required(), ["normal"])

            warnings = " ".join(cat.report.warnings)
            self.assertIn("core catalog not found", warnings)
            self.assertIn("missing normal texture", warnings)

            # search / filter
            self.assertEqual([s.name for s in cat.filter("ring")], ["Rings"])
            self.assertEqual([s.name for s in cat.filter(finish="GOLD")], ["My Sticker"])
            self.assertEqual(len(cat.filter(collection="Copenhagen 2024")), 2)
            self.assertEqual(cat.filter("crown holo"), [])
            self.assertEqual(cat.collections(), ["Copenhagen 2024", "Custom"])

    def test_duplicate_ids_are_renamed(self):
        with tempfile.TemporaryDirectory() as root:
            entry = {"id": "same", "name": "A", "textures": {"base": "a.png"}}
            with open(os.path.join(root, "catalog.json"), "w") as fh:
                json.dump({"stickers": [entry, dict(entry, name="B")]}, fh)
            cat = C.Catalog().load(root)
            self.assertEqual(sorted(s.id for s in cat.stickers), ["same", "same_2"])

    def test_catalog_claims_subtree(self):
        with tempfile.TemporaryDirectory() as root:
            # Exporter layout: catalog.json + textures/ with more images.
            touch(os.path.join(root, "textures", "stickers", "x", "a.png"))
            touch(os.path.join(root, "textures", "stickers", "x", "b.png"))
            with open(os.path.join(root, "catalog.json"), "w") as fh:
                json.dump({"stickers": [{"name": "A", "collection": "X", "finish": "PAPER",
                                         "textures": {"base": "textures/stickers/x/a.png"}}]}, fh)
            cat = C.Catalog().load(os.path.join(root, "no_core"), root)
            self.assertEqual([s.name for s in cat.stickers], ["A"])

    def test_bundled_source(self):
        with tempfile.TemporaryDirectory() as root:
            bundled, user = os.path.join(root, "bundled"), os.path.join(root, "user")
            touch(os.path.join(bundled, "Cap", "z_sticker.png"))
            touch(os.path.join(user, "Cap", "a_sticker.png"))
            cat = C.Catalog().load(os.path.join(root, "no_core"), user, bundled)
            self.assertEqual([(s.name, s.source) for s in cat.stickers],
                             [("Z Sticker", C.SOURCE_BUNDLED), ("A Sticker", C.SOURCE_USER)])

    def test_bad_json(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "catalog.json"), "w") as fh:
                fh.write("{ not json")
            cat = C.Catalog().load(root)
            self.assertEqual(cat.stickers, [])
            self.assertTrue(any("cannot read" in w for w in cat.report.warnings))


if __name__ == "__main__":
    unittest.main()
