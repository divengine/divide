#!/usr/bin/env python3
"""Copy a book's pages into divide's built-in help (src/divide/manual/books/<id>).

Each book of the help is a copy of a wiki or a documentation folder, written
once where it lives. src/divide/manual/books.json lists the books: where each
one comes from ("source", "path" inside it), its first page ("home") and its
table of contents ("contents": a wiki's _Sidebar.md or a list of pages).
Run it after the source changes:

    tools/sync_book.py divide path/to/divide.wiki
    tools/sync_book.py div path/to/div          # a checkout of the engine
    tools/sync_book.py divide path/to/divide-es.wiki --language es
    tools/sync_book.py --index                  # only the search index
    tools/sync_book.py --list

A book in another language is one more entry of books.json with the same
"id" and its "language" (and its "source"; the rest is the original's). Its
pages go to books/<id>.<language>, with the original's page names.

After copying, it builds the help's full-text search indexes
(src/divide/manual/search*.sqlite, see divide.manual.fulltext), one per language.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

MANUAL = Path(__file__).resolve().parent.parent / "src" / "divide" / "manual"
REGISTRY = MANUAL / "books.json"
sys.path.insert(0, str(MANUAL.parent.parent))  # divide from this checkout


def books() -> list[dict]:
    """The entries of books.json; a translation (an id's later entry) takes what it does
    not say from the original (its first entry), and is marked with "translation"."""
    out, originals = [], {}
    for entry in json.loads(REGISTRY.read_text(encoding="utf-8")):
        first = originals.setdefault(entry["id"], entry)
        out.append(entry if first is entry else {**first, **entry, "translation": True})
    return out


def folder(book: dict) -> str:
    """books/<id>, or books/<id>.<language> for a translation."""
    return f"{book['id']}.{book['language']}" if book.get("translation") else book["id"]


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
    target_dir = MANUAL / "books" / folder(book)
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
    parser.add_argument("--language", help="the book in this language (a translation's entry in books.json)")
    parser.add_argument("--list", action="store_true", help="list the books and their sources")
    parser.add_argument("--index", action="store_true", help="only build the search index")
    args = parser.parse_args()
    if args.index:
        return index()
    registry = books()
    if args.list or not args.book:
        for book in registry:
            print(f"{folder(book):<10} {book['source']}  ({book.get('path', '.')})")
        return 0
    same = [b for b in registry if b["id"] == args.book]
    book = next((b for b in same if b.get("language") == args.language), None) if args.language else (same or [None])[0]
    if book is None:
        print(f"no book {args.book!r}{' in ' + args.language if args.language else ''} in {REGISTRY}", file=sys.stderr)
        return 1
    if args.checkout is None:
        parser.error("the checkout of the book's source is required")
    status = sync(book, args.checkout)
    return status or index()


def index() -> int:
    from divide.manual import fulltext

    for lang, rows in fulltext.build_all().items():
        print(f"indexed {rows} sections in {fulltext.index_file(lang).name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
