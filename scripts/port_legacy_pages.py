#!/usr/bin/env python3
"""One-shot: port legacy carc.unm.edu pages into docs/ from migration/pages.yml.

Sibling of migrate_assets.py — a migration tool, not a build step. It talks to
the network (once; fetched HTML is cached under .legacy-cache/, laid out by
legacy path so migrate_assets.py --cache can share it) and never runs in CI.

For every manifest row with `action: port` it

  1. fetches the old page and takes the content column (div#primary),
  2. converts the Cascade WYSIWYG markup to the Markdown dialect this site
     renders (python-markdown: extra, admonition, sane_lists, smarty),
  3. writes docs/<to> with OKF v0.2 frontmatter in the shape of
     docs/news/sc24-team.md — `sources[].resource` records the legacy URL, which
     is what makes scripts/gen_htaccess.py emit the 301,
  4. maps every image/PDF through migration/assets.yml (a row's `drop_images`
     list names legacy files to leave behind, e.g. ones gone from the old host
     or third-party logos), appending entries for
     files not yet localized (as text, under a marker, so the hand-written
     comments in that file survive) — run scripts/migrate_assets.py afterwards
     to actually fetch and optimize them,
  5. rewrites links to the ported legacy URLs everywhere under docs/ to relative
     .md links (the build turns those into real URLs), and
  6. regenerates the marker-delimited Archive in docs/news/index.md.

A page that a human has touched — `verified:` present, or `generated.by` that is
not this script — is never overwritten without --force. Re-runs are idempotent
when --at is fixed.

Usage:
    python3 scripts/port_legacy_pages.py [--dry-run] [--diff] [--only PATH|SLUG ...]
                                         [--offline] [--force] [--at ISO8601]
                                         [--no-index] [--no-rewrite]
"""

from __future__ import annotations

import argparse
import difflib
import html
import posixpath
import re
import sys
import textwrap
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_htaccess import from_provenance, page_url  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
MIGRATION = ROOT / "migration"
CACHE = ROOT / ".legacy-cache"
MANIFEST = MIGRATION / "pages.yml"
ASSETS_YML = MIGRATION / "assets.yml"

LEGACY_HOST = "https://carc.unm.edu"
LEGACY_HOST_RE = re.compile(r"^https?://(?:www\.)?carc\.unm\.edu(/.*)?$", re.I)
ASSET_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".xlsx", ".docx", ".pptx"}
ACTOR = "process:scripts/port_legacy_pages.py"
MARK_START = "<!-- archive:start -->"
MARK_END = "<!-- archive:end -->"
ASSETS_MARKER = "# --- Ported legacy pages (appended by scripts/port_legacy_pages.py) ---"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]

REPORT: dict[str, list[str]] = {}
REDIRECTS: dict[str, str] = {}
INVENTORY: set[str] = set()


def note(kind: str, msg: str) -> None:
    REPORT.setdefault(kind, []).append(msg)


# --- fetching -----------------------------------------------------------------

def fetch(legacy_path: str, offline: bool) -> str:
    local = CACHE / legacy_path.lstrip("/")
    if local.is_file():
        return local.read_text(encoding="utf-8", errors="replace")
    if offline:
        raise SystemExit(f"error: {legacy_path} is not cached and --offline was given")
    url = LEGACY_HOST + urllib.parse.quote(legacy_path)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 carc-port"})
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode("utf-8", "replace")
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(text, encoding="utf-8")
    return text


def primary_fragment(page: str) -> str:
    """The content column of a Cascade page: div#primary up to div#secondary."""
    i = page.find('id="primary"')
    if i < 0:
        raise ValueError("no div#primary")
    i = page.index(">", i) + 1
    j = page.find('id="secondary"', i)
    if j < 0:
        j = page.find('id="lower"', i)
    frag = page[i:j] if j > 0 else page[i:]
    # drop the dangling "<div" that opens #secondary and the </div> closing #primary
    frag = re.sub(r"<div\s*$", "", frag.rstrip())
    return frag


# --- HTML -> Markdown ---------------------------------------------------------

def esc(text: str) -> str:
    """Escape the few characters that would otherwise become Markdown."""
    return re.sub(r"([*_`\\])", r"\\\1", text)


class Converter(HTMLParser):
    """Walk the content column and emit blocks.

    Blocks are ("p", inline_text), ("h", level, text), ("li", ordered, [items]),
    ("img", src, alt), ("raw", html).
    """

    BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
                  "table", "blockquote", "pre", "figure", "figcaption"}

    def __init__(self, page_url: str, link_fn, image_fn):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.link_fn = link_fn      # href -> markdown target text (with {target=_blank} when external)
        self.image_fn = image_fn    # src -> /assets/name
        self.blocks: list = []
        self.cur: list[str] = []
        self.stack: list[str] = []
        self.list_stack: list[tuple[bool, list[str]]] = []
        self.link: list[dict] | None = None
        self.h1: str | None = None
        self.pre = False

    # -- helpers
    def flush(self) -> None:
        text = "".join(self.cur)
        self.cur = []
        text = re.sub(r"[ \t\r\n\xa0]+", " ", text).strip()
        if not text:
            return
        if self.list_stack:
            self.list_stack[-1][1].append(text)
        elif self.stack and self.stack[-1] in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(self.stack[-1][1])
            if level == 1 and self.h1 is None:
                self.h1 = text
            else:
                self.blocks.append(("h", min(max(level, 2), 4), text))
        else:
            self.blocks.append(("p", text))

    def emit_text(self, s: str) -> None:
        if self.link is not None:
            self.link[-1]["text"].append(s)
        else:
            self.cur.append(s)

    # -- parser callbacks
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.flush()
            self.stack.append(tag)
        elif tag in ("p", "div", "blockquote", "figure", "figcaption", "table"):
            self.flush()
            self.stack.append(tag)
        elif tag in ("ul", "ol"):
            self.flush()
            self.list_stack.append((tag == "ol", []))
            self.stack.append(tag)
        elif tag == "li":
            self.flush()
            self.stack.append(tag)
        elif tag == "br":
            self.emit_text("<br>")
        elif tag == "img":
            src, alt = a.get("src", ""), (a.get("alt") or "").strip()
            self.flush()
            ref = self.image_fn(src, alt)
            if ref:
                self.blocks.append(("img", ref, clean_alt(alt, src)))
        elif tag == "a":
            href = a.get("href", "")
            self.link = (self.link or []) + [{"href": href, "text": []}]
        elif tag in ("strong", "b"):
            self.emit_text("**")
        elif tag in ("em", "i"):
            self.emit_text("*")
        elif tag in ("sub", "sup"):
            self.emit_text(f"<{tag}>")
        elif tag == "pre":
            self.flush()
            self.pre = True
            self.stack.append(tag)
        # span, font, u, etc. are transparent

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "blockquote",
                   "figure", "figcaption", "table", "pre"):
            self.flush()
            if tag == "pre":
                self.pre = False
            if self.stack and self.stack[-1] == tag:
                self.stack.pop()
        elif tag in ("ul", "ol"):
            self.flush()
            if self.list_stack:
                ordered, items = self.list_stack.pop()
                items = [i for i in items if i]
                if items:
                    self.blocks.append(("li", ordered, items))
            if self.stack and self.stack[-1] == tag:
                self.stack.pop()
        elif tag == "li":
            self.flush()
            if self.stack and self.stack[-1] == tag:
                self.stack.pop()
        elif tag == "a":
            if self.link:
                link = self.link.pop()
                self.link = self.link or None
                text = re.sub(r"\s+", " ", "".join(link["text"])).strip()
                if not text:
                    return  # an image or nothing was wrapped; the image block already stands
                self.cur.append(self.link_fn(link["href"], text))
        elif tag in ("strong", "b"):
            self.emit_text("**")
        elif tag in ("em", "i"):
            self.emit_text("*")
        elif tag in ("sub", "sup"):
            self.emit_text(f"</{tag}>")

    def handle_data(self, data):
        if self.pre:
            self.cur.append(data)
        else:
            self.emit_text(esc(data.replace("\xa0", " ")))


def clean_alt(alt: str, src: str) -> str:
    """Drop alt text that merely repeats the file name; keep real descriptions."""
    base = posixpath.basename(urllib.parse.unquote(src))
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", base)
    if not alt:
        return ""
    norm = lambda s: re.sub(r"\d+$", "", re.sub(r"[\W_]+", "", s.lower()))
    if norm(alt) in (norm(base), norm(stem)) or norm(re.sub(r"\.[A-Za-z0-9]+$", "", alt)) in (norm(base), norm(stem)):
        return ""
    return re.sub(r"\s+", " ", alt).strip()


def blocks_to_markdown(blocks: list, width: int = 78) -> str:
    out: list[str] = []
    for b in blocks:
        kind = b[0]
        if kind == "p":
            text = b[1]
            # tidy bold/italic markers that ended up around spaces
            text = re.sub(r"\*\*\s+", "** ", text)
            out.append(textwrap.fill(text, width, break_long_words=False, break_on_hyphens=False))
        elif kind == "h":
            out.append("#" * b[1] + " " + b[2])
        elif kind == "li":
            ordered, items = b[1], b[2]
            lines = []
            for n, item in enumerate(items, 1):
                marker = f"{n}. " if ordered else "* "
                lines.append(textwrap.fill(item, width, initial_indent=marker,
                                           subsequent_indent="  " if not ordered else "   ",
                                           break_long_words=False, break_on_hyphens=False))
            out.append("\n".join(lines))
        elif kind == "img":
            src, alt = b[1], b[2]
            piece = f"![{alt}]({src})"
            # a sentence-like alt (a caption) is also worth showing under the image
            if len(alt.split()) >= 6:
                piece += f"\n\n*{alt}*"
            out.append(piece)
        elif kind == "raw":
            out.append(b[1])
    return "\n\n".join(out).strip() + "\n"


# --- dates, bylines, descriptions -------------------------------------------

def human_date(date: str) -> str:
    if not date:
        return ""
    parts = date.split("-")
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{MONTHS[int(parts[1]) - 1]} {parts[0]}"
    return f"{MONTHS[int(parts[1]) - 1]} {int(parts[2])}, {parts[0]}"


def byline_html(author: str, date: str) -> str:
    bits = []
    if author:
        bits.append(f"By {author}")
    if date:
        bits.append(human_date(date))
    return f'<p class="carc-byline">{" · ".join(bits)}</p>' if bits else ""


BYLINE_RE = re.compile(r"^\*{0,2}By\s+([A-Z][^*]{2,80}?)\*{0,2}$")


def pull_byline(blocks: list) -> tuple[list, str]:
    """A leading 'By NAME' paragraph becomes the author."""
    for i, b in enumerate(blocks[:3]):
        if b[0] == "p":
            m = BYLINE_RE.match(b[1].strip())
            if m:
                author = m.group(1).strip().rstrip(".")
                return blocks[:i] + blocks[i + 1:], author
            break
    return blocks, ""


def make_description(blocks: list, limit: int = 220) -> str:
    for b in blocks:
        if b[0] == "p":
            text = b[1]
            text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
            text = re.sub(r"\[([^\]]*)\]\([^)]*\)(\{[^}]*\})?", r"\1", text)
            text = re.sub(r"<[^>]+>", "", text)
            text = text.replace("**", "").replace("\\", "")
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            if len(text) <= limit:
                return text
            first = re.match(r"^(.*?[.!?])(\s|$)", text)
            if first and 60 < len(first.group(1)) <= 300:
                return first.group(1).strip()
            cut = text[:limit]
            m = re.search(r"^(.*?[.!?])\s", cut)
            return (m.group(1) if m and len(m.group(1)) > 60 else cut.rsplit(" ", 1)[0] + "…").strip()
    return ""


# --- manifest, assets, page map ----------------------------------------------

def load_manifest() -> list[dict]:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}
    rows = []
    for r in data.get("pages") or []:
        if not isinstance(r, dict) or not r.get("from") or not r.get("to"):
            continue
        r = dict(r)
        r["action"] = r.get("action") or "port"
        r["date"] = str(r.get("date") or "").strip()
        r["author"] = (r.get("author") or "").strip()
        r["tags"] = r.get("tags") or ["News"]
        r["type"] = r.get("type") or "News"
        r["aliases"] = r.get("aliases") or []
        r["drop_images"] = [str(x) for x in (r.get("drop_images") or [])]
        rows.append(r)
    return rows


def load_assets() -> dict[str, str]:
    data = yaml.safe_load(ASSETS_YML.read_text(encoding="utf-8")) or {}
    return {e["from"]: e["to"] for e in data.get("assets") or [] if isinstance(e, dict)}


def append_assets(entries: list[dict], dry: bool) -> int:
    """Append new assets.yml entries as text so hand-written comments survive."""
    if not entries:
        return 0
    text = ASSETS_YML.read_text(encoding="utf-8")
    if ASSETS_MARKER not in text:
        text = text.rstrip("\n") + "\n\n  " + ASSETS_MARKER + "\n"
    lines = []
    for e in entries:
        lines.append(f"  - from: {e['from']}")
        lines.append(f"    to: {e['to']}")
        if e.get("alt"):
            alt = e["alt"].replace('"', '\\"')
            lines.append(f'    alt: "{alt}"')
    text = text.rstrip("\n") + "\n" + "\n".join(lines) + "\n"
    if not dry:
        ASSETS_YML.write_text(text, encoding="utf-8")
    return len(entries)


def load_redirects() -> dict[str, str]:
    """Hand-authored legacy redirects (migration/redirects-extra.yml): old path -> target URL."""
    f = MIGRATION / "redirects-extra.yml"
    data = yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else {}
    return {str(e["from"]): str(e["to"]) for e in (data or {}).get("redirects") or []
            if isinstance(e, dict) and e.get("from") and e.get("to")}


def load_inventory() -> set[str]:
    f = MIGRATION / "legacy-paths.txt"
    return {l for l in f.read_text(encoding="utf-8").splitlines() if l} if f.exists() else set()


def build_page_map(rows: list[dict]) -> dict[str, str]:
    """legacy path -> docs-relative .md path, for every page that has a home."""
    out: dict[str, str] = {}
    for old, url, _src in from_provenance():
        rel = url.strip("/")
        out[old] = (rel + "/index.md") if not rel else (rel + ".md" if not (DOCS / rel / "index.md").exists() else rel + "/index.md")
    for r in rows:
        if r["action"] in ("port", "manual"):
            out[r["from"]] = r["to"]
            for a in r["aliases"]:
                out[a] = r["to"]
    return out


# --- the port -----------------------------------------------------------------

def port_page(row: dict, page_map: dict[str, str], assets: dict[str, str],
              new_assets: list[dict], at: str, offline: bool) -> tuple[str, dict]:
    legacy_path = row["from"]
    page_url_abs = LEGACY_HOST + urllib.parse.quote(legacy_path)
    target_rel = row["to"]
    target_dir = posixpath.dirname(target_rel)
    slug = posixpath.basename(target_rel).replace(".md", "")
    used_assets: list[str] = []

    def rel_link(to_rel: str) -> str:
        rel = posixpath.relpath(to_rel, target_dir or ".")
        return rel

    def link_fn(href: str, text: str) -> str:
        href = href.strip()
        if href.startswith("mailto://"):
            href = "mailto:" + href[len("mailto://"):]
        if href.startswith(("mailto:", "#", "tel:")):
            return f"[{text}]({href})"
        absu = urllib.parse.urljoin(page_url_abs, href)
        m = LEGACY_HOST_RE.match(absu)
        if m:
            path = urllib.parse.unquote(m.group(1) or "/").split("#")[0].split("?")[0]
            ext = posixpath.splitext(path)[1].lower()
            if ext in ASSET_EXT:
                ref = asset_ref(path, "")
                return f"[{text}]({ref})" if ref else text
            if path in page_map:
                return f"[{text}]({rel_link(page_map[path])})"
            if path in ("/", "/index.html"):
                return f"[{text}](/)"
            if path.startswith("/docs/"):
                return f"[{text}]({path})"
            if path in REDIRECTS:
                to = REDIRECTS[path]
                return f"[{text}]({to})" if to.startswith("/") else f"[{text}]({to}){{target=_blank}}"
            if INVENTORY and path not in INVENTORY:
                note("dead legacy links unlinked", f"{legacy_path}: {path}")
                return text
            note("legacy links kept", f"{legacy_path}: {path}")
            return f"[{text}]({absu}){{target=_blank}}"
        return f"[{text}]({absu}){{target=_blank}}"

    def asset_ref(src: str, alt: str) -> str | None:
        absu = urllib.parse.urljoin(page_url_abs, src.strip())
        m = LEGACY_HOST_RE.match(absu)
        if not m:
            note("external images kept", f"{legacy_path}: {absu}")
            return absu
        path = urllib.parse.unquote(m.group(1) or "")
        if path in row["drop_images"]:
            note("images dropped per manifest", f"{legacy_path}: {path}")
            return None
        if path in assets:
            name = assets[path]
        else:
            base = posixpath.basename(path)
            stem, ext = posixpath.splitext(base)
            stem = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
            stem = re.sub(r"-?\d*$", "", stem) or stem  # drop Cascade's numeric suffixes (photo1.jpg)
            name = f"{slug}-{stem}{ext.lower()}" if not stem.startswith(slug) else f"{stem}{ext.lower()}"
            taken = set(assets.values()) | {e["to"] for e in new_assets}
            n = 2
            while name in taken or (DOCS / "assets" / name).exists() and path not in assets:
                name = f"{slug}-{stem}-{n}{ext.lower()}"
                n += 1
            assets[path] = name
            new_assets.append({"from": path, "to": name, "alt": alt})
        used_assets.append(name)
        return f"/assets/{name}"

    def image_fn(src: str, alt: str) -> str:
        return asset_ref(src, clean_alt(alt, src))

    page = fetch(legacy_path, offline)
    conv = Converter(page_url_abs, link_fn, image_fn)
    conv.feed(primary_fragment(page))
    conv.flush()
    blocks, found_author = pull_byline(conv.blocks)
    author = row["author"] or found_author
    title = row.get("title") or conv.h1 or slug
    description = row.get("description") or make_description(blocks)
    if not row.get("description"):
        note("auto descriptions to polish", f"{target_rel}")
    if not row["date"]:
        note("undated", f"{target_rel}")

    fm = {
        "title": title,
        "description": description,
        "type": row["type"],
        "tags": list(row["tags"]),
    }
    if row["date"]:
        fm["date"] = row["date"]
    fm["generated"] = {"by": ACTOR, "at": at}
    sources = [{"id": "carc-web", "resource": LEGACY_HOST + legacy_path,
                "title": f"{title} (carc.unm.edu)", "author": "team:unm-carc"}]
    for n, alias in enumerate(row["aliases"], 2):
        sources.append({"id": f"carc-web-{n}", "resource": LEGACY_HOST + alias,
                        "title": f"{title}, duplicate address (carc.unm.edu)", "author": "team:unm-carc"})
    fm["sources"] = sources

    body = f"# {title}\n\n"
    bl = byline_html(author, row["date"])
    if bl:
        body += bl + "\n\n"
    body += blocks_to_markdown(blocks)
    text = f"---\n{frontmatter_text(fm)}\n---\n\n{body}"
    return text, {"assets": used_assets, "author": author}


def yq(s: str) -> str:
    """Double-quoted YAML scalar, the way the hand-written pages are formatted."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def frontmatter_text(fm: dict) -> str:
    """Emit frontmatter in the same shape as docs/news/sc24-team.md."""
    lines = [f"title: {yq(fm['title'])}", f"description: {yq(fm['description'])}", f"type: {fm['type']}", "tags:"]
    lines += [f"  - {tag}" for tag in fm["tags"]]
    if fm.get("date"):
        lines.append(f"date: {yq(fm['date'])}")
    lines += ["generated:", f"  by: {yq(fm['generated']['by'])}", f"  at: {yq(fm['generated']['at'])}", "sources:"]
    for s in fm["sources"]:
        lines += [f"  - id: {s['id']}", f"    resource: {yq(s['resource'])}", f"    title: {yq(s['title'])}",
                  f"    author: {yq(s['author'])}"]
    return "\n".join(lines)


def guard(target: Path, force: bool) -> str | None:
    """Why this target must not be overwritten (None = fine)."""
    if not target.exists() or force:
        return None
    head = target.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", head, re.DOTALL)
    fm = yaml.safe_load(m.group(1)) if m else {}
    fm = fm if isinstance(fm, dict) else {}
    if fm.get("verified"):
        return "carries verified:"
    by = str((fm.get("generated") or {}).get("by", ""))
    if by and by != ACTOR:
        return f"generated.by is {by!r}"
    return None


# --- rewriting links elsewhere & the archive index ---------------------------

def rewrite_links(page_map: dict[str, str], ported: set[str], dry: bool) -> int:
    changed = 0
    for md in sorted(DOCS.rglob("*.md")):
        rel = md.relative_to(DOCS)
        if rel.parts[0] == "assets" or rel.name in ("log.md",) or rel.suffix != ".md":
            continue
        if rel.name.startswith("llms"):
            continue
        text = original = md.read_text(encoding="utf-8")
        here = posixpath.dirname(str(rel).replace("\\", "/"))
        for old in ported:
            to = page_map[old]
            if str(rel) == to:
                continue
            new = posixpath.relpath(to, here or ".")
            for variant in (old, urllib.parse.quote(old), old.replace(" ", "%20")):
                pat = re.compile(r"\]\(https?://(?:www\.)?carc\.unm\.edu" + re.escape(variant) + r"\)(\{target=_blank\})?")
                text = pat.sub(f"]({new})", text)
        if text != original:
            changed += 1
            if not dry:
                md.write_text(text, encoding="utf-8")
    return changed


def frontmatter_of(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}
    return fm if isinstance(fm, dict) else {}


def regenerate_archive(dry: bool) -> bool:
    index = DOCS / "news" / "index.md"
    text = index.read_text(encoding="utf-8")
    if MARK_START not in text or MARK_END not in text:
        note("index", f"{index.relative_to(ROOT)} has no {MARK_START} / {MARK_END} markers; archive not regenerated")
        return False
    head, rest = text.split(MARK_START, 1)
    _old, tail = rest.split(MARK_END, 1)
    linked_above = set(re.findall(r"\]\(([^)]+\.md)\)", head))
    entries = []
    for md in sorted((DOCS / "news").glob("*.md")):
        if md.name == "index.md" or md.name in linked_above:
            continue
        fm = frontmatter_of(md)
        date = str(fm.get("date") or "")
        entries.append((date[:4] if date else "", date, fm.get("title") or md.stem, fm.get("description") or "", md.name))
    years = sorted({e[0] for e in entries if e[0]}, reverse=True)
    out = ["", "## Archive", "",
           "Older stories, by year. Stories from the previous website are being brought",
           "into this archive as they are ported; the rest still serve at their original",
           "carc.unm.edu addresses.", ""]
    for y in years + ([""] if any(not e[0] for e in entries) else []):
        out.append(f"### {y or 'Undated'}")
        out.append("")
        for _y, date, title, desc, name in sorted((e for e in entries if e[0] == y), key=lambda e: (e[1], e[2]), reverse=True):
            line = f"* [{title}]({name})"
            if desc:
                line += f" - {desc}"
            out.append(line)
        out.append("")
    new = head + MARK_START + "\n" + "\n".join(out) + MARK_END + tail
    if new != text and not dry:
        index.write_text(new, encoding="utf-8")
    return new != text


# --- main ---------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("--diff", action="store_true", help="show a unified diff for pages that already exist")
    ap.add_argument("--only", action="append", default=[], help="legacy path or slug; repeatable")
    ap.add_argument("--offline", action="store_true", help="fail instead of fetching anything not in .legacy-cache/")
    ap.add_argument("--force", action="store_true", help="overwrite pages a human has verified or authored")
    ap.add_argument("--at", default="2026-09-10T00:00:00Z", help="generated.at stamp (fixed so re-runs are byte-identical)")
    ap.add_argument("--no-index", action="store_true", help="do not regenerate the docs/news/index.md archive")
    ap.add_argument("--no-rewrite", action="store_true", help="do not rewrite legacy links elsewhere in docs/")
    args = ap.parse_args()

    rows = load_manifest()
    assets = load_assets()
    REDIRECTS.update(load_redirects())
    INVENTORY.update(load_inventory())
    page_map = build_page_map(rows)
    new_assets: list[dict] = []
    ported: set[str] = set()
    written = skipped = 0

    for row in rows:
        if row["action"] != "port":
            continue
        slug = posixpath.basename(row["to"]).replace(".md", "")
        if args.only and row["from"] not in args.only and slug not in args.only:
            continue
        target = DOCS / row["to"]
        why = guard(target, args.force)
        if why:
            skipped += 1
            note("skipped (human-owned)", f"{row['to']}: {why}")
            ported.add(row["from"])  # still a home for links
            continue
        try:
            text, info = port_page(row, page_map, assets, new_assets, args.at, args.offline)
        except Exception as e:  # noqa: BLE001 — report and keep going
            note("FAILED", f"{row['from']}: {e}")
            continue
        if args.diff and target.exists():
            old = target.read_text(encoding="utf-8").splitlines(keepends=True)
            sys.stdout.writelines(difflib.unified_diff(old, text.splitlines(keepends=True),
                                                       fromfile=str(row["to"]), tofile=str(row["to"]) + " (new)"))
        if not args.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        written += 1
        ported.add(row["from"])
        for a in row["aliases"]:
            ported.add(a)
        print(f"  {'would write' if args.dry_run else 'wrote':11} {row['to']:60} {row['date'] or '(undated)':10} "
              f"{('by ' + info['author']) if info['author'] else ''}  [{len(info['assets'])} asset(s)]")

    added = append_assets(new_assets, args.dry_run)
    changed = 0 if args.no_rewrite else rewrite_links(page_map, ported, args.dry_run)
    idx = False if args.no_index else regenerate_archive(args.dry_run)

    print(f"\n{written} page(s) {'would be ' if args.dry_run else ''}written, {skipped} skipped; "
          f"{added} new assets.yml entr{'y' if added == 1 else 'ies'}; {changed} page(s) with links rewritten; "
          f"archive index {'updated' if idx else 'unchanged'}"
          + ("   [dry run, nothing saved]" if args.dry_run else ""))
    if added:
        print("  -> run: python3 scripts/migrate_assets.py --cache .legacy-cache --only-missing")
    for kind, items in REPORT.items():
        print(f"\n{kind} ({len(items)}):")
        for it in items:
            print(f"  {it}")
    return 1 if REPORT.get("FAILED") else 0


if __name__ == "__main__":
    sys.exit(main())
