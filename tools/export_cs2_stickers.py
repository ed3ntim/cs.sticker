# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Export all CS2 stickers from your own game installation into a
cs.sticker library (catalog.json + textures), using Source2Viewer-CLI.

    python tools/export_cs2_stickers.py --out D:/cs2_stickers
    python tools/export_cs2_stickers.py --out D:/cs2_stickers --collections cph2024,alyx
    python tools/export_cs2_stickers.py --out D:/cs2_stickers --download-s2v

Then either point the add-on's "User Sticker Folder" at --out, or build a
personal add-on zip with everything included:

    python tools/build_zip.py --with-stickers D:/cs2_stickers

Requirements: CS2 installed via Steam, Source2Viewer-CLI
(https://github.com/ValveResourceFormat/ValveResourceFormat/releases,
asset "cli-windows-x64.zip"; --download-s2v fetches it). Python 3.9+, no
other packages. A full export is roughly 8-9 GB and takes about an hour;
after a CS2 update simply run it again (or --collections for new capsules).

The textures are Valve's copyrighted game assets: export them for your own
use only and do not redistribute them.
"""

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import types
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.join(ROOT, "cs_sticker", "library")

S2V_RELEASES = "https://api.github.com/repos/ValveResourceFormat/ValveResourceFormat/releases/latest"
S2V_ASSET = "cli-windows-x64.zip"
S2V_NAMES = ("Source2Viewer-CLI.exe", "Source2Viewer-CLI")

ITEMS_GAME = "scripts/items/items_game.txt"
DEFAULT_TEXTURES = "materials/default/stickers/"
STICKER_ROOT = "stickers/"
RAW_DIR = "_raw"
TEXTURE_DIR = "textures"


# ---------------------------------------------------------------------------
# Library modules (loaded without bpy / the add-on package __init__)
# ---------------------------------------------------------------------------

def _load_library():
    """Import cs_sticker/library/{finishes,vmat,catalog}.py as a stand-alone
    package so the shared parsing code runs outside Blender."""
    pkg = types.ModuleType("cslib")
    pkg.__path__ = [LIB_DIR]
    sys.modules["cslib"] = pkg
    mods = {}
    for name in ("finishes", "vmat", "catalog"):
        spec = importlib.util.spec_from_file_location(f"cslib.{name}", os.path.join(LIB_DIR, f"{name}.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        mods[name] = mod
    return mods["finishes"], mods["vmat"], mods["catalog"]


F, V, C = _load_library()


# ---------------------------------------------------------------------------
# Locating CS2 and Source2Viewer
# ---------------------------------------------------------------------------

def _steam_roots():
    roots = []
    if sys.platform == "win32":
        try:
            import winreg
            for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        for value in ("SteamPath", "InstallPath"):
                            try:
                                roots.append(winreg.QueryValueEx(k, value)[0])
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass
        roots += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    else:
        home = os.path.expanduser("~")
        roots += [os.path.join(home, ".steam", "steam"), os.path.join(home, ".local", "share", "Steam"),
                  os.path.join(home, "Library", "Application Support", "Steam")]
    return [os.path.normpath(r) for r in roots if r and os.path.isdir(r)]


def find_cs2(explicit=""):
    """Path to game/csgo (the folder holding pak01_dir.vpk)."""
    candidates = []
    if explicit:
        candidates += [explicit, os.path.join(explicit, "game", "csgo")]
    for steam in _steam_roots():
        libraries = [steam]
        vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf):
            with open(vdf, encoding="utf-8", errors="replace") as fh:
                libraries += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', fh.read())]
        for lib in libraries:
            candidates.append(os.path.join(lib, "steamapps", "common", "Counter-Strike Global Offensive", "game", "csgo"))
    for c in candidates:
        if os.path.isfile(os.path.join(c, "pak01_dir.vpk")):
            return os.path.normpath(c)
    raise SystemExit("CS2 not found. Pass --cs2 <...>/Counter-Strike Global Offensive")


def download_s2v(dest):
    print("downloading Source2Viewer-CLI (latest release) ...")
    req = urllib.request.Request(S2V_RELEASES, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        release = json.load(resp)
    asset = next((a for a in release.get("assets", []) if a["name"] == S2V_ASSET), None)
    if asset is None:
        raise SystemExit(f"release {release.get('tag_name')} has no {S2V_ASSET}")
    os.makedirs(dest, exist_ok=True)
    zpath = os.path.join(dest, S2V_ASSET)
    urllib.request.urlretrieve(asset["browser_download_url"], zpath)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(dest)
    print(f"Source2Viewer-CLI {release.get('tag_name')} -> {dest}")


def find_s2v(explicit, tools_dir, download):
    candidates = [explicit] if explicit else []
    candidates += [os.path.join(tools_dir, n) for n in S2V_NAMES]
    candidates += [shutil.which(n) or "" for n in S2V_NAMES]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    if download:
        download_s2v(tools_dir)
        return find_s2v("", tools_dir, False)
    raise SystemExit("Source2Viewer-CLI not found. Pass --s2v <path> or use --download-s2v")


def run_s2v(exe, vpk, out, filters, extensions=None, decompile=True, threads=8):
    cmd = [exe, "-i", vpk, "-o", out, "-f", ",".join(filters), "--threads", str(threads)]
    if extensions:
        cmd += ["-e", extensions]
    if decompile:
        cmd.append("-d")
    started, written = time.time(), 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    for line in proc.stdout:
        if "Dump written" in line or "written to" in line:
            written += 1
            if written % 500 == 0:
                print(f"  {written} files ({time.time() - started:.0f}s)", flush=True)
        elif "error" in line.lower() or "exception" in line.lower():
            print("  " + line.rstrip())
    if proc.wait() != 0:
        raise SystemExit(f"Source2Viewer-CLI failed (exit {proc.returncode})")
    print(f"  done: {written} files in {time.time() - started:.0f}s")


# ---------------------------------------------------------------------------
# KeyValues (items_game.txt, localization)
# ---------------------------------------------------------------------------

_KV_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|//[^\n]*|([^\s{}"]+)')


def parse_kv(text):
    """Parse KeyValues1 into nested lists of (key, value) pairs; values are
    strings or lists. Keeps duplicate keys (items_game has many
    "sticker_kits" blocks)."""
    stack = [[]]
    key = None
    for m in _KV_TOKEN.finditer(text):
        quoted, brace, bare = m.groups()
        if brace == "{":
            block = []
            stack[-1].append((key, block))
            stack.append(block)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        elif quoted is not None or bare is not None:
            tok = quoted if quoted is not None else bare
            if key is None:
                key = tok
            else:
                stack[-1].append((key, tok))
                key = None
    return stack[0]


def find_blocks(pairs, name):
    for key, value in pairs:
        if isinstance(value, list):
            if key and key.lower() == name:
                yield value
            else:
                yield from find_blocks(value, name)


def load_tokens(path):
    """Localization tokens, lower-cased keys."""
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        data = parse_kv(fh.read())
    tokens = {}
    for block in find_blocks(data, "tokens"):
        for key, value in block:
            if isinstance(value, str) and key:
                tokens.setdefault(key.lower(), value)
    return tokens


def load_sticker_kits(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        data = parse_kv(fh.read())
    kits = {}
    for block in find_blocks(data, "sticker_kits"):
        for kit_id, fields in block:
            if isinstance(fields, list):
                entry = {k.lower(): v for k, v in fields if isinstance(v, str)}
                if entry.get("sticker_material"):
                    kits[kit_id] = entry
    return kits


# ---------------------------------------------------------------------------
# Building the library
# ---------------------------------------------------------------------------

_PAREN = re.compile(r"\(([^)]*)\)")


def describe(kit, tokens):
    """(display name, collection, finish hint) for a sticker kit."""
    material = kit["sticker_material"].replace("\\", "/")
    raw = tokens.get(kit.get("item_name", "").lstrip("#").lower(), "")
    name, collection = raw, ""
    if " | " in raw:
        name, collection = (p.strip() for p in raw.rsplit(" | ", 1))
    if not collection and kit.get("tournament_event_id"):
        collection = tokens.get(f"csgo_tournament_event_nameshort_{kit['tournament_event_id']}", "")
    if not collection:
        folder = os.path.dirname(material) or "misc"
        collection = " / ".join(C.pretty_name(p) for p in folder.split("/"))
    if not name:
        name = C.pretty_name(os.path.basename(material))
    # "Natus Vincere (Holo)" -> HOLO; "(Champion)" and the like are ignored.
    hint = None
    for inner in _PAREN.findall(raw):
        hint = F.finish_from_tokens(V.tokenize(inner)) or hint
    return name, collection, hint


def build_library(out, raw, kits, tokens, collections, move):
    """Write out/catalog.json and copy the used textures to out/textures."""
    stickers, copied, skipped, missing_tex, graffiti = [], {}, 0, 0, 0
    tex_root = os.path.join(out, TEXTURE_DIR)

    def place(src):
        """Copy/move one texture below out/textures, once."""
        key = os.path.normcase(os.path.abspath(src))
        if key not in copied:
            rel = os.path.relpath(src, raw)
            dst = os.path.join(tex_root, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if move:
                os.replace(src, dst)
            else:
                shutil.copy2(src, dst)
            copied[key] = os.path.relpath(dst, out).replace(os.sep, "/")
        return copied[key]

    default_dir = os.path.join(raw, *DEFAULT_TEXTURES.strip("/").split("/"))
    for kit_id, kit in sorted(kits.items(), key=lambda kv: kv[1]["sticker_material"]):
        material = kit["sticker_material"].replace("\\", "/")
        if collections and material.split("/")[0] not in collections:
            continue
        if "graffiti" in material.lower():
            graffiti += 1  # sprays share sticker_kits but are not stickers
            continue
        vmat_path = os.path.join(raw, "stickers", *material.split("/")) + ".vmat"
        if not os.path.isfile(vmat_path):
            skipped += 1
            continue
        info = V.parse_vmat(vmat_path)
        name, collection, hint = describe(kit, tokens)
        finish = hint or info.finish or F.DEFAULT_FINISH
        textures = {}
        for role, ref in info.textures.items():
            src = V.resolve_texture(vmat_path, ref, search_dirs=(default_dir,))
            if src:
                textures[role] = src
            else:
                missing_tex += 1
        if F.ROLE_BASE not in textures:
            skipped += 1
            continue
        # Glitter stickers: the "holo" mask slot is their glitter mask.
        if finish == "GLITTER" and F.ROLE_GLITTER not in textures and F.ROLE_HOLOMASK in textures:
            textures[F.ROLE_GLITTER] = textures[F.ROLE_HOLOMASK]
        params = V.group_params(info)
        if finish == "GOLD" and "Tint Amount" not in params:
            params["Tint Amount"] = 0.0  # gold albedo texture, no shader tint
        stickers.append({
            "id": f"cs2_{kit_id}_{C.make_id(material)}",
            "name": name,
            "collection": collection,
            "finish": finish,
            "textures": textures,
            "params": params,
            "tags": [material, kit.get("item_rarity", "")],
        })

    # Second pass: textures are shared between stickers (one spectrum for a
    # whole capsule), so all of them are resolved before any file is moved.
    for sticker in stickers:
        sticker["textures"] = {role: place(src) for role, src in sticker["textures"].items()}

    catalog = {
        "version": 1,
        "generator": "cs.sticker tools/export_cs2_stickers.py",
        "note": "Valve game assets exported from a local CS2 install. Personal use only.",
        "stickers": stickers,
    }
    with open(os.path.join(out, C.CATALOG_FILE), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(catalog, fh, indent=1, ensure_ascii=False)
    return stickers, skipped, missing_tex, graffiti


def main():
    ap = argparse.ArgumentParser(description="Export CS2 stickers into a cs.sticker library.")
    ap.add_argument("--out", required=True, help="library folder to create/update")
    ap.add_argument("--cs2", default="", help="CS2 install folder (auto-detected via Steam)")
    ap.add_argument("--s2v", default="", help="path to Source2Viewer-CLI(.exe)")
    ap.add_argument("--download-s2v", action="store_true", help="download Source2Viewer-CLI if not found")
    ap.add_argument("--collections", default="", help="comma-separated sticker folders, e.g. cph2024,alyx")
    ap.add_argument("--language", default="english", help="localization for names (default english)")
    ap.add_argument("--threads", type=int, default=max(2, (os.cpu_count() or 4) - 1))
    ap.add_argument("--keep-raw", action="store_true", help="keep the raw Source2Viewer export in <out>/_raw")
    ap.add_argument("--skip-export", action="store_true", help="reuse an existing <out>/_raw export")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    raw = os.path.join(out, RAW_DIR)
    os.makedirs(raw, exist_ok=True)
    collections = [c.strip().strip("/") for c in args.collections.split(",") if c.strip()]
    loc_file = f"resource/csgo_{args.language}.txt"

    if not args.skip_export:
        game = find_cs2(args.cs2)
        vpk = os.path.join(game, "pak01_dir.vpk")
        exe = find_s2v(args.s2v, os.path.join(out, "_tools"), args.download_s2v)
        print(f"CS2: {game}\nSource2Viewer: {exe}")
        print("1/3 metadata")
        run_s2v(exe, vpk, raw, [ITEMS_GAME, loc_file], decompile=False, threads=1)
        print("2/3 default sticker textures")
        run_s2v(exe, vpk, raw, [DEFAULT_TEXTURES], extensions="vtex_c", threads=args.threads)
        print("3/3 sticker materials + textures (this is the long part)")
        filters = [f"{STICKER_ROOT}{c}/" for c in collections] or [STICKER_ROOT]
        run_s2v(exe, vpk, raw, filters, extensions="vmat_c", threads=args.threads)

    items_game = os.path.join(raw, *ITEMS_GAME.split("/"))
    loc_path = os.path.join(raw, *loc_file.split("/"))
    if not os.path.isfile(items_game):
        raise SystemExit(f"missing {items_game}: run without --skip-export")
    kits = load_sticker_kits(items_game)
    tokens = load_tokens(loc_path) if os.path.isfile(loc_path) else {}
    print(f"{len(kits)} sticker kits, {len(tokens)} localization tokens")

    tex_root = os.path.join(out, TEXTURE_DIR)
    if os.path.isdir(tex_root):
        shutil.rmtree(tex_root)  # rebuilt from raw, keeps the library in sync
    stickers, skipped, missing_tex, graffiti = build_library(out, raw, kits, tokens, collections,
                                                             move=not args.keep_raw)
    if not args.keep_raw:
        shutil.rmtree(raw, ignore_errors=True)

    by_finish = {}
    for s in stickers:
        by_finish[s["finish"]] = by_finish.get(s["finish"], 0) + 1
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(tex_root) for f in fs)
    print(f"\n{len(stickers)} stickers -> {os.path.join(out, C.CATALOG_FILE)} ({size / 2**30:.2f} GiB textures)")
    print("  " + ", ".join(f"{k.title()}: {v}" for k, v in sorted(by_finish.items())))
    print(f"  graffiti kits ignored: {graffiti}")
    if skipped or missing_tex:
        print(f"  skipped kits without material/color map: {skipped}, unresolved maps: {missing_tex}")
    print("Reminder: these are Valve's assets. Personal use only, do not redistribute.")


if __name__ == "__main__":
    main()
