# unm-carc.github.io

Follow the editing conventions of the UNM-CARC docs repository: https://github.com/UNM-CARC/docs/blob/main/AGENTS.md

This repo is the source of https://carc.unm.edu/ and, as the org ROOT Pages site (it must stay named unm-carc.github.io), its staging mirror at https://unm-carc.github.io/. Every content page needs OKF v0.2 frontmatter with a non-empty type; section index.md files carry no frontmatter; log.md is the dated change log.

Build order: scripts/okf_validate.py docs, scripts/check_legacy_links.py docs, scripts/gen_llms_txt.py, scripts/build_cascade_site.py, scripts/postbuild_agent_surface.py site, scripts/gen_htaccess.py site. Zensical does not render this site; zensical.toml only supplies site_url (CARC_SITE_URL overrides it).

Publishing: CI pushes the built site into Cascade CMS through scripts/cascade_sync.py and Cascade publishes it by SFTP; never edit in Cascade. Images go in docs/assets/ and are referenced as /assets/<name> — never hotlink carc.unm.edu. A page's sources[].resource carc.unm.edu URL becomes a 301 to that page automatically. `layout: cards` in frontmatter renders a #### [Title](url) + image + summary list as a card grid.
