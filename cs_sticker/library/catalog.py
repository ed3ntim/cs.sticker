# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Sticker catalog: loading the embedded core set and scanning user folders.

Pure Python (no bpy) so it can be unit tested. Three ways to describe
stickers, all usable in the user folder:

1. ``catalog.json`` - a list of stickers with explicit metadata (the core set
   uses this). Texture paths are relative to the JSON file.
2. ``sticker.json`` - one sticker per folder (same fields as a catalog entry,
   textures relative to the folder). Handy for hand-made drop folders.
3. Raw Source2Viewer exports - ``.vmat`` files and/or loose PNGs. Textures
   are grouped by name, roles and finish are guessed (see vmat.py).

The first sub-folder below the user root is used as collection/capsule name
when no metadata says otherwise, so ``<root>/Copenhagen 2024/...`` shows up
as collection "Copenhagen 2024".
"""

import json
import os
import re
from dataclasses import dataclass, field

from . import finishes as F
from . import vmat as V

CATALOG_FILE = "catalog.json"
STICKER_FILE = "sticker.json"
DEFAULT_COLLECTION = "User"

SOURCE_CORE = "CORE"
SOURCE_BUNDLED = "BUNDLED"  # full sticker set baked into a personal build
SOURCE_USER = "USER"


class _FileIndex:
    """os.path.isfile replacement that lists each directory once.

    A full CS2 export has ~45k texture references; one stat call each takes
    seconds on Windows, a listing per directory (a few hundred) does not.
    Reset on every Catalog.load so the result is never stale for long."""

    def __init__(self):
        self._dirs = {}

    def exists(self, path):
        if not path:
            return False
        folder, name = os.path.split(os.path.normcase(os.path.abspath(path)))
        names = self._dirs.get(folder)
        if names is None:
            try:
                names = {os.path.normcase(n) for n in os.listdir(folder)}
            except OSError:
                names = set()
            self._dirs[folder] = names
        return name in names

    def clear(self):
        self._dirs.clear()


FILES = _FileIndex()


@dataclass
class Sticker:
    id: str
    name: str
    collection: str
    finish: str
    textures: dict = field(default_factory=dict)  # role -> absolute path
    params: dict = field(default_factory=dict)    # finish parameters (e.g. frames)
    source: str = SOURCE_USER
    origin: str = ""                              # file the entry came from
    tags: tuple = ()

    @property
    def base_path(self):
        return self.textures.get(F.ROLE_BASE, "")

    def missing_files(self):
        """Roles whose texture path is set but does not exist on disk."""
        return [r for r, p in self.textures.items() if not FILES.exists(p)]

    def missing_required(self):
        """Required roles of the finish that are absent or missing on disk."""
        present = {r for r, p in self.textures.items() if FILES.exists(p)}
        return F.missing_roles(self.finish, present)

    def search_text(self):
        return " ".join((self.name, self.collection, self.finish, " ".join(self.tags))).lower()


def make_id(*parts):
    """Stable, filesystem-safe id from arbitrary strings."""
    text = "_".join(p for p in parts if p)
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "sticker"


def pretty_name(stem):
    """'howling_dawn_holo' -> 'Howling Dawn Holo'."""
    words = [w for w in re.split(r"[_\-\s]+", stem) if w]
    return " ".join(w[:1].upper() + w[1:] for w in words) or stem


@dataclass
class LoadReport:
    """Collects problems while loading so the UI can show them."""
    warnings: list = field(default_factory=list)

    def warn(self, msg):
        self.warnings.append(msg)


# ---------------------------------------------------------------------------
# JSON metadata
# ---------------------------------------------------------------------------

def sticker_from_entry(entry, base_dir, source, origin, default_collection, report):
    """Build a Sticker from a JSON dict. Returns None for invalid entries."""
    if not isinstance(entry, dict):
        report.warn(f"{origin}: entry is not an object")
        return None
    name = str(entry.get("name") or "").strip()
    textures_in = entry.get("textures") or {}
    if not name or not isinstance(textures_in, dict):
        report.warn(f"{origin}: entry without 'name' or 'textures' skipped")
        return None

    textures = {}
    for role, rel in textures_in.items():
        role = str(role).lower()
        if role not in F.ALL_ROLES:
            report.warn(f"{origin}: '{name}' unknown texture role '{role}'")
            continue
        textures[role] = os.path.normpath(os.path.join(base_dir, str(rel)))

    finish = F.normalize_finish(entry.get("finish")) or F.guess_finish(
        V.tokenize(name), textures.keys())
    collection = str(entry.get("collection") or default_collection)
    sticker = Sticker(
        id=str(entry.get("id") or make_id(source, collection, name, finish)),
        name=name,
        collection=collection,
        finish=finish,
        textures=textures,
        params=dict(entry.get("params") or {}),
        source=source,
        origin=origin,
        tags=tuple(str(t) for t in entry.get("tags") or ()),
    )
    for role in sticker.missing_files():
        report.warn(f"'{name}': missing {role} texture {textures[role]}")
    return sticker


def load_catalog_file(path, source, default_collection, report):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        report.warn(f"{path}: cannot read ({exc})")
        return []
    base_dir = os.path.dirname(path)
    # A sticker.json may hold a single entry; catalog.json holds {"stickers": [...]}.
    entries = data.get("stickers") if isinstance(data, dict) and "stickers" in data else [data]
    if not isinstance(entries, list):
        report.warn(f"{path}: 'stickers' must be a list")
        return []
    default_collection = (data.get("collection") if isinstance(data, dict) else None) \
        or default_collection
    out = []
    for entry in entries:
        s = sticker_from_entry(entry, base_dir, source, path, default_collection, report)
        if s:
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# Raw exports
# ---------------------------------------------------------------------------

def stickers_from_vmats(folder, files, collection, report, source=SOURCE_USER):
    """One sticker per .vmat in a folder. Returns (stickers, used_image_paths)."""
    out, used = [], set()
    for name in sorted(files):
        if not name.lower().endswith(".vmat"):
            continue
        path = os.path.join(folder, name)
        try:
            info = V.parse_vmat(path)
        except OSError as exc:
            report.warn(f"{path}: cannot read ({exc})")
            continue
        textures = {}
        for role, ref in info.textures.items():
            resolved = V.resolve_texture(path, ref)
            if resolved:
                textures[role] = resolved
                used.add(os.path.normcase(resolved))
            else:
                report.warn(f"{name}: {role} texture '{ref}' not found in export")
        stem = os.path.splitext(name)[0]
        if F.ROLE_BASE not in textures:
            # Fallback: loose PNGs with the same stem next to the vmat.
            for img in files:
                img_stem, role = V.split_texture_name(img)
                if img_stem == stem.lower() and img.lower().endswith(V.IMAGE_EXTENSIONS):
                    textures.setdefault(role, os.path.join(folder, img))
                    used.add(os.path.normcase(os.path.join(folder, img)))
        if F.ROLE_BASE not in textures:
            report.warn(f"{name}: no color texture found, skipped")
            continue
        out.append(Sticker(
            id=make_id(source, collection, stem),
            name=pretty_name(stem),
            collection=collection,
            finish=info.finish or F.DEFAULT_FINISH,
            textures=textures,
            params={k: v for k, v in info.params.items() if k.lower() != "shader"},
            source=source,
            origin=path,
        ))
    return out, used


def stickers_from_images(folder, files, collection, used, source=SOURCE_USER):
    """Group loose images without vmat by name stem into stickers."""
    groups = {}
    for name in sorted(files):
        if not name.lower().endswith(V.IMAGE_EXTENSIONS):
            continue
        path = os.path.join(folder, name)
        if os.path.normcase(path) in used:
            continue
        stem, role = V.split_texture_name(name)
        groups.setdefault(stem, {}).setdefault(role, path)
    out = []
    for stem, textures in groups.items():
        if F.ROLE_BASE not in textures:
            continue  # orphan normal/mask maps
        tokens = V.tokenize(stem)
        out.append(Sticker(
            id=make_id(source, collection, stem),
            name=pretty_name(stem),
            collection=collection,
            finish=F.guess_finish(tokens, textures.keys()),
            textures=textures,
            source=source,
            origin=folder,
        ))
    return out


def scan_user_dir(root, report, source=SOURCE_USER):
    """Walk a library folder and collect all stickers found."""
    out = []
    if not root or not os.path.isdir(root):
        return out
    root = os.path.abspath(root)
    for folder, dirs, files in os.walk(root):
        dirs.sort()
        rel = os.path.relpath(folder, root)
        collection = DEFAULT_COLLECTION if rel == "." else rel.split(os.sep)[0]
        lower = {f.lower(): f for f in files}

        # Explicit metadata wins and claims the folder with all sub-folders
        # (the exporter keeps its textures in sub-folders of catalog.json).
        if CATALOG_FILE in lower or STICKER_FILE in lower:
            for key in (CATALOG_FILE, STICKER_FILE):
                if key in lower:
                    out.extend(load_catalog_file(
                        os.path.join(folder, lower[key]), source, collection, report))
            dirs[:] = []
            continue

        vmat_stickers, used = stickers_from_vmats(folder, files, collection, report, source)
        out.extend(vmat_stickers)
        # In a Source2Viewer export the vmats define the stickers; leftover
        # images there are duplicates ("_psd_<hash>.png") or engine maps.
        if not vmat_stickers:
            out.extend(stickers_from_images(folder, files, collection, used, source))
    return out


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

class Catalog:
    """In-memory sticker database with search/filter helpers."""

    def __init__(self):
        self.stickers = []
        self.by_id = {}
        self.report = LoadReport()

    def load(self, core_dir, user_dir="", bundled_dir=""):
        self.report = LoadReport()
        FILES.clear()
        stickers = []
        core_file = os.path.join(core_dir, CATALOG_FILE)
        if os.path.isfile(core_file):
            stickers += load_catalog_file(core_file, SOURCE_CORE, "Core", self.report)
        else:
            self.report.warn(f"core catalog not found: {core_file}")
        stickers += scan_user_dir(bundled_dir, self.report, SOURCE_BUNDLED)
        stickers += scan_user_dir(user_dir, self.report)

        # De-duplicate ids (user entries may collide), keep the first.
        self.stickers, self.by_id = [], {}
        for s in stickers:
            if s.id in self.by_id:
                n = 2
                while f"{s.id}_{n}" in self.by_id:
                    n += 1
                s.id = f"{s.id}_{n}"
            self.by_id[s.id] = s
            self.stickers.append(s)
        order = {SOURCE_CORE: 0, SOURCE_BUNDLED: 1, SOURCE_USER: 2}
        self.stickers.sort(key=lambda s: (order.get(s.source, 3), s.collection.lower(), s.name.lower()))
        return self

    def get(self, sticker_id):
        return self.by_id.get(sticker_id)

    def collections(self):
        return sorted({s.collection for s in self.stickers}, key=str.lower)

    def filter(self, text="", collection="", finish=""):
        """Stickers matching all given criteria (empty means 'any').
        ``text`` is split into words that must all appear."""
        words = text.lower().split()
        out = []
        for s in self.stickers:
            if collection and s.collection != collection:
                continue
            if finish and s.finish != finish:
                continue
            hay = s.search_text()
            if all(w in hay for w in words):
                out.append(s)
        return out
