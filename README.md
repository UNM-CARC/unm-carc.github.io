# unm-carc.github.io

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
pip install zensical pyyaml
zensical serve                              # localhost:8000
zensical build --clean
python3 scripts/okf_validate.py docs        # OKF conformance (CI-enforced)
python3 scripts/gen_llms_txt.py             # regenerate llms.txt indexes
python3 scripts/postbuild_agent_surface.py  # md mirror + meta + robots.txt
```

## Notes

- Content migrated from carc.unm.edu with provenance frontmatter; news
  images currently **hotlink to carc.unm.edu** and must be localized into
  `docs/assets/` before the old site is retired.
- The repository must be named `unm-carc.github.io` to serve at the org
  root. Deployment is via GitHub Actions (`.github/workflows/docs.yml`);
  set Pages source to "GitHub Actions".
- Editing conventions match the docs repo — see its
  [AGENTS.md](https://github.com/UNM-CARC/docs/blob/main/AGENTS.md).
