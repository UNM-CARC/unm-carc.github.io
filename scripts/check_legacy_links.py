#!/usr/bin/env python3
"""Guard the asset localization against regression. Hermetic: no network.

Two checks:

1. No page body may reference a binary asset on carc.unm.edu. Those URLs resolve
   today only because that hostname still points at the old Cascade server; a
   page that reintroduces one is a page whose images break the moment the host
   changes.

2. Every local /assets/... reference must resolve to a file in docs/assets/,
   which catches renames and typos that would otherwise ship as broken images.

Frontmatter `sources[].resource` provenance is exempt from check 1 by design: it
records where a page came from, and a URL that no longer resolves is still a
factually correct citation.

Links to legacy Cascade *pages* are also fine and deliberately unchecked — the
site is published into the same document root, so those files stay put and keep
serving at their original addresses.

Usage: python3 scripts/check_legacy_links.py [docs_dir]
Exit code 1 on failures.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ASSET_EXT = r"(?:png|jpe?g|gif|svg|webp|pdf|xlsx|docx|pptx)"
LEGACY_ASSET_RE = re.compile(
    rf"https?://carc\.unm\.edu/[^\s)\"'>]+\.{ASSET_EXT}\b", re.IGNORECASE)
LOCAL_ASSET_RE = re.compile(r"[(\"']/assets/([^)\"'\s]+)")

# log.md is a historical record; it may legitimately cite old URLs.
EXEMPT_FILES = {"log.md"}


def body_of(text: str) -> str:
    """Everything after the YAML frontmatter block."""
    if not text.startswith("---"):
        return text
    m = re.match(r"^---\s*\n.*?\n---\s*\n?", text, re.DOTALL)
    return text[m.end():] if m else text


def main() -> int:
    docs = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs"
    if not docs.is_dir():
        print(f"error: {docs} is not a directory", file=sys.stderr)
        return 2

    errors: list[str] = []
    checked = refs = 0

    for path in sorted(docs.rglob("*.md")):
        rel = path.relative_to(docs)
        if rel.parts[0] == "assets":
            continue
        checked += 1
        body = body_of(path.read_text(encoding="utf-8"))

        if rel.name not in EXEMPT_FILES:
            for hit in LEGACY_ASSET_RE.findall(body):
                errors.append(
                    f"{rel}: hotlinked legacy asset {hit}\n"
                    f"    -> add it to migration/assets.yml and run "
                    f"scripts/migrate_assets.py")

        for name in LOCAL_ASSET_RE.findall(body):
            refs += 1
            if not (docs / "assets" / name).is_file():
                errors.append(f"{rel}: /assets/{name} does not exist in docs/assets/")

    for e in errors:
        print(f"ERROR {e}")
    print(f"\nChecked {checked} markdown files and {refs} local asset references: "
          f"{len(errors)} error(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
