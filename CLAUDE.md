# unm-carc.github.io

Follow the editing conventions of the UNM-CARC docs repository: https://github.com/UNM-CARC/docs/blob/main/AGENTS.md
This repo is the org ROOT site (must stay named unm-carc.github.io). Every content page needs OKF v0.2 frontmatter with a non-empty type; section index.md files carry no frontmatter; log.md is the dated change log. Validate with scripts/okf_validate.py, regenerate scripts/gen_llms_txt.py after content changes, and run scripts/postbuild_agent_surface.py after builds.
