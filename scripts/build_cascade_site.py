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
import os
import re
import shutil
import sys
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

# Google Tag Manager container carried over from the Cascade-era homepage, so
# analytics continue uninterrupted after the swap. (The old Universal Analytics
# tag that sat beside it is not carried: Google retired UA in 2024.)
GTM_ID = "GTM-WQT2MB"
GTM_HEAD = (
    "<!-- Google Tag Manager -->\n"
    "<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':\n"
    "new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],\n"
    "j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=\n"
    "'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);\n"
    "})(window,document,'script','dataLayer','" + GTM_ID + "');</script>\n"
    "<!-- End Google Tag Manager -->"
)
GTM_BODY = (
    "<!-- Google Tag Manager (noscript) -->\n"
    '<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=' + GTM_ID + '"\n'
    'height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>\n'
    "<!-- End Google Tag Manager (noscript) -->"
)

# Pages rendered in the site chrome but served from the root under their own
# filename rather than a pretty directory, and kept out of the sitemap.
# 404.html backs the Apache ErrorDocument that gen_htaccess.py emits.
ROOT_HTML_PAGES = {"404.md": "404.html"}


def site_url() -> str:
    """Canonical site origin. CARC_SITE_URL overrides zensical.toml so a build can
    be pointed at a different host (a test push, CI) without a commit."""
    override = os.environ.get("CARC_SITE_URL")
    if override:
        return override.rstrip("/") + "/"
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


def rewrite_md_links(html_text: str, src_dir: str, page_dir: str) -> str:
    """Rewrite hrefs pointing at .md sources to their pretty URLs.

    Relative links in the Markdown are relative to the SOURCE file's
    directory (src_dir, e.g. "education/cse" for education/cse/requirements.md),
    while the emitted URL must be relative to the rendered page's pretty
    directory (page_dir, e.g. "education/cse/requirements/") — a non-index
    page gains one directory level when it becomes <page>/index.html.
    """
    def sub(m):
        href = m.group(2)
        if href.startswith(("http://", "https://", "mailto:", "#", "/")):
            return m.group(0)
        path, _, frag = href.partition("#")
        if not path.endswith(".md"):
            return m.group(0)
        target = posixpath.normpath(posixpath.join(src_dir or ".", path))
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


def cards_html(content: str) -> str:
    """Turn a list page (intro, then repeated `#### [Title](url)` + optional
    image + summary) into a card grid. The Markdown source stays a plain list
    editors can append to; only the rendered presentation changes."""
    chunks = re.split(r"(?=<h4\b)", content)
    intro, cards = chunks[0], []
    for chunk in chunks[1:]:
        m = re.match(r"<h4[^>]*>(.*?)</h4>(.*)", chunk, re.S)
        if not m:
            intro += chunk
            continue
        title_html, rest = m.group(1), m.group(2)
        link = re.search(r'<a\s[^>]*href="([^"]+)"[^>]*>', title_html)
        href = link.group(1) if link else None
        target = ' target="_blank" rel="noopener"' if link and 'target="_blank"' in link.group(0) else ""
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        img = re.search(r"<img\b[^>]*>", rest)
        media = ""
        if img:
            src = re.search(r'src="([^"]+)"', img.group(0))
            alt = re.search(r'alt="([^"]*)"', img.group(0))
            tag = (f'<img src="{src.group(1)}" alt="{alt.group(1) if alt else ""}" loading="lazy">'
                   if src else "")
            media = (f'<a class="carc-card-media" href="{href}"{target}>{tag}</a>' if href
                     else f'<div class="carc-card-media">{tag}</div>')
            rest = rest.replace(img.group(0), "", 1)
        summary = re.sub(r"<p>\s*</p>", "", rest).strip()
        heading = f'<a href="{href}"{target}>{title}</a>' if href else title
        more = (f'<a class="carc-card-more" href="{href}"{target}>Read the story '
                f'<span aria-hidden="true">→</span></a>' if href else "")
        cards.append(f'<article class="carc-card">{media}<div class="carc-card-body">'
                     f'<h3 class="carc-card-title">{heading}</h3>'
                     f'<div class="carc-card-text">{summary}</div>{more}</div></article>')
    return intro + '<div class="carc-cards">' + "".join(cards) + "</div>"


# --- Cascade chrome (scraped verbatim from carc.unm.edu) --------------------

NAVBAR = """<div aria-label="header navigation" class="navbar navbar-unm" role="navigation"><div class="container"><a class="navbar-brand" href="https://www.unm.edu">The University of New Mexico</a><form action="//search.unm.edu/search" class="pull-right" id="unm_search_form" method="get"><div class="input-append search-query"><input accesskey="4" id="unm_search_form_q" maxlength="255" name="q" placeholder="Search" title="input search query here" type="text"><button accesskey="s" class="btn" id="unm_search_for_submit" name="submit" title="submit search" type="submit">  <span class="fa fa-search"></span> </button></div></form><ul class="nav navbar-nav navbar-right hidden-xs" id="toolbar-nav"><li><a href="https://directory.unm.edu/departments/" title="UNM A to Z">UNM A-Z</a></li><li><a href="https://my.unm.edu" title="myUNM">myUNM</a></li><li><a href="https://directory.unm.edu" title="Directory">Directory</a></li><li class="dropdown"><a class="dropdown-toggle" data-toggle="dropdown" href="#">Help </a><ul class="dropdown-menu"><li><a href="https://student.unm.edu/student-support.html" title="Student Support">Student Support</a></li><li><a href="https://studentinfo.unm.edu" title="StudentInfo">StudentInfo</a></li><li><a href="https://fastinfo.unm.edu" title="FastInfo">FastInfo</a></li></ul></li><li class="unm_panel_open hidden-sm"><a href="#unm_panel">more <span class="caret"></span></a></li></ul></div></div>"""

FOOTER = """<div aria-label="unm footer" id="footer" role="contentinfo"><div class="container"><div id="primary_aside_5"><div class="adr"><p class="BasicParagraph"><a href="{base}" target="_blank"><strong>UNM Center for Advanced Research Computing</strong></a></p><br><table border="0" style="height: 40px; width: 800px;"><tbody><tr><td><p>MSC01 1190<br>1601 Central Ave NE <br>Albuquerque NM 87106</p><a href="http://www.unm.edu/legal.html" target="_blank">Legal</a></td><td><p>Fax: 505.277.8235<br>Email: <a href="mailto:info@carc.unm.edu" target="_blank">info@carc.unm.edu</a></p><p><a href="http://www.unm.edu/accessibility.html" target="_blank">Accessibility</a></p></td><td><a href="https://www.youtube.com/@UNMCARC" target="_blank" title="UNM CARC on YouTube"><span class="fa fa-youtube-square fa-3x"><span class="sr-only">UNM CARC on YouTube</span></span></a></td></tr></tbody></table><p class="BasicParagraph"></p></div></div><hr><div class="row"><div class="col-md-8"><p><a href="https://www.unm.edu"><img alt="The University of New Mexico" src="https://webcore.unm.edu/v2/images/unm-transparent-white.png"></a></p><p class="small">© The University of New Mexico <br> Albuquerque, NM 87131, (505) 277-0111 <br> New Mexico's Flagship University</p></div><div class="col-md-4"><ul class="list-inline"><li><a href="https://www.facebook.com/universityofnewmexico" title="UNM on Facebook"><span class="fa fa-facebook-square fa-2x"><span class="sr-only">UNM on Facebook</span></span></a></li><li><a href="https://instagram.com/uofnm" title="UNM on Instagram"><span class="fa fa-instagram fa-2x"><span class="sr-only">UNM on Instagram</span></span></a></li><li><a href="https://twitter.com/unm" title="UNM on Twitter"><span class="fa fa-twitter-square fa-2x"><span class="sr-only">UNM on Twitter</span></span></a></li><li><a href="https://www.youtube.com/user/unmlive" title="UNM on YouTube"><span class="fa fa-youtube-square fa-2x"><span class="sr-only">UNM on YouTube</span></span></a></li></ul><p>more at <a class="link-underline" href="https://social.unm.edu" title="UNM Social Media Directory &amp; Information">social.unm.edu</a></p><ul class="list-inline" id="unm_footer_links"><li><a href="https://www.unm.edu/accessibility.html">Accessibility</a></li><li><a href="https://www.unm.edu/legal.html">Legal</a></li><li><a href="https://www.unm.edu/contactunm.html">Contact UNM</a></li><li><a href="https://www.unm.edu/consumer-information/">Consumer Information</a></li><li><a href="https://hed.state.nm.us/resources-for-schools/public_schools/tableau-charts-and-tables">New Mexico Higher Education Dashboard</a></li></ul></div></div></div></div>"""

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
#page > .navbar, #page > #carc-masthead, #page > #nav, #page > #breadcrumbs,
#page > #footer { flex: 0 0 auto; }
#page { background: var(--pg-bg) !important; }
/* keep the UNM bar, but keep the brand tab from hanging into the masthead:
   render it as the white UNM wordmark inside the red bar */
.navbar-unm .navbar-brand { position: static !important; float: left; height: 40px !important;
  width: 210px !important; text-indent: -9999px; overflow: hidden;
  background: transparent url("https://webcore.unm.edu/v2/images/unm-transparent-white.png") no-repeat left center !important;
  background-size: auto 20px !important; box-shadow: none !important; border: 0 !important; margin: 0 !important; }

/* CARC masthead: custom UNM-branded lockup replacing the text banner */
#carc-masthead { background: var(--pg-bg); border-bottom: 3px solid #ba0c2f; padding: 16px 0 12px; }
#carc-masthead .carc-lockup { margin: 0; line-height: 0; }
#carc-masthead img { height: 56px; width: auto; max-width: 100%; }
.carc-lockup-night { display: none; }
html[data-theme="dark"] .carc-lockup-day { display: none; }
html[data-theme="dark"] .carc-lockup-night { display: inline; }
@media (prefers-color-scheme: dark) {
  html:not([data-theme="light"]) .carc-lockup-day { display: none; }
  html:not([data-theme="light"]) .carc-lockup-night { display: inline; }
}
@media (max-width: 600px) { #carc-masthead img { height: 42px; } }
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
/* card grid for `layout: cards` pages (research/featured-projects) */
.carc-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 1.25rem; margin: 1.5rem 0 2rem; }
.carc-card { display: flex; flex-direction: column; background: var(--pg-card); border: 1px solid var(--pg-border); border-radius: 10px; overflow: hidden; transition: box-shadow .15s ease, transform .15s ease; }
.carc-card:hover { box-shadow: 0 6px 18px rgba(0,0,0,.12); transform: translateY(-2px); }
.carc-card-media { display: block; background: var(--pg-strip); }
.carc-card-media img { display: block; width: 100%; height: 170px; object-fit: cover; }
.carc-card-body { display: flex; flex-direction: column; flex: 1; padding: .9rem 1rem 1rem; }
#carc-content .carc-card-title { font-size: 1.02rem; line-height: 1.3; margin: 0 0 .5rem; font-weight: 700; }
#carc-content .carc-card-title a { color: var(--pg-fg); text-decoration: none; }
#carc-content .carc-card-title a:hover { color: var(--pg-link); }
.carc-card-text { font-size: .9rem; line-height: 1.45; color: var(--pg-muted); display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden; }
#carc-content .carc-card-text p { margin: 0 0 .5rem; color: var(--pg-muted); }
#carc-content .carc-card-more { margin-top: auto; padding-top: .6rem; font-weight: 600; font-size: .9rem; text-decoration: none; }
@media (max-width: 480px) { .carc-cards { grid-template-columns: 1fr; } }
</style>"""

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
{gtm_head}
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
{gtm_body}
<a class="sr-only sr-only-focusable skip2content" href="#carc-content">Skip to main content</a>
<div id="page">
{navbar}
<div aria-label="Center for Advanced Research Computing" id="carc-masthead" role="banner"><div class="container"><a href="{rel_root}"><h1 class="carc-lockup"><img class="carc-lockup-day" src="{rel_root}assets/carc-lockup.png" alt="UNM Center for Advanced Research Computing"><img class="carc-lockup-night" src="{rel_root}assets/carc-lockup-dark.png" alt="" aria-hidden="true"></h1></a></div></div>
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
    items.append(f'<li><a class="carc-ext-btn" href="{rel_root}docs/">'
                 'User Documentation <span aria-hidden="true">↗</span></a></li>')
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
        root_html = ROOT_HTML_PAGES.get(rel.name)
        pdir = root_html if root_html else pretty_dir(rel)
        title = fm.get("title") or next(
            (l[2:].strip() for l in body.splitlines() if l.startswith("# ")),
            rel.stem.replace("-", " ").title())
        content = markdown.markdown(body, extensions=MD_EXTENSIONS)
        src_dir = "" if str(rel.parent) == "." else str(rel.parent)
        content = rewrite_md_links(content, src_dir, pdir)
        if fm.get("layout") == "cards":
            content = cards_html(content)
        depth = 0 if root_html else (len(pdir.rstrip("/").split("/")) if pdir else 0)
        rel_root = "../" * depth if depth else "./"
        page = TEMPLATE.format(
            gtm_head=GTM_HEAD,
            gtm_body=GTM_BODY,
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
        if root_html:
            # served via ErrorDocument, so it gets no sitemap entry
            (SITE / root_html).write_text(page, encoding="utf-8")
            continue
        if pdir == "":
            continue  # root index.md: homepage comes from web/, mirror serves index.md
        out = SITE / pdir / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
        urls.append(base + pdir)

    # homepage + assets. web/index.html is hand-authored against the GitHub
    # Pages origin; its canonical and self-links follow site_url at build time.
    home = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    (SITE / "index.html").write_text(home.replace("https://unm-carc.github.io/", base),
                                     encoding="utf-8")
    urls.insert(0, base)
    if (DOCS / "assets").exists():
        shutil.copytree(DOCS / "assets", SITE / "assets", dirs_exist_ok=True)

    # sitemap
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    # No <lastmod>: a build-time date changed on every run, which under the
    # Cascade sync meant one needless edit+publish of sitemap.xml per deploy.
    sm += [f"<url><loc>{u}</loc></url>" for u in urls]
    sm.append("</urlset>")
    (SITE / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")

    # llms indexes ship with the site
    for f in ("llms.txt", "llms-full.txt"):
        if (DOCS / f).exists():
            shutil.copy2(DOCS / f, SITE / f)

    print(f"cascade site: {len(urls)} pages (incl. homepage), sitemap, assets")


if __name__ == "__main__":
    main()
