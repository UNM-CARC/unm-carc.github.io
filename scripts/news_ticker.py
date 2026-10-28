"""Build homepage ticker entries from current News links and downtime metadata."""
from datetime import datetime
import html
import json
from pathlib import Path
import re

import yaml


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    return yaml.safe_load(match[1]) if match else {}


def downtime_entries(docs):
    entries = []
    seen = set()
    for notice in frontmatter(docs / "downtime-notices.md").get("notices", []):
        anchor, title, status = (notice.get(key) for key in ("anchor", "title", "status"))
        if not title or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", anchor or ""):
            raise ValueError("Downtime notices need a title and a stable lowercase anchor")
        if anchor in seen or status not in ("scheduled", "active", "resolved"):
            raise ValueError(f"Duplicate anchor or invalid downtime status: {anchor}")
        if f'id="{anchor}"' not in (docs / "downtime-notices.md").read_text():
            raise ValueError(f"Missing downtime body anchor: {anchor}")
        seen.add(anchor)
        item = {"title": title, "url": f"downtime-notices/#{anchor}", "status": status}
        for key in ("start", "end"):
            value = notice.get(key)
            if value:
                stamp = datetime.fromisoformat(str(value))
                if stamp.tzinfo is None:
                    raise ValueError(f"{anchor}: {key} must include a timezone offset")
                item[key] = stamp.isoformat()
        if status == "scheduled" and not all(key in item for key in ("start", "end")):
            raise ValueError(f"{anchor}: scheduled notices need start and end")
        if "start" in item and "end" in item and datetime.fromisoformat(item["end"]) <= datetime.fromisoformat(item["start"]):
            raise ValueError(f"{anchor}: end must be after start")
        entries.append(item)
    return entries


def ticker_html(docs):
    # Only the curated current stories, never the historical archive.
    current = (docs / "news/index.md").read_text().split("<!-- archive:start -->")[0]
    news = []
    for target in re.findall(r"^\* \[[^\]]+\]\(([^)]+\.md)\)", current, re.M):
        path = docs / "news" / target
        metadata = frontmatter(path)
        if metadata.get("type") != "News":
            continue
        news.append({"title": metadata["title"], "url": "news/" + target.removesuffix(".md") + "/",
                     "date": str(metadata.get("date", ""))})
    news.sort(key=lambda item: item["date"], reverse=True)
    news = news[:6]
    data = json.dumps({"news": news, "notices": downtime_entries(docs)}, ensure_ascii=False).replace("<", "\\u003c")
    links = "".join('<a class="gg-ticker-item" href="' + html.escape(item["url"], quote=True)
                    + '"><span class="gg-ticker-kind">NEWS</span> ' + html.escape(item["title"])
                    + '<span class="gg-ticker-star" aria-hidden="true">✦</span></a>' for item in news)
    return ('<aside class="gg-ticker" aria-label="CARC news and downtime notices">'
            '<div class="gg-ticker-window" tabindex="0" aria-label="Headlines; scroll to browse when paused">'
            '<div class="gg-ticker-track"><div class="gg-ticker-group">' + links + '</div></div></div>'
            '<a class="gg-ticker-all" href="news/">All news</a></aside>'
            '<script type="application/json" id="gg-ticker-data">' + data + '</script>')
