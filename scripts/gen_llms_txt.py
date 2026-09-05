#!/usr/bin/env python3
"""Generate llms.txt and llms-full.txt from the docs/ OKF bundle.

llms.txt      — linked outline of the site (llmstxt.org convention): every
                concept page with its frontmatter description, grouped by
                section, with absolute URLs derived from site_url.
llms-full.txt — the entire corpus concatenated as Markdown, frontmatter
                included, so an agent can ingest the whole bundle in one file.

Both are written into docs/ so the static build ships them at the site root.

Usage: python3 scripts/gen_llms_txt.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

SECTION_ORDER = [
    "about", "research", "education", "education/cse", "news", "contact",
]


def site_url() -> str:
    """Canonical site origin. CARC_SITE_URL overrides zensical.toml so a build can
    be pointed at a different host (a test push, CI) without a commit."""
    override = os.environ.get("CARC_SITE_URL")
    if override:
        return override.rstrip("/") + "/"
    text = (ROOT / "zensical.toml").read_text(encoding="utf-8")
    m = re.search(r'^site_url\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return (m.group(1) if m else "/").rstrip("/") + "/"


def frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not m:
        return {}, text
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        data = {}
    return (data if isinstance(data, dict) else {}), text[m.end():]


def page_url(base: str, rel: Path) -> str:
    # use_directory_urls-style pretty URLs
    if rel.name == "index.md":
        tail = str(rel.parent) + "/" if str(rel.parent) != "." else ""
    else:
        tail = str(rel.with_suffix("")) + "/"
    return base + tail.replace("\\", "/")


def section_heading(section_dir: Path) -> str:
    idx = section_dir / "index.md"
    if idx.exists():
        for line in idx.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return section_dir.name.replace("-", " ").title()


def main():
    base = site_url()
    lines = [
        "# UNM Center for Advanced Research Computing",
        "",
        "> The UNM Center for Advanced Research Computing (CARC): mission, "
        "research, the CSE certificate program, news, and contact information. "
        "User documentation for CARC systems lives at "
        "https://unm-carc.github.io/docs/ (with its own llms.txt). The source "
        "repository is an Open Knowledge Format (OKF v0.2) bundle: every page "
        "carries YAML frontmatter with type, provenance, and lifecycle fields.",
        "",
        f"Full corpus for ingestion: {base}llms-full.txt",
        "",
        "Every page's Markdown source (OKF frontmatter included) is served at "
        "its URL plus `index.md` — for example "
        f"{base}about/mission/index.md. Agent guide: "
        f"{base}docs/about/ai-agents/",
        "",
    ]
    full = [
        "# UNM CARC website — full corpus",
        "",
        "Each page below begins with its canonical URL followed by its "
        "original Markdown, OKF frontmatter included.",
        "",
    ]

    n = 0
    for section in SECTION_ORDER:
        sdir = DOCS / section
        if not sdir.is_dir():
            continue
        lines += [f"## {section_heading(sdir)}", ""]
        for path in sorted(sdir.glob("*.md")):
            if path.name == "index.md":
                continue
            fm, _ = frontmatter(path)
            rel = path.relative_to(DOCS)
            url = page_url(base, rel)
            title = fm.get("title") or path.stem.replace("-", " ").title()
            desc = fm.get("description", "").strip()
            suffix = ""
            if fm.get("status") == "deprecated":
                suffix = " (deprecated; kept for history)"
            elif fm.get("status") == "draft":
                suffix = " (draft)"
            lines.append(f"- [{title}]({url}): {desc}{suffix}")
            full += [f"---8<--- {url}", "", path.read_text(encoding="utf-8").rstrip(), ""]
            n += 1
        lines.append("")

    # Root pages
    lines += ["## Meta", "",
              f"- [Documentation update log]({base}log/): dated history of changes to this bundle.", ""]
    log = DOCS / "log.md"
    if log.exists():
        full += [f"---8<--- {base}log/", "", log.read_text(encoding='utf-8').rstrip(), ""]

    (DOCS / "llms.txt").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    (DOCS / "llms-full.txt").write_text("\n".join(full).rstrip() + "\n", encoding="utf-8")
    print(f"llms.txt: {n} pages indexed; llms-full.txt: "
          f"{(DOCS / 'llms-full.txt').stat().st_size // 1024} KB")


if __name__ == "__main__":
    sys.exit(main())
