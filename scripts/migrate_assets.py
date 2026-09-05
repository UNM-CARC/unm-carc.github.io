#!/usr/bin/env python3
"""One-shot: localize legacy carc.unm.edu binaries into docs/assets/.

Reads migration/assets.yml, fetches each legacy file (from a local capture
directory when given, otherwise over HTTP), optimizes images, writes them into
docs/assets/ under their curated names, and rewrites every reference in
docs/**/*.md to the local /assets/<name> form.

This is a migration tool, not a build step. It talks to the network and needs
Pillow, and neither belongs in CI — the one thing guaranteed to break on cutover
day is a build that depends on carc.unm.edu still answering.

Frontmatter `sources[].resource` provenance is deliberately left untouched: it
records where a page came from, and a URL that no longer resolves is still a
factually correct citation.

Usage:
    python3 scripts/migrate_assets.py [--cache DIR] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import urllib.request
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"
LEGACY_HOST = "https://carc.unm.edu"

MAX_WIDTH = 1600
SIZE_BUDGET = 1_048_576  # SITE_INSTRUCTIONS.md documents a ~1 MB convention
JPEG_QUALITY = 82
RASTER = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def fetch(legacy_path: str, cache: Path | None) -> bytes:
    if cache:
        local = cache / legacy_path.lstrip("/")
        if local.is_file():
            return local.read_bytes()
        print(f"WARN  not in cache, fetching over HTTP: {legacy_path}", file=sys.stderr)
    with urllib.request.urlopen(LEGACY_HOST + legacy_path, timeout=60) as r:
        return r.read()


def optimize(raw: bytes, dest: Path, tmp: Path) -> bytes:
    """Resize and re-encode a raster image; pass other formats through."""
    if dest.suffix.lower() not in RASTER:
        return raw
    src = tmp / "in"
    src.write_bytes(raw)
    try:
        im = Image.open(src)
        im.load()
    except Exception as e:  # not a decodable image; ship it as-is
        print(f"WARN  {dest.name}: cannot decode ({e}); copying verbatim", file=sys.stderr)
        return raw

    if im.width > MAX_WIDTH:
        im = im.resize((MAX_WIDTH, round(im.height * MAX_WIDTH / im.width)),
                       Image.LANCZOS)

    out = tmp / ("out" + dest.suffix.lower())
    if dest.suffix.lower() in (".jpg", ".jpeg"):
        im.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY, optimize=True,
                               progressive=True)
    elif dest.suffix.lower() == ".png":
        im.save(out, "PNG", optimize=True)
    else:
        return raw
    return out.read_bytes()


def rewrite_refs(entries: list[dict], dry: bool) -> int:
    """Point every docs/ body reference at the local asset, and fix alt text."""
    changed = 0
    for md in sorted(DOCS.rglob("*.md")):
        if md.parts[1] == "assets":
            continue
        text = original = md.read_text(encoding="utf-8")
        for e in entries:
            url = re.escape(e["from"])
            host = r"https?://carc\.unm\.edu"
            new = f"/assets/{e['to']}"
            if e.get("alt"):
                text = re.sub(rf"!\[[^\]]*\]\({host}{url}\)",
                              lambda _m, a=e["alt"], n=new: f"![{a}]({n})", text)
            else:
                text = re.sub(rf"!\[([^\]]*)\]\({host}{url}\)",
                              lambda m, n=new: f"![{m.group(1)}]({n})", text)
            # plain links (PDFs, spreadsheets) keep their label
            text = re.sub(rf"\[([^\]]*)\]\({host}{url}\)",
                          lambda m, n=new: f"[{m.group(1)}]({n})", text)
        if text != original:
            changed += 1
            if not dry:
                md.write_text(text, encoding="utf-8")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path,
                    help="directory holding a prior capture, laid out by legacy path")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    spec = yaml.safe_load((ROOT / "migration" / "assets.yml").read_text(encoding="utf-8"))
    entries = spec.get("assets") or []
    if not args.dry_run:
        ASSETS.mkdir(parents=True, exist_ok=True)

    tmp = ROOT / ".asset-migration-tmp"
    tmp.mkdir(exist_ok=True)
    written: dict[str, int] = {}
    before = after = 0
    oversize, review = [], []

    try:
        for e in entries:
            dest = ASSETS / e["to"]
            raw = fetch(e["from"], args.cache)
            before += len(raw)

            if e["to"] in written:  # deduped target (byte-identical sources)
                print(f"  dedup  {e['from']} -> {e['to']}")
                continue

            data = optimize(raw, dest, tmp)
            written[e["to"]] = len(data)
            after += len(data)
            if not args.dry_run:
                dest.write_bytes(data)

            pct = f"{100 * len(data) / len(raw):.0f}%"
            print(f"  {len(raw)/1048576:7.2f} MB -> {len(data)/1048576:6.2f} MB "
                  f"({pct:>4})  {e['to']}")
            if len(data) > SIZE_BUDGET:
                oversize.append((e["to"], len(data)))
            if e.get("review"):
                review.append((e["to"], e["review"].strip()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    changed = rewrite_refs(entries, args.dry_run)

    print(f"\n{len(written)} file(s) written to docs/assets/ "
          f"({before/1048576:.1f} MB -> {after/1048576:.1f} MB), "
          f"{changed} markdown file(s) rewritten"
          + ("   [dry run, nothing saved]" if args.dry_run else ""))

    if oversize:
        print(f"\nWARN  still over the {SIZE_BUDGET//1024} KB budget — consider a .jpg "
              f"target in migration/assets.yml:", file=sys.stderr)
        for name, n in sorted(oversize, key=lambda x: -x[1]):
            print(f"        {n/1048576:6.2f} MB  {name}", file=sys.stderr)
    if review:
        print("\nNEEDS HUMAN REVIEW before shipping:", file=sys.stderr)
        for name, why in review:
            print(f"  {name}: {why}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
