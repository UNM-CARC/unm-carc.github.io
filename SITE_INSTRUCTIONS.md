# Managing the CARC website

How to add news articles, edit pages, and keep this site current — **no
Cascade CMS, no local software required**. Everything on the site is a plain
Markdown text file in the `docs/` folder of this repository. When a change is
committed to the `main` branch, GitHub Actions checks it, rebuilds every page
in the UNM Cascade standard (header, footer, navigation), and publishes it
to <https://carc.unm.edu/> — live in a few minutes. (A staging copy also
lands at <https://unm-carc.github.io/>.)

**Do not edit the site in Cascade CMS any more.** The publishing pipeline
pushes every page through Cascade automatically, and anything changed there
by hand is overwritten on the next publish. This repository is the only place
to edit.

You can do all of this in the GitHub web interface in your browser. The
optional [local preview](#working-locally-optional) is for bigger changes.

## The one-minute mental model

| You edit… | It becomes… |
| --------- | ----------- |
| `docs/news/2026-new-cluster.md` | the page `/news/2026-new-cluster/` |
| `docs/about/mission.md` | the page `/about/mission/` |
| `docs/news/index.md` | the News section landing page `/news/` |

The build wraps your Markdown in the standard UNM header, section navigation,
breadcrumbs, and footer automatically — you only ever write the content
column. Filenames are lowercase-with-hyphens (`kebab-case.md`).

## Publish a news article

1. Open [`templates/news-article.md`](templates/news-article.md), click the
   **copy raw file** button (two overlapping squares), and copy its contents.
2. Go to the [`docs/news/`](docs/news/) folder → **Add file → Create new
   file**. Name it with a short slug, e.g. `2026-fall-workshops.md`.
3. Paste the template and replace every UPPERCASE placeholder — headline,
   summary, your NetID, the date, the body. The template's comment block
   explains each field and can be deleted (or left in — it won't display).
4. Open [`docs/news/index.md`](docs/news/index.md) (pencil icon to edit) and
   add your article at the **top** of the list, matching the existing lines:

   ```markdown
   * [Your headline](2026-fall-workshops.md) - One-line summary.
   ```

5. Commit both changes (green **Commit changes** button; a short message like
   "news: fall workshops announcement" is perfect).
6. Watch the **Actions** tab if you like — when the run goes green, the
   article is live.

## Edit an existing page

1. Browse to the file under [`docs/`](docs/) (see the mental model above for
   which file is which page) and click the **pencil** icon.
2. Change the text. Leave the block between the `---` lines at the top (the
   *frontmatter*) intact except for fields you mean to change — update
   `description` if the page's summary changed.
3. Commit. Done.

Routine examples: staff changes go in `docs/contact/personnel.md`; workshop
details in `docs/education/workshops.md`; services in `docs/research/`.

## Add a page to any other section

Same as a news article, but start from
[`templates/content-page.md`](templates/content-page.md), place the file in
the section's folder (`docs/about/`, `docs/research/`, `docs/education/`,
`docs/contact/`), and link it from that section's `index.md`. Creating a
brand-new top-level section is the one thing that needs a maintainer: the
section list lives in `SECTIONS` at the top of
`scripts/build_cascade_site.py`.

## Images

1. Upload the image to [`docs/assets/`](docs/assets/) (**Add file → Upload
   files**). Use a descriptive kebab-case name, e.g. `cam-2026-poster.jpg`.
2. Reference it from any page by absolute path, with alt text for
   accessibility:

   ```markdown
   ![Students at the CAM 2026 poster session](/assets/cam-2026-poster.jpg)
   ```

Keep images under ~1 MB (resize before uploading). Every image on the site is
already stored this way — **never paste an image URL from carc.unm.edu into a
page.** Those addresses only work by accident of the old server still running,
and the build check rejects them.

## The frontmatter, briefly

Every page starts with a small YAML block. It's what makes the site readable
by AI assistants and search engines (the site is an
[Open Knowledge Format v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
bundle), and CI rejects pages that omit it.

```yaml
---
title: "Page title"                      # required
description: "One-sentence summary."     # required in practice — feeds search/AI
type: News                               # required: News | Reference | Guide | Policy
tags:
  - News
generated:
  by: "human:yournetid"                  # who wrote it: human:<netid> for people
  at: "2026-09-15T00:00:00Z"             # when
---
```

Two special rules:

* **Section `index.md` files carry no frontmatter** — just the heading and
  the list of pages. (The root `docs/index.md` is the machine-readable site
  index; edit it only if you add or remove pages.)
* If you **review and confirm** a page's accuracy, add a `verified` block —
  it upgrades the page's published trust tier from "unverified" to
  "human-reviewed":

  ```yaml
  verified:
    by: "human:yournetid"
    at: "2026-09-15T00:00:00Z"
  ```

## Formatting that works (and doesn't)

Pages are standard Markdown plus a few extras:

* Headings `##`, bold, italics, bullet and numbered lists, tables, fenced
  code blocks.
* Internal links point at the `.md` file relative to the current one
  (`[mission](../about/mission.md)`) — the build rewrites them to real URLs.
* External links: append `{target=_blank}` to open in a new tab.
* Callout boxes: `!!! note "Title"` / `tip` / `warning` / `danger`, with the
  box text indented four spaces on the next lines.
* Buttons: `[Label](URL){ .md-button .md-button--primary target=_blank }`.
* Bylines on news articles: `<p class="carc-byline">By Name · Date</p>`.

**Does not work on this site** (these are /docs/-site features): Material
icon codes like `:material-calendar-month:`, content tabs, and keyboard-key
markup. Use plain Unicode symbols (📅 ✉ →) instead of icon codes.

## The changelog

For anything beyond a typo fix, add a line to [`docs/log.md`](docs/log.md)
under a `## YYYY-MM-DD` heading (create today's heading if it doesn't exist,
newest at the top):

```markdown
## 2026-09-15

* **News**: Announced the fall workshop series.
```

## If the build fails

A red ✗ in the **Actions** tab means the check caught something — the live
site is untouched until it's fixed. Click the failed run → the failed step
prints the file and problem, almost always one of: missing frontmatter
(deleted a `---` line?), missing `type:`, frontmatter accidentally added
to a section `index.md`, an image URL pasted from carc.unm.edu, or a
`/assets/...` path that doesn't match an uploaded file. Fix the file, commit
again, and the pipeline reruns.

## Working locally (optional)

For previewing bigger changes before they publish:

```bash
git clone https://github.com/UNM-CARC/unm-carc.github.io.git
cd unm-carc.github.io
pip install pyyaml markdown
python3 scripts/okf_validate.py docs        # the same check CI runs
python3 scripts/build_cascade_site.py       # render the site
python3 scripts/postbuild_agent_surface.py  # robots.txt + agent surface
python3 -m http.server 8080 -d site         # browse at http://localhost:8080
```

Edit, rebuild, refresh. Commit and push when happy — CI still runs the same
checks.

## What not to touch

* `web/index.html` — the hand-authored homepage with the animated hero.
* `scripts/` and `.github/workflows/` — the build pipeline.
* The `docs/llms.txt` / `docs/llms-full.txt` indexes — regenerated
  automatically at deploy time.
* The site chrome (UNM header, footer, Quick Links) — it's generated from
  the official UNM webcore standard inside `scripts/build_cascade_site.py`.
* Anything in Cascade CMS — see above; it is no longer an editing surface.

Questions or something beyond this guide (new sections, homepage changes,
design work): open an issue on this repository or ask a maintainer. The
companion user documentation at
[carc.unm.edu/docs](https://carc.unm.edu/docs/) lives in the
separate [UNM-CARC/docs](https://github.com/UNM-CARC/docs) repository with
its own contributor guide.
