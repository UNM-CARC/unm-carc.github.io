#!/usr/bin/env python3
"""Install the hand-authored homepage over the Zensical-generated one.

The CARC homepage is standard HTML (web/index.html) — UNM Cascade webcore
header/footer retained verbatim, plus the Googie/D3 hero — rather than a
Zensical-themed page. Interior pages remain Zensical. Run AFTER
`zensical build` and BEFORE postbuild_agent_surface.py (the homepage carries
its own okf:* meta and rel=alternate, so postbuild leaves it alone; the
markdown mirror still serves docs/index.md at /index.md for agents).

Usage: python3 scripts/build_home.py [site_dir]
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    site = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "site"
    src = ROOT / "web" / "index.html"
    if not site.is_dir():
        print(f"error: {site} not found — run `zensical build` first", file=sys.stderr)
        sys.exit(2)
    shutil.copy2(src, site / "index.html")
    print(f"homepage installed: web/index.html -> {site / 'index.html'}")


if __name__ == "__main__":
    main()
