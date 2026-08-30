#!/usr/bin/env python3
"""Build the whole site in the UNM Cascade webcore standard.

Replaces Zensical rendering for this repository: every Markdown page in
docs/ (the OKF v0.2 bundle) is converted to HTML and wrapped in the standard
UNM Cascade chrome — webcore navbar, department banner, section navigation,
breadcrumbs, department + UNM global footer, Quick Links panel — with a plain
Bootstrap content column (no Zensical/Material theming). The hand-authored
Googie homepage (web/index.html) is installed at the root.

Pipeline order:
    python3 scripts/build_cascade_site.py        # this script -> site/
    python3 scripts/postbuild_agent_surface.py   # md mirror, meta, robots.txt

Requires: pyyaml, markdown  (pip install pyyaml markdown)
"""

from __future__ import annotations

import html
import posixpath
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import markdown
import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE = ROOT / "site"

SECTIONS = [
    ("about", "About"),
    ("research", "Research"),
    ("education", "Education"),
    ("news", "News"),
    ("contact", "Contact"),
]

MD_EXTENSIONS = ["extra", "admonition", "sane_lists", "smarty"]


def site_url() -> str:
    text = (ROOT / "zensical.toml").read_text(encoding="utf-8")
    m = re.search(r'^site_url\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return (m.group(1) if m else "/").rstrip("/") + "/"


def split_frontmatter(text: str):
    if text.startswith("---"):
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
        if m:
            try:
                fm = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError:
                fm = {}
            return (fm if isinstance(fm, dict) else {}), text[m.end():]
    return {}, text


def pretty_dir(rel: Path) -> str:
    """Source path -> site-relative pretty directory ('' for root index)."""
    if rel.name == "index.md":
        d = str(rel.parent)
        return "" if d == "." else d + "/"
    return str(rel.with_suffix("")) + "/"


def rewrite_md_links(html_text: str, page_dir: str) -> str:
    """Rewrite hrefs pointing at .md sources to their pretty URLs."""
    def sub(m):
        href = m.group(2)
        if href.startswith(("http://", "https://", "mailto:", "#", "/")):
            return m.group(0)
        path, _, frag = href.partition("#")
        if not path.endswith(".md"):
            return m.group(0)
        target = posixpath.normpath(posixpath.join(page_dir or ".", path))
        if target.startswith(".."):
            return m.group(0)
        tdir = pretty_dir(Path(target))
        rel = posixpath.relpath("/" + tdir, "/" + (page_dir or ""))
        out = ("" if rel == "." else rel.rstrip("/") + "/") or "./"
        if frag:
            out += "#" + frag
        return f'{m.group(1)}"{out}"'

    return re.sub(r'(href=)"([^"]+)"', sub, html_text)


def okf_meta(fm: dict) -> str:
    def tier(f):
        v = f.get("verified")
        if not v:
            return "unverified"
        entries = v if isinstance(v, list) else [v]
        return ("human-reviewed" if any(str(e.get("by", "")).startswith("human:")
                for e in entries if isinstance(e, dict)) else "machine-confirmed")
    lines = ['<meta name="robots" content="index, follow, max-snippet:-1, '
             'max-image-preview:large, max-video-preview:-1">',
             '<link rel="alternate" type="text/markdown" '
             'title="Markdown source (OKF v0.2 frontmatter)" href="index.md">']
    def meta(n, v):
        if v:
            lines.append(f'<meta name="{n}" content="{html.escape(str(v), quote=True)}">')
    meta("okf:type", fm.get("type"))
    meta("okf:status", fm.get("status", "stable"))
    meta("okf:trust-tier", tier(fm))
    gen = fm.get("generated") or {}
    if isinstance(gen, dict):
        meta("okf:generated-at", gen.get("at"))
        meta("okf:generated-by", gen.get("by"))
    meta("okf:stale-after", fm.get("stale_after"))
    return "\n".join(lines)


# --- Cascade chrome (scraped verbatim from carc.unm.edu) --------------------

NAVBAR = """<div aria-label="header navigation" class="navbar navbar-unm" role="navigation"><div class="container"><a class="navbar-brand" href="https://www.unm.edu">The University of New Mexico</a><form action="//search.unm.edu/search" class="pull-right" id="unm_search_form" method="get"><div class="input-append search-query"><input accesskey="4" id="unm_search_form_q" maxlength="255" name="q" placeholder="Search" title="input search query here" type="text"><button accesskey="s" class="btn" id="unm_search_for_submit" name="submit" title="submit search" type="submit">  <span class="fa fa-search"></span> </button></div></form><ul class="nav navbar-nav navbar-right hidden-xs" id="toolbar-nav"><li><a href="https://directory.unm.edu/departments/" title="UNM A to Z">UNM A-Z</a></li><li><a href="https://my.unm.edu" title="myUNM">myUNM</a></li><li><a href="https://directory.unm.edu" title="Directory">Directory</a></li><li class="dropdown"><a class="dropdown-toggle" data-toggle="dropdown" href="#">Help </a><ul class="dropdown-menu"><li><a href="https://student.unm.edu/student-support.html" title="Student Support">Student Support</a></li><li><a href="https://studentinfo.unm.edu" title="StudentInfo">StudentInfo</a></li><li><a href="https://fastinfo.unm.edu" title="FastInfo">FastInfo</a></li></ul></li><li class="unm_panel_open hidden-sm"><a href="#unm_panel">more <span class="caret"></span></a></li></ul></div></div>"""

FOOTER = """<div aria-label="unm footer" id="footer" role="contentinfo"><div class="container"><div id="primary_aside_5"><div class="adr"><p class="BasicParagraph"><a href="{base}" target="_blank"><strong>UNM Center for Advanced Research Computing</strong></a></p><br><table border="0" style="height: 40px; width: 800px;"><tbody><tr><td><p>MSC01 1190<br>1601 Central Ave NE <br>Albuquerque NM 87106</p><a href="http://www.unm.edu/legal.html" target="_blank">Legal</a></td><td><p>Fax: 505.277.8235<br>Email: <a href="mailto:info@carc.unm.edu" target="_blank">info@carc.unm.edu</a></p><p><a href="http://www.unm.edu/accessibility.html" target="_blank">Accessibility</a></p></td><td><a href="https://twitter.com/unmcarc" target="_blank"><img alt="UNM CARC on Twitter" height="50" src="https://carc.unm.edu/images/twitter-icon.png" width="50"></a><a href="https://www.facebook.com/centerforadvancedresearchcomputing/" target="_blank"><img alt="UNM CARC on Facebook" height="50" src="https://carc.unm.edu/images/facebook-icon.png" width="50"></a></td></tr></tbody></table><p class="BasicParagraph"></p></div></div><hr><div class="row"><div class="col-md-8"><p><a href="https://www.unm.edu"><img alt="The University of New Mexico" src="https://webcore.unm.edu/v2/images/unm-transparent-white.png"></a></p><p class="small">© The University of New Mexico <br> Albuquerque, NM 87131, (505) 277-0111 <br> New Mexico's Flagship University</p></div><div class="col-md-4"><ul class="list-inline"><li><a href="https://www.facebook.com/universityofnewmexico" title="UNM on Facebook"><span class="fa fa-facebook-square fa-2x"><span class="sr-only">UNM on Facebook</span></span></a></li><li><a href="https://instagram.com/uofnm" title="UNM on Instagram"><span class="fa fa-instagram fa-2x"><span class="sr-only">UNM on Instagram</span></span></a></li><li><a href="https://twitter.com/unm" title="UNM on Twitter"><span class="fa fa-twitter-square fa-2x"><span class="sr-only">UNM on Twitter</span></span></a></li><li><a href="https://www.youtube.com/user/unmlive" title="UNM on YouTube"><span class="fa fa-youtube-square fa-2x"><span class="sr-only">UNM on YouTube</span></span></a></li></ul><p>more at <a class="link-underline" href="https://social.unm.edu" title="UNM Social Media Directory &amp; Information">social.unm.edu</a></p><ul class="list-inline" id="unm_footer_links"><li><a href="https://www.unm.edu/accessibility.html">Accessibility</a></li><li><a href="https://www.unm.edu/legal.html">Legal</a></li><li><a href="https://www.unm.edu/contactunm.html">Contact UNM</a></li><li><a href="https://www.unm.edu/consumer-information/">Consumer Information</a></li><li><a href="https://hed.state.nm.us/resources-for-schools/public_schools/tableau-charts-and-tables">New Mexico Higher Education Dashboard</a></li></ul></div></div></div></div>"""

PANEL = """<div id="unm_panel" class="hidden-xs hidden-sm"><div class="container"><div class="row">
<div class="col-sm-4"><aside><h1>Quick Links</h1><div class="row quicklinks"><div class="col-lg-6 media"><a href="https://canvas.unm.edu"><span class="pull-left fa fa-graduation-cap fa-3x"></span><div class="media-body"><h2>UNM Canvas</h2> Online Classes</div></a></div><div class="col-lg-6 media"><a href="https://lobomail.unm.edu"><span class="pull-left fa fa-envelope fa-3x"></span><div class="media-body"><h2>LoboMail</h2> email and calendar</div></a></div><div class="col-lg-6 media"><a href="https://library.unm.edu"><span class="pull-left fa fa-book fa-3x"></span><div class="media-body"><h2>Library</h2> library services</div></a></div><div class="col-lg-6 media"><a href="https://my.unm.edu"><span class="pull-left fa fa-circle fa-3x"></span><div class="media-body"><h2>MyUNM</h2> campus portal</div></a></div><div class="col-lg-6 media"><a href="https://studentinfo.unm.edu"><span class="pull-left fa fa-support fa-3x"></span><div class="media-body"><h2>StudentInfo</h2> Student Support</div></a></div><div class="col-lg-6 media"><a href="https://fastinfo.unm.edu"><span class="pull-left fa fa-support fa-3x"></span><div class="media-body"><h2>FastInfo</h2> Faculty and Staff support</div></a></div><div class="col-lg-6 media"><a href="https://directory.unm.edu/departments/"><span class="pull-left fa fa-sort-alpha-asc fa-3x"></span><div class="media-body"><h2>UNM A-Z</h2> departments and services</div></a></div><div class="col-lg-6 media"><a href="https://directory.unm.edu"><span class="pull-left fa fa-phone-square fa-3x"></span><div class="media-body"><h2>Directory</h2> student, staff, and faculty</div></a></div><div class="col-lg-6 media"><a href="https://students.unm.edu"><span class="pull-left fa fa-group fa-3x"></span><div class="media-body"><h2>Students.UNM</h2> get started at UNM</div></a></div></div></aside></div>
<div class="col-sm-4"></div>
<div class="col-sm-4"><aside><h1 class="padlock">LoboAlerts</h1><p><strong><a href="https://www.getrave.com/login/unm">Log into LoboAlerts now!</a></strong><br> <br> <a href="https://loboalerts.unm.edu/faq.html">LoboAlerts FAQ</a><a href="http://loboalerts.unm.edu"><br> More info about LoboAlerts</a></p><h1 class="padlock">Join The Pack</h1><ul class="list-inline"><li><a href="https://www.facebook.com/universityofnewmexico" title="UNM on Facebook"><span class="fa fa-facebook-square fa-2x"><span class="sr-only">UNM on Facebook</span></span></a></li><li><a href="https://instagram.com/uofnm" title="UNM on Instagram"><span class="fa fa-instagram fa-2x"><span class="sr-only">UNM on Instagram</span></span></a></li><li><a href="https://twitter.com/unm" title="UNM on Twitter"><span class="fa fa-twitter-square fa-2x"><span class="sr-only">UNM on Twitter</span></span></a></li><li><a href="https://www.youtube.com/user/unmlive" title="UNM on YouTube"><span class="fa fa-youtube-square fa-2x"><span class="sr-only">UNM on YouTube</span></span></a></li></ul><p>more at <a href="https://social.unm.edu">social.unm.edu</a></p></aside></div>
</div></div></div>"""

PAGE_CSS = """<style>
:root { --pg-bg:#ffffff; --pg-fg:#3a3a3a; --pg-muted:#63666a; --pg-card:#faf8f4;
  --pg-border:#dddddd; --pg-link:#ba0c2f; --pg-strip:#f4f2ee; }
html[data-theme="dark"] { --pg-bg:#14161d; --pg-fg:#e8e6e1; --pg-muted:#a7a8aa;
  --pg-card:#1c1f28; --pg-border:#333845; --pg-link:#4fd3e0; --pg-strip:#10131a; }
@media (prefers-color-scheme: dark) {
  html:not([data-theme="light"]) { --pg-bg:#14161d; --pg-fg:#e8e6e1; --pg-muted:#a7a8aa;
    --pg-card:#1c1f28; --pg-border:#333845; --pg-link:#4fd3e0; --pg-strip:#10131a; }
}
/* sticky footer: short pages pin the footer to the viewport bottom,
   so it sits at the same height on every section page */
html, body { height: 100%; }
#page { min-height: 100vh; display: flex; flex-direction: column; }
#page > #main { flex: 1 0 auto; min-height: calc(100vh - 180px); }
#page > .navbar, #page > #header, #page > #nav, #page > #breadcrumbs,
#page > #footer { flex: 0 0 auto; }
#page { background: var(--pg-bg) !important; }
#header h1 { color: var(--pg-fg) !important; }
#footer table { width: 100% !important; height: auto !important; }
#footer td { padding-right: 1em; }
#carc-content table { display: block; overflow-x: auto; }
#main, #carc-content { background: var(--pg-bg); color: var(--pg-fg); }
#carc-content h1, #carc-content h2, #carc-content h3, #carc-content h4 { color: var(--pg-fg); }
#carc-content a { color: var(--pg-link); }
#carc-content p, #carc-content li, #carc-content td { color: var(--pg-fg); }
#nav { background: var(--pg-strip); }
#breadcrumbs .breadcrumb a { color: var(--pg-link); }
#breadcrumbs .breadcrumb .active { color: var(--pg-muted); }
.carc-ext-btn { border: 2px solid #ba0c2f; border-radius: 999px; padding: .3em 1em !important;
  margin: .25em .15em; font-weight: 700; }
.carc-ext-btn:hover { background: #ba0c2f; color: #fff !important; }
.carc-theme-li { float: right; }
#carc-theme-btn { border: none; background: transparent; color: var(--pg-link);
  font-size: 1.35em; line-height: 1; padding: .15em .35em; margin: .3em 0;
  cursor: pointer; transition: transform .15s; }
#carc-theme-btn:hover { transform: scale(1.25) rotate(-12deg); }
#carc-content { padding: 1.6em 0 3em; }
#carc-content .col-content { max-width: 62em; }
#carc-content img { max-width: 100%; height: auto; }
#carc-content table { width: 100%; margin: 1em 0 1.5em; border-collapse: collapse; }
#carc-content table th { background: var(--pg-strip); }
#carc-content table th, #carc-content table td { border: 1px solid var(--pg-border); padding: .5em .7em; vertical-align: top; }
#carc-content .admonition { border-left: 5px solid #ba0c2f; background: var(--pg-card);
  padding: .8em 1em .6em; margin: 1.2em 0; border-radius: 0 4px 4px 0;
  box-shadow: 0 1px 4px rgba(0,0,0,.07); }
#carc-content .admonition-title { font-weight: 700; margin: 0 0 .3em; color: #ba0c2f; }
#carc-content .admonition.note, #carc-content .admonition.info, #carc-content .admonition.tip
  { border-left-color: #007a86; }
#carc-content .admonition.note .admonition-title, #carc-content .admonition.info .admonition-title,
#carc-content .admonition.tip .admonition-title { color: #007a86; }
#carc-content .admonition.success { border-left-color: #4a7729; }
#carc-content .admonition.success .admonition-title { color: #4a7729; }
#carc-content .admonition.quote { border-left-color: #a7a8aa; font-style: italic; }
#carc-content .admonition.quote .admonition-title { color: #63666a; font-style: normal; }
#carc-content .carc-byline { text-transform: uppercase; letter-spacing: .08em;
  font-size: .85em; color: var(--pg-muted); margin-top: -0.5em; }
#carc-content .md-button { display: inline-block; background: #ba0c2f; color: #fff;
  padding: .5em 1.2em; border-radius: 3px; text-decoration: none; margin: .2em 0; }
#carc-content .md-button:hover { background: #8a0923; color: #fff; }
#breadcrumbs .breadcrumb { background: transparent; margin: .6em 0 0; padding: 0; }
#nav ul.carc-sections { margin: 0; padding: 0; list-style: none; }
#nav ul.carc-sections li { display: inline-block; }
#nav ul.carc-sections li a { display: inline-block; padding: .7em 1em; color: var(--pg-link); text-decoration: none; }
#nav ul.carc-sections li.active a, #nav ul.carc-sections li a:hover { background: #ba0c2f; color: #fff; }
</style>"""

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} :: Center for Advanced Research Computing | The University of New Mexico</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<link rel="icon" href="{rel_root}assets/unm.ico">
{okf}
<link rel="stylesheet" href="https://webcore.unm.edu/v2/fonts/unm-fonts.css">
<link rel="stylesheet" href="https://webcore.unm.edu/v2/css/unm-styles.min.css">
{css}
</head>
<body>
<a class="sr-only sr-only-focusable skip2content" href="#carc-content">Skip to main content</a>
<div id="page">
{navbar}
<div aria-label="department logo block" id="header" role="banner"><div class="container"><a href="{rel_root}"><h1>Center for Advanced Research Computing</h1></a></div></div>
<div id="nav"><div class="container"><ul class="carc-sections">
{navitems}
</ul></div></div>
<div aria-label="breadcrumbs" id="breadcrumbs" role="navigation"><div class="container"><ol class="breadcrumb">
{crumbs}
</ol></div></div>
<div id="main" role="main"><main id="carc-content"><div class="container"><div class="col-content">
{content}
</div></div></main></div>
{footer}
</div>
<div id="totop"><span class="fa fa-arrow-circle-up"></span></div>
{panel}
<script src="https://webcore.unm.edu/v2/js/unm-scripts.min.js"></script>
<script>
(function () {{
  var KEY = "carc-theme", root = document.documentElement, saved = null;
  try {{ saved = localStorage.getItem(KEY); }} catch (e) {{}}
  if (saved) root.setAttribute("data-theme", saved);
  var btn = document.getElementById("carc-theme-btn");
  function isDark() {{
    var d = root.getAttribute("data-theme");
    if (d) return d === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }}
  function label() {{ if (btn) btn.textContent = isDark() ? "☀" : "☾"; }}
  if (btn) {{
    label();
    btn.addEventListener("click", function () {{
      var next = isDark() ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {{ localStorage.setItem(KEY, next); }} catch (e) {{}}
      label();
    }});
  }}
}})();
</script>
</body>
</html>
"""


def nav_items(rel_root: str, active: str) -> str:
    items = []
    for slug, label in SECTIONS:
        cls = ' class="active"' if slug == active else ""
        items.append(f'<li{cls}><a href="{rel_root}{slug}/">{label}</a></li>')
    items.append('<li><a class="carc-ext-btn" href="https://unm-carc.github.io/docs/" '
                 'target="_blank" rel="noopener">User Documentation <span aria-hidden="true">↗</span></a></li>')
    items.append('<li><a class="carc-ext-btn" href="https://support.alliance.unm.edu/" '
                 'target="_blank" rel="noopener">Help Desk <span aria-hidden="true">↗</span></a></li>')
    items.append('<li class="carc-theme-li"><button id="carc-theme-btn" type="button" '
                 'aria-label="Toggle day / night theme" title="Toggle day / night theme">☾</button></li>')
    return "\n".join(items)


def crumbs_for(rel: Path, title: str, rel_root: str) -> str:
    out = [f'<li><a href="{rel_root}">Home</a></li>']
    parts = list(rel.parts[:-1]) if rel.name == "index.md" else list(rel.parts[:-1])
    section = dict(SECTIONS)
    walked = ""
    for i, part in enumerate(parts):
        walked += part + "/"
        label = section.get(part, part.replace("-", " ").title()) if i == 0 else part.replace("-", " ").upper() if part == "cse" else part.replace("-", " ").title()
        if part == "cse":
            label = "CSE Certificate"
        if rel.name == "index.md" and i == len(parts) - 1:
            out.append(f"<li class=\"active\">{html.escape(label)}</li>")
        else:
            depth = len(pretty_dir(rel).rstrip("/").split("/")) if pretty_dir(rel) else 0
            up = "../" * (depth - (i + 1))
            out.append(f'<li><a href="{up}">{html.escape(label)}</a></li>')
    if rel.name != "index.md":
        out.append(f"<li class=\"active\">{html.escape(title)}</li>")
    return "\n".join(out)


def main():
    base = site_url()
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    urls = []
    for src in sorted(DOCS.rglob("*.md")):
        rel = src.relative_to(DOCS)
        if rel.parts[0] in ("assets", "stylesheets"):
            continue
        fm, body = split_frontmatter(src.read_text(encoding="utf-8"))
        pdir = pretty_dir(rel)
        title = fm.get("title") or next(
            (l[2:].strip() for l in body.splitlines() if l.startswith("# ")),
            rel.stem.replace("-", " ").title())
        content = markdown.markdown(body, extensions=MD_EXTENSIONS)
        content = rewrite_md_links(content, pdir)
        depth = len(pdir.rstrip("/").split("/")) if pdir else 0
        rel_root = "../" * depth if depth else "./"
        page = TEMPLATE.format(
            title=html.escape(title),
            description=html.escape(fm.get("description", "")),
            canonical=base + pdir,
            rel_root=rel_root,
            okf=okf_meta(fm),
            css=PAGE_CSS,
            navbar=NAVBAR,
            navitems=nav_items(rel_root, rel.parts[0] if len(rel.parts) > 1 or rel.name != "index.md" else ""),
            crumbs=crumbs_for(rel, title, rel_root),
            content=content,
            footer=FOOTER.format(base=base),
            panel=PANEL,
        )
        if pdir == "":
            continue  # root index.md: homepage comes from web/, mirror serves index.md
        out = SITE / pdir / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
        urls.append(base + pdir)

    # homepage + assets
    shutil.copy2(ROOT / "web" / "index.html", SITE / "index.html")
    urls.insert(0, base)
    if (DOCS / "assets").exists():
        shutil.copytree(DOCS / "assets", SITE / "assets", dirs_exist_ok=True)

    # sitemap
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    lastmod = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sm += [f"<url><loc>{u}</loc><lastmod>{lastmod}</lastmod></url>" for u in urls]
    sm.append("</urlset>")
    (SITE / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")

    # llms indexes ship with the site
    for f in ("llms.txt", "llms-full.txt"):
        if (DOCS / f).exists():
            shutil.copy2(DOCS / f, SITE / f)

    print(f"cascade site: {len(urls)} pages (incl. homepage), sitemap, assets")


if __name__ == "__main__":
    main()
