# cs.sticker

Blender add-on that places CS2 stickers on mesh surfaces with a material
setup per finish: Paper, Glitter, Holo, Foil, Gold, Lenticular, Embroidered.
Target: Blender 5.2, compatible back to 4.5.

**For plugin excluding the sticker assets (CS2 export required) [⬇ Download cs_sticker.zip (latest release)](https://github.com/ed3ntim/cs.sticker/releases/latest/download/cs_sticker.zip)**

**For the version including all sticker assets visit my page [⬇ Download cs_sticker-1.4.0 - all sticker.zip](https://ed3n.gallery/apps/cs-sticker/)**

## Installation

1. Download [`cs_sticker.zip`](https://github.com/ed3ntim/cs.sticker/releases/latest/download/cs_sticker.zip)
   (all versions: [Releases](https://github.com/ed3ntim/cs.sticker/releases)).
2. Blender: *Edit > Preferences > Get Extensions > ⌄ > Install from Disk...*
   and pick the zip (drag & drop onto the Blender window works too).
3. 3D Viewport sidebar (`N`), tab **cs.sticker**.

The add-on ships with one demo sticker per finish. To use the real CS2
stickers, export them from your own game installation (see
[CS2 stickers](#cs2-stickers)).

## Usage

1. **Library**: search by name, collection, finish or tag; filter by
   collection and finish. **Preview** shows the texture and its maps.
2. **Placement** (size, rotation, subdivisions, offset, attach mode).
   Size is relative by default: 6.5 % of the target's longest side, which
   matches CS2 stickers on rifles in any scene scale (meters or Source
   units). Switch to *Absolute* for a fixed width. The offset is a
   percentage of the sticker width. *Reset to Defaults* restores all
   placement settings.
   - **Place Interactively**: the sticker follows the mouse over surfaces as
     a live preview. Wheel = rotate (Shift = fine), Ctrl+Wheel = scale,
     F = toggle upright, LMB = place, Shift+LMB = place and continue,
     RMB/Esc = finish/cancel.
   - **Spawn Sticker**: onto the selected mesh, at the point closest to the
     3D cursor (Shift+right-click on the surface sets the cursor).
   - **Manual (at Cursor)**: plane plus modifier stack at the cursor.
3. **Active Sticker**: rotate, scale, retarget, Shrinkwrap/Subdivision
   values and all material parameters (Wear, Holo Strength, ...).

Each sticker is a plane with **Subdivision (Simple) → Shrinkwrap (Project)
→ Clip**, attached to the surface via Parent or Child Of. Projection works
like a decal: the plane hovers slightly above the surface and is projected
inward, so it lands on the outermost surface (over plates and levers, not
under them). Parts that would hang past the edge of the target are hidden,
as are the steep walls of steps the sticker is pulled over.

## CS2 stickers

Valve's sticker textures are copyrighted game assets and are not part of
this repository or the release. `tools/export_cs2_stickers.py` exports them
from **your own** CS2 installation with
[Source2Viewer](https://github.com/ValveResourceFormat/ValveResourceFormat)
into a library the add-on reads: about 11,000 stickers in 70 collections,
roughly 7 GB.

```
python tools/export_cs2_stickers.py --out D:/cs2_stickers --download-s2v
```

- CS2 is found through Steam; otherwise pass `--cs2 <path>`.
- `--download-s2v` fetches Source2Viewer-CLI; alternatively `--s2v <path>`.
- `--collections cph2024,alyx` exports only certain capsule folders.
- Names, collections and finishes come from `items_game.txt` and the
  localization ("Natus Vincere (Holo)", "Copenhagen 2024").

Then either set *Preferences > Add-ons > cs.sticker > User Sticker Folder*
to the `--out` folder, or bake everything into a personal add-on zip:

```
python tools/build_zip.py --with-stickers D:/cs2_stickers
→ dist/cs_sticker-<version>-full.zip   (for your own use only, do not share)
```

### Own stickers

The user folder also reads your own stickers and raw exports (first folder
level = collection):

```
<user folder>/
  My Capsule/
    crown_foil.vmat + textures       ← Source2Viewer export
    howling_dawn_color.png           ← loose PNGs, grouped by name
    rings_holo_color.png  rings_holo_holomask.png
  Custom/My Sticker/sticker.json     ← explicit metadata
```

Map suffixes: `color/albedo/base/diffuse`, `normal/nrm`, `holomask`,
`holospectrum/spectrum/holowarp/warp`, `glitter`, `roughness`,
`metalness/metal`. The finish comes from the vmat, the name (`_foil`,
`_holo`, `_gold`, `_glitter`, `_lenticular`, `_embroidered`, `_paper`) or
the available maps.

`sticker.json` (one sticker) or `catalog.json` (`{"stickers": [...]}`):

```json
{
  "name": "My Sticker",
  "collection": "Custom",
  "finish": "HOLO",
  "textures": { "base": "art.png", "holomask": "art_mask.png", "holospectrum": "spec.png" },
  "params": { "Holo Strength": 0.8 },
  "tags": ["team", "2024"]
}
```

`params` sets same-named inputs of the finish node group.

## Material setup per finish

Each finish is a reusable node group (`CS2 Sticker <Finish>`) that takes
texture samples as inputs and drives a Principled BSDF. Every group has
the same wear inputs and Alpha Clip.

**Wear** works per sticker, like in CS2: each CS2 sticker has its own wear
mask whose gray value sets the order in which areas scrape off (background
first, logo last), plus its own wear bias and scratch amount from the
material (`g_vWearBiasSticker0`, `g_fWearScratchesSticker0`). Stickers
without a wear mask use seeded noise instead. Every sticker gets its own
Wear Seed derived from its id; you can change it in *Active Sticker*.

| Finish | Maps | Implementation |
|---|---|---|
| Paper | base, (normal, roughness, emission) | matte print, clear coat option, self-illumination mask |
| Glitter | base, glitter mask | Voronoi flakes tilt the normal, metallic in the mask |
| Holo | base, holomask, holospectrum | mask R = strength, G/B = spectrum lookup, shifted by viewing angle |
| Foil | base, normal, (roughness) | metallic, embossed via normal map |
| Gold | base, normal, (roughness) | like Foil, optional gold tint |
| Lenticular | base, holomask, holospectrum | CS2: the mask addresses alternate images in the spectrum, they flip with viewing angle. Own stickers: frame strip in the base texture |
| Embroidered | base, normal | fabric with sheen, thread relief |

The mapping follows the CS2 material `csgo_weapon_sticker.vfx`
(`TextureColorSticker0`, `TextureHoloMaskSticker0`, `g_bHolographicSticker0`,
...). CS2 color maps have no alpha; the shape comes from
`TextureWearMaskSticker0`. Valve does not document the shader, so the node
setups are approximations.

## Development

Tests run headless in Blender:

```
blender -b --factory-startup --python tests/run_tests.py
```

- Demo textures: `python tools/generate_demo_textures.py`
- Release zip: `python tools/build_zip.py`, check with
  `blender --command extension validate dist/cs_sticker-<version>.zip`

## License

[PolyForm Noncommercial 1.0.0](LICENSE.md), Copyright 2026 ed3n.
Free for noncommercial use. Any commercial use (selling the add-on, paid
bundles, paid services) needs a written agreement, see
[COMMERCIAL.md](COMMERCIAL.md). Contact: contact@ed3n.gallery
