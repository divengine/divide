#!/usr/bin/env python3
"""Copy the wiki's pages into divide's built-in help (src/divide/manual/pages).

The wiki is the manual; the help window reads this copy. Run it after
changing the wiki:

    tools/sync_manual.py path/to/divide.wiki
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PAGES = Path(__file__).resolve().parent.parent / "src" / "divide" / "manual" / "pages"
SKIP = {"_Footer.md"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wiki", type=Path, help="a checkout of github.com/divengine/divide.wiki")
    args = parser.parse_args()
    pages = sorted(p for p in args.wiki.glob("*.md") if p.name not in SKIP)
    if not pages:
        print(f"no pages in {args.wiki}", file=sys.stderr)
        return 1
    PAGES.mkdir(parents=True, exist_ok=True)
    wanted = {p.name for p in pages}
    for old in PAGES.glob("*.md"):
        if old.name not in wanted:
            old.unlink()
            print("removed", old.name)
    for page in pages:
        target = PAGES / page.name
        if not target.exists() or target.read_bytes() != page.read_bytes():
            shutil.copyfile(page, target)
            print("copied", page.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
