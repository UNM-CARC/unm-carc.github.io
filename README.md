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

- Content migrated from carc.unm.edu with provenance frontmatter. All images
  and documents are localized into `docs/assets/` — nothing hotlinks the old
  host any more, and `scripts/check_legacy_links.py` fails the build if a page
  reintroduces one. The mapping from legacy URL to local filename lives in
  `migration/assets.yml`.
- Legacy Cascade URLs that were superseded get real Apache 301s, generated into
  `.htaccess` by `scripts/gen_htaccess.py` from each page's OKF
  `sources[].resource` provenance. Legacy pages whose content never moved get no
  redirect: their files stay in the document root and keep serving.
- The repository must be named `unm-carc.github.io` to serve at the org
  root. GitHub Pages (`unm-carc.github.io`) is the staging mirror; the
  public site is `carc.unm.edu`, published by the `publish-cascade` job in
  `.github/workflows/docs.yml`: `scripts/cascade_sync.py` pushes the built
  tree into Cascade CMS through its REST API and Cascade publishes it to
  the UNM web host by SFTP. Cascade is a conduit, not an editor — **anything
  edited in Cascade is overwritten by the next sync.** The tool owns only
  the assets recorded in its manifest and never touches the legacy folders.
- The user documentation (`UNM-CARC/docs`) is published the same way into
  `/docs/` on the same host, so it shares this site's root `robots.txt` —
  a `robots.txt` at `/docs/robots.txt` is ignored by crawlers.
- Editing conventions match the docs repo — see its
  [AGENTS.md](https://github.com/UNM-CARC/docs/blob/main/AGENTS.md).
