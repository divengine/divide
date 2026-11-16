"""Full-text search of the help books, ranked: SQLite's FTS5.

Every section of every page (the page's opening, then each ``##`` / ``###``
heading with the text below it) is a row of an FTS5 table: the page title,
the heading and the text, plus where it leads (``book:Page#anchor``). A
query keeps the sections that have all the words typed and ranks them with
BM25, a match in a title worth more than one in a heading, which is worth
more than one in the text.

The words typed are of two kinds. The finished ones are stemmed (Porter):
``configure`` finds "configuring" and "configured". The last one is still
being typed, so it is a prefix; but a prefix of a stem is not a prefix of
the word (*Iterations* is indexed as ``iter``: ``itera`` would find nothing),
so the sections are indexed twice, stemmed (``help``) and as written
(``help_raw``, same rows), and the last word may match either. FTS5 also
cuts the snippet that shows each match in its sentence.

The index is built by ``tools/sync_book.py`` when it copies a book, and is
shipped beside the books (``manual/search.sqlite``). It records a
fingerprint of the pages it was built from: when the pages differ (a book
copied by hand, a checkout in the middle of a change) the index is built
again, in memory, on the first search. It takes a fraction of a second.

Each language of the books has its index (``search.sqlite`` for the
originals, ``search.<language>.sqlite`` for the books in another language,
with the pages they have not translated yet in the original's). Porter's
stemmer is English's: the other languages are indexed as written, where a
prefix still finds the longer words.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from divide import i18n, manual

INDEX_FILE = manual.HERE / "search.sqlite"
VERSION = "2"  # of the index's layout: a new one rebuilds the index
TOKENIZER = "porter unicode61 remove_diacritics 2"  # English's
RAW_TOKENIZER = "unicode61 remove_diacritics 2"  # the words as written: for the prefix being typed
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


def index_file(lang: str | None = None) -> Path:
    lang = lang or manual.language()
    return INDEX_FILE if lang == i18n.SOURCE else INDEX_FILE.with_name(f"search.{lang}.sqlite")


def tokenizer(lang: str) -> str:
    return TOKENIZER if lang == i18n.SOURCE else RAW_TOKENIZER


def fingerprint() -> str:
    """Of the books' pages (in the language they are shown in) and the index's layout:
    an index built from other pages is stale."""
    digest = hashlib.sha1(f"{VERSION}\0{manual.language()}".encode())
    for book in manual.books():
        for name, path in sorted(manual.files(book.id).items()):
            if name.endswith(".md"):
                digest.update(f"{book.id}/{path.parent.name}/{name}\0".encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


# -------------------------------------------------------------------- index
def _create(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    for table, tokenizer_ in (("help", tokenizer(manual.language())), ("help_raw", RAW_TOKENIZER)):
        db.execute(
            f"CREATE VIRTUAL TABLE {table} USING fts5("
            "title, heading, body, book UNINDEXED, page UNINDEXED, anchor UNINDEXED, "
            f"tokenize = '{tokenizer_}')"
        )


def fill(db: sqlite3.Connection) -> int:
    """Index every book into ``db`` (empty, made by ``_create``). Returns the rows."""
    rows = 0
    for book in manual.books():
        for name in manual.page_names(book.id):
            title = manual.title_of(name)
            page = manual.split(name)[1]
            for heading, anchor, body in sections(name):
                rows += 1
                for table in ("help", "help_raw"):  # the same rowid in both
                    db.execute(f"INSERT INTO {table}(rowid, title, heading, body, book, page, anchor) VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (rows, title, heading, body, book.id, page, anchor))
    db.execute("INSERT INTO meta VALUES ('fingerprint', ?)", (fingerprint(),))
    db.execute("INSERT INTO help(help) VALUES ('optimize')")
    db.execute("INSERT INTO help_raw(help_raw) VALUES ('optimize')")
    db.commit()
    return rows


def build(path: Path | None = None, lang: str = i18n.SOURCE) -> int:
    """Write the index file of a language. Returns the rows."""
    path = path or index_file(lang)
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    try:
        with manual.reading_in(lang):
            _create(db)
            rows = fill(db)
        db.execute("VACUUM")
    finally:
        db.close()
    tmp.replace(path)
    return rows


def build_all() -> dict[str, int]:
    """The index of every language there are books in (``tools/sync_book.py`` calls it);
    an index of a language no book is in any more is removed."""
    built = {lang: build(lang=lang) for lang in manual.languages()}
    for old in INDEX_FILE.parent.glob("search.*.sqlite"):
        if old.name.split(".")[1] not in built:
            old.unlink()
    return built


@lru_cache(maxsize=4)
def _connection(lang: str, stamp: str) -> sqlite3.Connection:
    """The shipped index when it was built from these pages, else one built in memory."""
    path = index_file(lang)
    if path.is_file():
        try:
            db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
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
    return _connection(manual.language(), fingerprint())


# -------------------------------------------------------------------- query
def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _quoted(words: list[str], prefix_last: bool = False, op: str = " ") -> str:
    """Quoted, so FTS5's own operators (AND, NEAR...) are plain words."""
    terms = [f'"{w}"' for w in words]
    if prefix_last and terms:
        terms[-1] += "*"
    return op.join(terms)


def search(text: str, limit: int = MAX_RESULTS) -> list[Hit]:
    """The sections that match ``text``, best first: all the words (the finished ones
    stemmed, the last one a prefix of the word or of its stem) if any section has them
    all, else any of them."""
    found = words(text)
    if not found:
        return []
    db = connection()
    weights = ", ".join(map(str, WEIGHTS))
    done, typing = found[:-1], found[-1]
    # the last word: a prefix of the word as written, or of its stem; each row's best rank
    last = (
        f"SELECT rowid, bm25(help_raw, {weights}) AS r FROM help_raw WHERE help_raw MATCH :typing_raw "
        f"UNION ALL SELECT rowid, bm25(help, {weights}) FROM help WHERE help MATCH :typing"
    )
    params = {"typing_raw": _quoted([typing], True), "typing": _quoted([typing], True), "limit": limit}
    if done:
        params["done"] = _quoted(done)
        sql = (
            f"WITH last AS (SELECT rowid, MIN(r) AS r FROM ({last}) GROUP BY rowid), "
            f"done AS (SELECT rowid, bm25(help, {weights}) AS r FROM help WHERE help MATCH :done) "
            "SELECT rowid, done.r + last.r AS rank FROM done JOIN last USING (rowid) ORDER BY rank LIMIT :limit"
        )
    else:
        sql = f"SELECT rowid, MIN(r) AS rank FROM ({last}) GROUP BY rowid ORDER BY rank LIMIT :limit"
    try:
        ranked = db.execute(sql, params).fetchall()
        if not ranked and done:  # no section has them all: any of them, as written
            ranked = db.execute(
                f"SELECT rowid, bm25(help_raw, {weights}) AS rank FROM help_raw WHERE help_raw MATCH ? "
                "ORDER BY rank LIMIT ?", (_quoted(found, True, " OR "), limit)).fetchall()
    except sqlite3.Error:
        return []
    return [_hit(db, rowid, rank, found) for rowid, rank in ranked]


def _hit(db: sqlite3.Connection, rowid: int, rank: float, found: list[str]) -> Hit:
    """The section ``rowid``, with the sentence where the words are."""
    snip = f"snippet({{t}}, 2, '{MARK_START}', '{MARK_END}', '...', {SNIPPET_WORDS})"
    row = None
    # stemmed (lights "configuration" for "configure"), else as written (lights "Itera" of "Iterations")
    for table, query in (("help", _quoted(found, True, " OR ")), ("help_raw", _quoted(found, True, " OR "))):
        row = db.execute(
            f"SELECT book, page, anchor, title, heading, {snip.format(t=table)} FROM {table} "
            f"WHERE {table} MATCH ? AND rowid = ?", (query, rowid)).fetchone()
        if row and MARK_START in row[5]:
            break
    if row is None:
        row = db.execute("SELECT book, page, anchor, title, heading, substr(body, 1, 120) FROM help WHERE rowid = ?",
                         (rowid,)).fetchone()
    book, page, anchor, title, heading, snippet = row
    target = f"{book}:{page}" + (f"#{anchor}" if anchor else "")
    return Hit(target, book, title, heading, re.sub(r"\s+", " ", snippet).strip(), rank)
