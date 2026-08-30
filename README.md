# unm-carc.github.io

> **Adding a news article or editing a page?** See
> **[SITE_INSTRUCTIONS.md](SITE_INSTRUCTIONS.md)** — the admin guide for
> updating this site entirely from the GitHub web interface — and start from
> the ready-made page templates in [`templates/`](templates/).

The public website of the [UNM Center for Advanced Research Computing](https://unm-carc.github.io/)
— a rebuild of [carc.unm.edu](https://carc.unm.edu) built with
[Zensical](https://zensical.org) and structured as an
[Open Knowledge Format (OKF) v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
knowledge bundle, sharing its design system and agent surface with the
[user documentation](https://github.com/UNM-CARC/docs) served at
[/docs/](https://unm-carc.github.io/docs/).

Because this is the **organization root site**, it owns the origin-wide
`robots.txt` (which advertises the llms.txt indexes and sitemaps of both this
site and /docs/), and a future custom domain set on this repository will
serve every UNM-CARC project site under it (e.g. `carc.unm.edu/docs/`).

## Quick start

```bash
pip install pyyaml markdown
python3 scripts/build_cascade_site.py       # render all pages (UNM Cascade standard)
python3 scripts/postbuild_agent_surface.py  # md mirror + meta + robots.txt
python3 -m http.server 8080 -d site         # preview at localhost:8080
python3 scripts/okf_validate.py docs        # OKF conformance (CI-enforced)
python3 scripts/gen_llms_txt.py             # regenerate llms.txt indexes
```

## Rendering: UNM Cascade standard

Every page uses the UNM Cascade webcore standard — the exact header, section
navigation, breadcrumbs, footer, and Quick Links panel from carc.unm.edu
(webcore.unm.edu assets) around a plain Bootstrap content column. Markdown in
`docs/` (the OKF bundle) is rendered by `scripts/build_cascade_site.py`; the
homepage is hand-authored standard HTML (`web/index.html`) with the Googie/D3
hero. Zensical is no longer used to render this site (`zensical.toml` remains
only as the `site_url` config source). The machine-readable OKF index stays
at `/index.md`.

## Notes

- Content migrated from carc.unm.edu with provenance frontmatter; news
  images currently **hotlink to carc.unm.edu** and must be localized into
  `docs/assets/` before the old site is retired.
- The repository must be named `unm-carc.github.io` to serve at the org
  root. Deployment is via GitHub Actions (`.github/workflows/docs.yml`);
  set Pages source to "GitHub Actions".
- Editing conventions match the docs repo — see its
  [AGENTS.md](https://github.com/UNM-CARC/docs/blob/main/AGENTS.md).
