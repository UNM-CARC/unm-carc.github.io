#!/usr/bin/env python3
"""One-time: tidy the Cascade site tree after the cutover.

Everything the rebuilt site does not own is moved under `archive/` so the
Cascade tree shows the new site's structure and nothing else. Every move is
made WITHOUT unpublish: the files Cascade published years ago stay exactly
where they are in the document root, so no legacy URL changes — the moves
only affect what an editor sees inside Cascade.

What moves:
  - the legacy top-level folders (about-carc, contact-us, education--training,
    images, new-users, news--events, systems, user-support-2)  -> archive/<name>
  - the legacy children of research/ (the new site owns only its index and
    five subfolders there)                                      -> archive/research-legacy/
  - the V2 theme folders assets/css, assets/img, assets/js        -> archive/assets-v2/
  - the four superseded Pages held in _retired/                  -> archive/retired-2026-09/
  - the unpublished donate-to-carc symlink                       -> archive/

What stays: _internal (site machinery), _carc-sync (the sync manifests),
google*.html (Search Console), and everything the build publishes.

Usage: python3 scripts/cascade_archive_legacy.py [--dry-run]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cascade_sync import Cascade, CascadeError, load_key, log  # noqa: E402

LEGACY_ROOT_FOLDERS = ["about-carc", "contact-us", "education--training", "images",
                       "new-users", "news--events", "systems", "user-support-2"]
RESEARCH_OWNED = {"research/index.html", "research/index.md", "research/featured-projects",
                  "research/publications", "research/free-services",
                  "research/grant-resources", "research/premium-services"}
ASSET_THEME_FOLDERS = ["assets/css", "assets/img", "assets/js"]


def folder_id(cx: Cascade, path: str) -> str | None:
    a = cx.read("folder", path)
    return a["folder"]["id"] if a else None


def ensure_folder(cx: Cascade, parent_path: str, name: str, dry: bool) -> str | None:
    path = f"{parent_path}/{name}".strip("/")
    fid = folder_id(cx, path)
    if fid:
        return fid
    log(f"  create folder {path} (unpublishable)")
    if dry:
        return None
    return cx.create("folder", {"name": name, "parentFolderPath": "/" + parent_path.strip("/"),
                                "shouldBePublished": False, "shouldBeIndexed": False})


FAILED: list[str] = []


def conforming(name: str) -> str:
    """Cascade re-validates a name on move against the site's naming rules,
    which legacy assets predate: lowercase, collapse doubled hyphens, drop
    trailing ones."""
    import re
    n = re.sub(r"-{2,}", "-", name.lower()).strip("-")
    return n or name


def move(cx: Cascade, kind: str, src_path: str, dest_id: str | None, dry: bool,
         new_name: str | None = None) -> bool:
    a = cx.read(kind, src_path)
    if not a:
        log(f"  skip   {kind} {src_path}: not found (already moved?)")
        return False
    aid = next(iter(a.values()))["id"]
    log(f"  move   {kind:7} {src_path}" + (f"  -> {new_name}" if new_name else ""))
    if dry:
        return True
    try:
        r = cx.move(kind, aid, dest_folder_id=dest_id, new_name=new_name, unpublish=False)
    except CascadeError as e:
        r = {"success": False, "message": str(e)}
    if not r.get("success") and "naming rules" in str(r.get("message", "")):
        base = src_path.split("/")[-1]
        alt = conforming(new_name or base)
        if alt != (new_name or base):
            log(f"         name refused; retrying as {alt!r}")
            try:
                r = cx.move(kind, aid, dest_folder_id=dest_id, new_name=alt, unpublish=False)
            except CascadeError as e:
                r = {"success": False, "message": str(e)}
    if not r.get("success"):
        log(f"  !! failed: {kind} {src_path}: {r.get('message')}")
        FAILED.append(src_path)
        return False
    return True


def main() -> int:
    dry = "--dry-run" in sys.argv
    cx = Cascade(load_key(None))
    arch = cx.read("folder", "archive")["folder"]
    log(f"archive/: id {arch['id']}, shouldBePublished={arch.get('shouldBePublished')}, "
        f"{len(arch.get('children', []))} children")
    if arch.get("shouldBePublished"):
        log("  !! archive/ is publishable; refusing — make it unpublishable in Cascade first")
        return 1
    arch_id = arch["id"]
    existing = {c["path"]["path"].split("/")[-1] for c in arch.get("children", [])}
    n = 0

    log("legacy top-level folders -> archive/")
    for name in LEGACY_ROOT_FOLDERS:
        if name in existing:
            log(f"  !! archive/{name} already exists; skipping {name}")
            continue
        n += move(cx, "folder", name, arch_id, dry)

    log("research/ legacy children -> archive/research-legacy/")
    dest = ensure_folder(cx, "archive", "research-legacy", dry)
    kids = cx.read("folder", "research")["folder"].get("children", [])
    for k in kids:
        if k["path"]["path"] in RESEARCH_OWNED:
            continue
        n += move(cx, k["type"], k["path"]["path"], dest, dry)

    log("assets/ theme folders -> archive/assets-v2/")
    dest = ensure_folder(cx, "archive", "assets-v2", dry)
    for p in ASSET_THEME_FOLDERS:
        n += move(cx, "folder", p, dest, dry)

    log("_retired/ -> archive/retired-2026-09")
    n += move(cx, "folder", "_retired", arch_id, dry, new_name="retired-2026-09")

    log("donate-to-carc symlink -> archive/")
    n += move(cx, "symlink", "donate-to-carc", arch_id, dry)

    log(f"{'would move' if dry else 'moved'} {n} asset(s)")
    if FAILED:
        log(f"{len(FAILED)} not moved:")
        for f in FAILED:
            log(f"  {f}")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CascadeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(3)
