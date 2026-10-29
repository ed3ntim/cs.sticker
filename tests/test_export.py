# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Tests for tools/export_cs2_stickers.py (everything after the
Source2Viewer step, on a synthetic export)."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import export_cs2_stickers as X  # noqa: E402

ITEMS_GAME = r'''"items_game"
{
	"sticker_kits"
	{
		"0" { "name" "default" "item_name" "#StickerKit_Default" }
		"10"
		{
			"name"		"big_hugs_holo"
			"item_name"		"#StickerKit_big_hugs_holo"
			"sticker_material"		"alyx/big_hugs_holo"
			"item_rarity"		"mythical"
		}
	}
	"other" { "x" "y" }
	"sticker_kits"
	{
		"20"
		{
			"item_name"		"#StickerKit_cph2024_navi_holo"
			"sticker_material"		"cph2024/navi_holo"
			"tournament_event_id"		"22"
		}
		"21" { "item_name" "#StickerKit_navi_graffiti" "sticker_material" "cph2024/navi_graffiti" }
		"22" { "item_name" "#StickerKit_unknown" "sticker_material" "cph2024/not_in_vpk" }
	}
}
'''

LOCALIZATION = '﻿"lang"\n{\n"Language" "English"\n"Tokens"\n{\n' \
    '"StickerKit_big_hugs_holo"\t\t"Big Hugs (Holo)"\n' \
    '"StickerKit_cph2024_navi_holo"\t"Natus Vincere (Holo) | Copenhagen 2024"\n' \
    '"CSGO_Tournament_Event_NameShort_22"\t"PGL Copenhagen 2024"\n' \
    '"Quote"\t"say \\"hi\\""\n}\n}\n'

HOLO_VMAT = '''"Layer0"
{{
	"shader"	"csgo_weapon_sticker.vfx"
	"g_bHolographicSticker0"	"1"
	"TextureColor"	"materials/default/stickers/sticker_default_backing.psd"
	"TextureHoloSpectrumSticker0"	"{spectrum}"
	"TextureHoloMaskSticker0"	"stickers/{folder}/{name}_holomask.png"
	"TextureColorSticker0"	"stickers/{folder}/{name}.png"
}}
'''


def write(path, text, binary=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if binary else "w", **({} if binary else {"encoding": "utf-8"})) as fh:
        fh.write(text)


class TestKeyValues(unittest.TestCase):
    def test_duplicate_blocks_and_kits(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "items_game.txt"), ITEMS_GAME)
            kits = X.load_sticker_kits(os.path.join(d, "items_game.txt"))
        self.assertEqual(sorted(kits), ["10", "20", "21", "22"])  # "0" has no material
        self.assertEqual(kits["20"]["tournament_event_id"], "22")

    def test_localization(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "loc.txt"), LOCALIZATION)
            tokens = X.load_tokens(os.path.join(d, "loc.txt"))
        self.assertEqual(tokens["stickerkit_big_hugs_holo"], "Big Hugs (Holo)")
        self.assertEqual(tokens["quote"], 'say \\"hi\\"')

    def test_describe(self):
        tokens = {"stickerkit_a": "Natus Vincere (Holo) | Copenhagen 2024",
                  "stickerkit_b": "Crown (Champion)",
                  "csgo_tournament_event_nameshort_9": "Katowice 2019"}
        self.assertEqual(X.describe({"item_name": "#StickerKit_a", "sticker_material": "cph2024/navi_holo"}, tokens),
                         ("Natus Vincere (Holo)", "Copenhagen 2024", "HOLO"))
        self.assertEqual(X.describe({"item_name": "#StickerKit_b", "sticker_material": "community01/crown",
                                     "tournament_event_id": "9"}, tokens),
                         ("Crown (Champion)", "Katowice 2019", None))
        self.assertEqual(X.describe({"item_name": "#missing", "sticker_material": "community/auto_racing/burnout"}, {}),
                         ("Burnout", "Community / Auto Racing", None))


class TestBuildLibrary(unittest.TestCase):
    def test_shared_textures_and_skips(self):
        with tempfile.TemporaryDirectory() as out:
            raw = os.path.join(out, X.RAW_DIR)
            write(os.path.join(raw, *X.ITEMS_GAME.split("/")), ITEMS_GAME)
            write(os.path.join(raw, "resource", "csgo_english.txt"), LOCALIZATION)
            default_spec = os.path.join(raw, "materials", "default", "stickers", "default_holospectrum_tga_e12c79bd.png")
            write(default_spec, b"png", binary=True)
            for folder, name, spectrum in (
                    ("alyx", "big_hugs_holo", "materials/default/stickers/default_holospectrum.tga"),
                    ("cph2024", "navi_holo", "stickers/cph2024/spectrum_teams.png")):
                d = os.path.join(raw, "stickers", folder)
                write(os.path.join(d, f"{name}.vmat"),
                      HOLO_VMAT.format(folder=folder, name=name, spectrum=spectrum))
                write(os.path.join(d, f"{name}.png"), b"png", binary=True)
                write(os.path.join(d, f"{name}_holomask.png"), b"png", binary=True)
            write(os.path.join(raw, "stickers", "cph2024", "spectrum_teams.png"), b"png", binary=True)
            # A second sticker sharing the default spectrum (moved only once).
            d = os.path.join(raw, "stickers", "alyx")
            write(os.path.join(d, "twin_holo.vmat"), HOLO_VMAT.format(
                folder="alyx", name="twin_holo", spectrum="materials/default/stickers/default_holospectrum.tga"))
            write(os.path.join(d, "twin_holo.png"), b"png", binary=True)
            write(os.path.join(d, "twin_holo_holomask.png"), b"png", binary=True)

            kits = X.load_sticker_kits(os.path.join(raw, *X.ITEMS_GAME.split("/")))
            kits["30"] = {"item_name": "#x", "sticker_material": "alyx/twin_holo"}
            tokens = X.load_tokens(os.path.join(raw, "resource", "csgo_english.txt"))
            stickers, skipped, missing, graffiti = X.build_library(out, raw, kits, tokens, [], move=True)

            self.assertEqual((skipped, missing, graffiti), (1, 0, 1))  # not_in_vpk, -, navi_graffiti
            by_name = {s["name"]: s for s in stickers}
            self.assertEqual(set(by_name), {"Big Hugs (Holo)", "Natus Vincere (Holo)", "Twin Holo"})
            navi = by_name["Natus Vincere (Holo)"]
            self.assertEqual((navi["collection"], navi["finish"]), ("Copenhagen 2024", "HOLO"))
            self.assertEqual(navi["textures"]["holospectrum"], "textures/stickers/cph2024/spectrum_teams.png")
            spec = "textures/materials/default/stickers/default_holospectrum_tga_e12c79bd.png"
            self.assertEqual(by_name["Big Hugs (Holo)"]["textures"]["holospectrum"], spec)
            self.assertEqual(by_name["Twin Holo"]["textures"]["holospectrum"], spec)
            for s in stickers:
                for rel in s["textures"].values():
                    self.assertTrue(os.path.isfile(os.path.join(out, rel)), rel)

            # The written catalog loads as a cs.sticker library.
            with open(os.path.join(out, "catalog.json"), encoding="utf-8") as fh:
                self.assertEqual(len(json.load(fh)["stickers"]), 3)
            import shutil
            shutil.rmtree(raw)
            cat = X.C.Catalog().load(os.path.join(out, "no_core"), out)
            self.assertEqual(len(cat.stickers), 3)
            self.assertEqual(cat.report.warnings[1:], [])  # only "core catalog not found"

    def test_glitter_flakes(self):
        # Every CS2 sticker references the shared flake normal; only glitter keeps it.
        flakes = '\t"TextureGlitterNormalSticker0"\t"materials/default/stickers/squares_glitter_normal.tga"\n'
        with tempfile.TemporaryDirectory() as out:
            raw = os.path.join(out, X.RAW_DIR)
            write(os.path.join(raw, "materials", "default", "stickers", "squares_glitter_normal_tga_25145674.png"),
                  b"png", binary=True)
            d = os.path.join(raw, "stickers", "antwerp2022")
            for name, flag in (("astr_glitter", "g_bGlitterSticker0"), ("astr_holo", "g_bHolographicSticker0")):
                write(os.path.join(d, f"{name}.vmat"),
                      f'"Layer0"\n{{\n\t"shader"\t"csgo_weapon_sticker.vfx"\n\t"{flag}"\t"1"\n{flakes}'
                      f'\t"TextureHoloMaskSticker0"\t"stickers/antwerp2022/{name}_mask.png"\n'
                      f'\t"TextureColorSticker0"\t"stickers/antwerp2022/astr.png"\n}}\n')
                write(os.path.join(d, f"{name}_mask.png"), b"png", binary=True)
            write(os.path.join(d, "astr.png"), b"png", binary=True)
            kits = {"1": {"item_name": "#a", "sticker_material": "antwerp2022/astr_glitter"},
                    "2": {"item_name": "#b", "sticker_material": "antwerp2022/astr_holo"}}
            stickers, _, missing, _ = X.build_library(out, raw, kits, {}, [], move=True)

            self.assertEqual(missing, 0)
            by_finish = {s["finish"]: s for s in stickers}
            rel = by_finish["GLITTER"]["textures"]["flakes"]
            self.assertEqual(rel, "textures/materials/default/stickers/squares_glitter_normal_tga_25145674.png")
            self.assertTrue(os.path.isfile(os.path.join(out, rel)))
            self.assertNotIn("flakes", by_finish["HOLO"]["textures"])


if __name__ == "__main__":
    unittest.main()
