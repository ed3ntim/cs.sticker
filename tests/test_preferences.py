# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Add-on preferences: uninstall button. The real install/uninstall round
trip needs an isolated user folder (BLENDER_USER_RESOURCES), so here only
the location lookup and the operator are checked."""

import unittest

import bpy

from cs_sticker import preferences as P


class UninstallTest(unittest.TestCase):
    def test_legacy_location(self):
        # The test runner enables the add-on from the repo (legacy module).
        self.assertEqual(P.install_location(bpy.context), ("LEGACY", None, "cs_sticker"))

    def test_operator_available(self):
        self.assertTrue(hasattr(bpy.ops.cs_sticker, "uninstall"))
        self.assertTrue(bpy.ops.cs_sticker.uninstall.poll())

    def test_extension_location(self):
        repos = bpy.context.preferences.extensions.repos
        index = next(i for i, r in enumerate(repos) if r.module == "user_default")
        old = P.ADDON_ID
        try:
            P.ADDON_ID = "bl_ext.user_default.cs_sticker"
            self.assertEqual(P.install_location(bpy.context), ("EXTENSION", index, "cs_sticker"))
            P.ADDON_ID = "bl_ext.no_such_repo.cs_sticker"
            self.assertIsNone(P.install_location(bpy.context))
        finally:
            P.ADDON_ID = old


if __name__ == "__main__":
    unittest.main()
