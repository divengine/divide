#!/usr/bin/env python3
"""Copy a book's pages into divide's built-in help (src/divide/manual/books/<id>).

Each book of the help is a copy of a wiki or a documentation folder, written
once where it lives. src/divide/manual/books.json lists the books: where each
one comes from ("source", "path" inside it), its first page ("home") and its
table of contents ("contents": a wiki's _Sidebar.md or a list of pages).
Run it after the source changes:

    tools/sync_book.py divide path/to/divide.wiki
    tools/sync_book.py div path/to/div          # a checkout of the engine
    tools/sync_book.py --list
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

MANUAL = Path(__file__).resolve().parent.parent / "src" / "divide" / "manual"
REGISTRY = MANUAL / "books.json"


def books() -> list[dict]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def sync(book: dict, checkout: Path) -> int:
    root = checkout / book.get("path", ".")
    skip = set(book.get("skip", []))
    contents = book.get("contents")
    pages = sorted(p for p in root.glob("*.md") if p.name not in skip)
    if contents and not contents.endswith(".md") and (root / contents).is_file():
        pages.append(root / contents)
    if not pages:
        print(f"no pages in {root}", file=sys.stderr)
        return 1
    target_dir = MANUAL / "books" / book["id"]
    target_dir.mkdir(parents=True, exist_ok=True)
    wanted = {p.name for p in pages}
    for old in sorted(target_dir.iterdir()):
        if old.is_file() and old.name not in wanted:
            old.unlink()
            print("removed", old.name)
    for page in pages:
        target = target_dir / page.name
        if not target.exists() or target.read_bytes() != page.read_bytes():
            shutil.copyfile(page, target)
            print("copied", page.name)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("book", nargs="?", help="the book's id in books.json")
    parser.add_argument("checkout", nargs="?", type=Path, help="a checkout of the book's source")
    parser.add_argument("--list", action="store_true", help="list the books and their sources")
    args = parser.parse_args()
    registry = books()
    if args.list or not args.book:
        for book in registry:
            print(f"{book['id']:<10} {book['source']}  ({book.get('path', '.')})")
        return 0
    book = next((b for b in registry if b["id"] == args.book), None)
    if book is None:
        print(f"no book {args.book!r} in {REGISTRY}", file=sys.stderr)
        return 1
    if args.checkout is None:
        parser.error("the checkout of the book's source is required")
    return sync(book, args.checkout)


if __name__ == "__main__":
    sys.exit(main())
