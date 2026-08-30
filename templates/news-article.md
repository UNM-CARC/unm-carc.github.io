---
title: "HEADLINE OF THE ARTICLE"
description: "ONE-SENTENCE SUMMARY — shown in the news index, search results, and AI answers."
type: News
tags:
  - News
generated:
  by: "human:YOURNETID"
  at: "YYYY-MM-DDT00:00:00Z"
---

<!--
HOW TO USE THIS TEMPLATE (delete this comment block when done — but nothing
breaks if you forget: it stays invisible on the published page)

1. Copy this file into  docs/news/  and rename it to a short kebab-case slug,
   e.g.  2026-new-cluster.md   →  published at  /news/2026-new-cluster/
2. Fill in every UPPERCASE placeholder, above and below. Keep the quotes.
   "human:YOURNETID" marks you as the author, e.g. "human:mrosales".
3. Make the # heading identical to the frontmatter title.
4. Add one line for the article at the TOP of the list in  docs/news/index.md :
     * [Headline](your-slug.md) - One-line summary.
5. (Optional) Add a dated entry to  docs/log.md .
6. Commit. GitHub Actions validates and publishes automatically (~2 min).

Full walkthrough: SITE_INSTRUCTIONS.md at the repository root.
-->

# HEADLINE OF THE ARTICLE

<p class="carc-byline">By AUTHOR NAME · MONTH DD, YYYY</p>

Opening paragraph: who, what, when, where — the paragraph a reader (or an AI
assistant) sees first.

Second paragraph with more detail. Formatting that works on this site:

* **Bold**, *italics*, and [internal links to other pages](../about/mission.md)
  written as relative paths to the `.md` file — the build turns them into
  proper URLs.
* [External links](https://carc.unm.edu){target=_blank} get
  `{target=_blank}` so they open in a new tab.
* Images live in `docs/assets/` and are referenced by absolute path:

![DESCRIBE THE IMAGE FOR SCREEN READERS](/assets/YOUR-IMAGE.jpg)

!!! note "Optional callout box"

    Use `!!! note`, `!!! tip`, `!!! warning`, or `!!! danger` plus an
    indented paragraph for a highlighted box. Delete this if not needed.

Closing paragraph. A call-to-action button looks like this:

[📅 Register here](https://EXAMPLE.COM/FORM){ .md-button .md-button--primary target=_blank }

<!-- Do NOT use :material-*: icon codes — they only render on the /docs/
site. Plain Unicode symbols (📅 ✉ →) work everywhere. -->
