"""Full-text search of the help books, ranked: SQLite's FTS5.

Every section of every page (the page's opening, then each ``##`` / ``###``
heading with the text below it) is a row of an FTS5 table: the page title,
the heading and the text, plus where it leads (``book:Page#anchor``). A
query keeps the sections that have all the words typed (the last one as a
prefix, as you type it), and ranks them with BM25, a match in a title worth
more than one in a heading, which is worth more than one in the text. Words
are stemmed (Porter): ``configure`` finds "configuring" and "configured".
FTS5 also cuts the snippet that shows each match in its sentence.

The index is built by ``tools/sync_book.py`` when it copies a book, and is
shipped beside the books (``manual/search.sqlite``). It records a
fingerprint of the pages it was built from: when the pages differ (a book
copied by hand, a checkout in the middle of a change) the index is built
again, in memory, on the first search. It takes a fraction of a second.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from divide import manual

INDEX_FILE = manual.HERE / "search.sqlite"
VERSION = "1"  # of the index's layout: a new one rebuilds the index
TOKENIZER = "porter unicode61 remove_diacritics 2"
WEIGHTS = (8.0, 4.0, 1.0)  # title, heading, text (BM25 column weights)
MARK_START, MARK_END = "\x01", "\x02"  # around the words found, in the snippet
SNIPPET_WORDS = 14
MAX_RESULTS = 200


@dataclass(frozen=True)
class Hit:
    target: str  # book:Page or book:Page#anchor
    book: str
    title: str  # the page's
    heading: str  # the section's ("" for the page's opening)
    snippet: str  # with MARK_START / MARK_END around the words found
    rank: float  # lower is better (BM25)

    @property
    def label(self) -> str:
        return f"{self.heading} · {self.title}" if self.heading else self.title


# ----------------------------------------------------------------- sections
def _text(line: str) -> str:
    """A line of Markdown as the words it shows."""
    line = re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", line)  # list marks
    line = line.replace("|", " ")  # table cells
    line = re.sub(r"^\s*>\s?(\[!\w+\])?", "", line)  # quotes, alerts
    return manual._plain(line).strip()


def sections(name: str) -> list[tuple[str, str, str]]:
    """``(heading, anchor, text)`` of a page: its opening (no heading), then each
    ``#``-``###`` section. Code blocks count as text: their names are searched for."""
    out: list[tuple[str, str, str]] = []
    heading, lines = "", []
    in_code = False
    for line in (manual.source(name) or "").splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        m = None if in_code else re.match(r"^(#{1,3}) (.+)$", line)
        if m and len(m.group(1)) == 1:
            continue  # the page's title: indexed as the title
        if m:
            out.append((heading, manual.slug(heading) if heading else "", " ".join(lines)))
            heading, lines = manual._plain(m.group(2)), []
        elif (shown := line.strip() if in_code else _text(line)) and not re.fullmatch(r"[-:\s|]+", line):
            lines.append(shown)
    out.append((heading, manual.slug(heading) if heading else "", " ".join(lines)))
    return [s for s in out if s[0] or s[2]]


def fingerprint() -> str:
    """Of the books' pages and the index's layout: an index built from other pages is stale."""
    digest = hashlib.sha1(VERSION.encode())
    for book in manual.books():
        for path in sorted(book.dir.glob("*.md")):
            digest.update(f"{book.id}/{path.name}\0".encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


# -------------------------------------------------------------------- index
def _create(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    db.execute(
        "CREATE VIRTUAL TABLE help USING fts5("
        "title, heading, body, book UNINDEXED, page UNINDEXED, anchor UNINDEXED, "
        f"tokenize = '{TOKENIZER}')"
    )


def fill(db: sqlite3.Connection) -> int:
    """Index every book into ``db`` (empty, made by ``_create``). Returns the rows."""
    rows = 0
    for book in manual.books():
        for name in manual.page_names(book.id):
            title = manual.title_of(name)
            page = manual.split(name)[1]
            for heading, anchor, body in sections(name):
                db.execute("INSERT INTO help VALUES (?, ?, ?, ?, ?, ?)", (title, heading, body, book.id, page, anchor))
                rows += 1
    db.execute("INSERT INTO meta VALUES ('fingerprint', ?)", (fingerprint(),))
    db.execute("INSERT INTO help(help) VALUES ('optimize')")
    db.commit()
    return rows


def build(path: Path = INDEX_FILE) -> int:
    """Write the index file (``tools/sync_book.py`` calls it). Returns the rows."""
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    try:
        _create(db)
        rows = fill(db)
        db.execute("VACUUM")
    finally:
        db.close()
    tmp.replace(path)
    return rows


@lru_cache(maxsize=1)
def _connection(stamp: str) -> sqlite3.Connection:
    """The shipped index when it was built from these pages, else one built in memory."""
    if INDEX_FILE.is_file():
        try:
            db = sqlite3.connect(f"file:{INDEX_FILE}?mode=ro", uri=True, check_same_thread=False)
            found = db.execute("SELECT value FROM meta WHERE key = 'fingerprint'").fetchone()
            if found and found[0] == stamp:
                return db
            db.close()
        except sqlite3.Error:
            pass
    db = sqlite3.connect(":memory:", check_same_thread=False)
    _create(db)
    fill(db)
    return db


def connection() -> sqlite3.Connection:
    return _connection(fingerprint())


# -------------------------------------------------------------------- query
def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def fts_query(text: str, *, any_word: bool = False) -> str | None:
    """The FTS5 query for what was typed: every word (or any, ``any_word``), the last
    one a prefix; quoted, so FTS5's own operators are plain words."""
    found = words(text)
    if not found:
        return None
    terms = [f'"{w}"' for w in found[:-1]] + [f'"{found[-1]}"*']
    return (" OR " if any_word else " ").join(terms)


def search(text: str, limit: int = MAX_RESULTS) -> list[Hit]:
    """The sections that match ``text``, best first. All the words if any section has
    them all, else any of them."""
    db = connection()
    sql = (
        "SELECT book, page, anchor, title, heading, "
        f"snippet(help, 2, '{MARK_START}', '{MARK_END}', '...', {SNIPPET_WORDS}), "
        f"bm25(help, {', '.join(map(str, WEIGHTS))}) AS rank "
        "FROM help WHERE help MATCH ? ORDER BY rank LIMIT ?"
    )
    for any_word in (False, True):
        query = fts_query(text, any_word=any_word)
        if query is None:
            return []
        try:
            rows = db.execute(sql, (query, limit)).fetchall()
        except sqlite3.Error:
            return []
        if rows:
            break
    hits = []
    for book, page, anchor, title, heading, snippet, rank in rows:
        target = f"{book}:{page}" + (f"#{anchor}" if anchor else "")
        hits.append(Hit(target, book, title, heading, re.sub(r"\s+", " ", snippet).strip(), rank))
    return hits
