# Website update log

## 2026-08-29

* **Update**: All interior pages now render in the UNM Cascade webcore standard — the exact carc.unm.edu header, section navigation, breadcrumbs, department + UNM global footer, and Quick Links panel on every page, with a plain content column replacing the Zensical/Material theme (`scripts/build_cascade_site.py`). The OKF bundle, llms indexes, Markdown mirrors, and robots.txt are unchanged.

* **Update**: Replaced the Zensical-themed homepage with a hand-authored standard-HTML page (`web/index.html`, installed by `scripts/build_home.py`): the UNM Cascade webcore header, Quick Links panel, and footer are retained verbatim, and the hero is a Googie/mid-century D3 scene — neon CARC motel sign with chaser bulbs, atomic orbits, starbursts, and Route 66 — in UNM Cherry/Turquoise/Silver. Interior pages remain Zensical; the machine-readable index remains at `/index.md`.

* **Initialization**: Created this rebuild of [carc.unm.edu](https://carc.unm.edu) with [Zensical](https://zensical.org), structured as an Open Knowledge Format (OKF v0.2) bundle with the same agent surface as the [user documentation](https://unm-carc.github.io/docs/): llms.txt, per-page Markdown mirrors, and an origin-wide robots.txt.
* **Migration**: Migrated core pages from carc.unm.edu — About (mission, strategic plan, history, IAB), Research (featured projects, publications, services, grant resources), Education (workshops, CSE certificate program), Contact (personnel, visitors) — and the ten most recent news stories, with provenance frontmatter. Content images currently hotlink to carc.unm.edu and must be localized before the old site is retired.
