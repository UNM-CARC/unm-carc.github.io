# Website update log

## 2026-09-04

* **Update**: Groundwork for publishing this site into UNM's Apache document root for [carc.unm.edu](https://carc.unm.edu), so the site keeps its `.edu` address while all editing moves to this repository and Cascade is retired. The build now emits an `.htaccess` of real 301 redirects (`scripts/gen_htaccess.py`) — something GitHub Pages cannot do — derived automatically from each page's OKF `sources[].resource` provenance, so migrating a page and recording its origin is all it takes to redirect its old URL. Legacy Cascade pages whose content never moved are deliberately left alone: their files stay in the document root and keep serving at their original addresses.

* **New**: A [Page not found](404.md) page, wired to the Apache `ErrorDocument` directive. The live site's `ErrorDocument` currently points at a file that does not exist, so 404s fall back to the stock Apache error.

* **Update**: CI now also runs on pull requests, so validation and a full trial build catch problems before they reach `main` rather than after.

## 2026-08-30

* **Update**: The homepage "Latest from CARC" cards now feature the newest announcements (new Director, departures & retirements, new NSF awards), and the "no vacancy? never —" and "full service, every orbit —" taglines are retired.

* **Update**: Restructured the [News](news/index.md) section: six new announcements are staged as placeholders pending final text from CARC administration — the new Director (Tyson Swetnam), recent departures and retirements (Patrick Bridges, Hussein Al-Azzawi, Jim Prewett), an In Memoriam for Cleve Moler by Matthew Fricke, two new NSF awards (IDSS MESA; research hardware, Ruskai), and a 2026 PSAAP COMPASS update. All stories from before August 2026 moved into an Archive with by-year headers.

* **Fix**: The homepage section navigation now uses exactly the interior pages' styling (same type, spacing, hover, and theme-aware strip colors) instead of the Bootstrap default it had been inheriting.

* **Fix**: Removed the department footer's X/Twitter and Facebook icons — those CARC accounts no longer exist; the live [UNM CARC YouTube channel](https://www.youtube.com/@UNMCARC) stands in their place. (The UNM global footer's university-wide social links remain.)

* **Update**: New site masthead. The text-only department banner is gone; in its place is the official UNM + Center for Advanced Research Computing lockup (cherry interlocking monogram, gray wordmark) on a clean band — colorway on light, silver-on-dark after dusk — with the UNM webcore bar kept above it in the spirit of the university standard (its hanging brand tab now renders as the compact white UNM wordmark inside the red bar, as other UNM centers do). Applied to the homepage and every interior page.

* **Fix**: Cadillac scene corrections from review: Lobo now has a full body and a cleaner angular profile (and his wave is visible over the door); Sparky sits *in* the car instead of floating above it; the side-view fin is solid with twin bullet taillights pointing rearward; the rear fins are now visible in the approaching view; and the driving-away view shows the quad taillights as two horizontal pairs, '59-style.

* **Update**: Overhauled the [CSE Certificate Program](education/cse/index.md) course pages. Every core course and approved elective was validated against the UNM Schedule of Classes for Fall 2026 (checked August 30, 2026) and now links directly to its live schedule entry; the [electives page](education/cse/electives.md) shows per-course offering status, notes renamed courses (ECE 517 "Machine Learning", CE 502, ME 500, MATH 505), and flags the CS/ECE/MATH graduate renumbering for Program Committee review. The Spring 2027 schedule publishes mid-October 2026 and the pages say so.

* **Fix**: Corrected a site-wide link-rewriting bug that resolved relative links against the rendered page directory instead of the source file's directory — the cause of the broken `/education/cse/requirements/electives/` URL (and several other cross-section links). A full-site sweep now reports zero broken internal links.

* **Update**: Added ready-made page templates (`templates/news-article.md`, `templates/content-page.md`) and an admin guide (`SITE_INSTRUCTIONS.md`) so staff can publish news articles and edit any page entirely from the GitHub web interface — no Cascade CMS or local tooling required. The deploy pipeline now regenerates the llms.txt machine indexes and sitemap dates automatically at build time.

* **Fix**: The hero's text panel now keeps identical size and position in the day and night themes (the night layout is canonical); the daytime cream backing is painted without affecting layout. Also replaced a Material icon code on the workshops page that rendered as literal text.

* **Update**: The day/night toggle is now a bare ☾/☀ glyph in the navigation — no outline or text — so it no longer resembles the User Documentation and Help Desk buttons.

## 2026-08-29

* **Update**: Deepened the hero landscape in both themes: snow-capped peaks inspired by the Sangre de Cristo Mountains now rise behind the eastern mesas (rosy brown with white caps by day, moonlit blue-gray by night), with a mid-distance ridge, a horizon haze band, and a foreground of chamisa bushes and yuccas scattered along old Route 66 — all theme-aware.

* **Update**: The homepage hero now follows the site-wide day/night theme (same saved preference and a ☾/☀ toggle in the navigation). By day it becomes a monsoon scene over the high desert: turquoise sky, tan and brown mesas, a googie ray-sun risen above the horizon, towering cumulonimbus drifting slowly with rain curtains and falling streaks, and a hawk riding the thermals — while the neon sign goes unlit (the OPEN lozenge stays on) and the Cadillacs keep cruising. Night remains the neon Route 66 scene. Hero CTAs now open in new tabs.

* **Update**: Responsive shakedown across full-screen monitor (2560px), desktop (1920px), laptop (1440px), tablet (768px), and mobile (375px): fixed the department footer's fixed-width table that forced horizontal overflow on small screens; capped the hero overlay width on ultra-wide monitors; added three-tier hero framing (phones center on the neon sign, tablets show sign + road + cars, desktops get the full diorama); content tables scroll within the page. Verified zero horizontal overflow at every size and that the hero animations hold up.

* **Update**: Remodeled the hero's cars on the 1959 Cadillac — blade tailfins with twin bullet taillights in chrome pods, quad headlights, eggcrate grille, dagmar bumper, full-length chrome spear, wraparound windshield, long rear overhang. Lobo is now an angular UNM-logo-style wolf and Sparky a 1950s Yoshiya-style tin robot with a glowing chest spark window. The arriving car now stops fully in frame before waving, and the road's centerline dashes shorten with distance for perspective.

* **Update**: Interior pages gained day and night themes (system preference plus a ☾/☀ toggle in the section navigation, remembered per browser); User Documentation and Help Desk render as pill buttons that open in new tabs (↗). The homepage hero's road centerline is now static, replaced by an animated scene: Lobo drives a turquoise finned Cadillac convertible with Sparky the android riding shotgun away toward the mesa; a second car arrives, swings broadside, its occupants wave, and it sinks off-screen before the loop repeats.

* **Update**: All interior pages now render in the UNM Cascade webcore standard — the exact carc.unm.edu header, section navigation, breadcrumbs, department + UNM global footer, and Quick Links panel on every page, with a plain content column replacing the Zensical/Material theme (`scripts/build_cascade_site.py`). The OKF bundle, llms indexes, Markdown mirrors, and robots.txt are unchanged.

* **Update**: Replaced the Zensical-themed homepage with a hand-authored standard-HTML page (`web/index.html`, installed by `scripts/build_home.py`): the UNM Cascade webcore header, Quick Links panel, and footer are retained verbatim, and the hero is a Googie/mid-century D3 scene — neon CARC motel sign with chaser bulbs, atomic orbits, starbursts, and Route 66 — in UNM Cherry/Turquoise/Silver. Interior pages remain Zensical; the machine-readable index remains at `/index.md`.

* **Initialization**: Created this rebuild of [carc.unm.edu](https://carc.unm.edu) with [Zensical](https://zensical.org), structured as an Open Knowledge Format (OKF v0.2) bundle with the same agent surface as the [user documentation](https://unm-carc.github.io/docs/): llms.txt, per-page Markdown mirrors, and an origin-wide robots.txt.
* **Migration**: Migrated core pages from carc.unm.edu — About (mission, strategic plan, history, IAB), Research (featured projects, publications, services, grant resources), Education (workshops, CSE certificate program), Contact (personnel, visitors) — and the ten most recent news stories, with provenance frontmatter. Content images currently hotlink to carc.unm.edu and must be localized before the old site is retired.
