"""The help inside divide: several books, each a copy of a wiki or a docs folder.

``books.json`` lists the books (divide's manual, Div's documentation, …) and
``books/<id>/`` holds each one's pages, copied from where they are written
by ``tools/sync_book.py``: a documentation is written once, in its own place.
This module turns their Markdown into help topics: lines of styled spans,
cross references between topics (``[[Page]]``, ``[[text|Page]]``,
``[text](Page#section)``, ``[[book:Page]]`` to another book) and anchors for
the headings. Images are left out; external links are plain text; links
that lead nowhere in the book are plain text too.

A topic is named ``book:Page`` (a bare ``Page`` is divide's). Each book has
a generated Contents (its wiki sidebar or its list of pages) and an Index;
the Books topic lists the books.

Topics are laid out for a width: paragraphs, list items and the last column
of tables wrap, code blocks do not.
"""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, unquote

HERE = Path(__file__).parent
BOOKS_DIR = HERE / "books"
DEFAULT = "divide"  # the book of bare topic names
LIBRARY = "_Books"  # generated: the list of books
CONTENTS = "_Contents"  # generated per book: its sidebar or its list of pages
INDEX = "_Index"  # generated per book: every topic and heading, alphabetically


@dataclass(frozen=True)
class Book:
    id: str
    title: str
    description: str = ""
    home: str = "Home"
    contents: str = ""  # "_Sidebar.md" (a wiki's) or a file listing the pages in order
    source: str = ""

    @property
    def dir(self) -> Path:
        return BOOKS_DIR / self.id


@dataclass(frozen=True)
class Span:
    text: str
    style: str = "text"  # text, bold, code, link, url, heading, title, rule, head
    link: int | None = None  # index into Topic.links


@dataclass
class Link:
    target: str  # "book:Page" or "book:Page#anchor"
    places: list[tuple[int, int, int]] = field(default_factory=list)  # (line, x0, x1)


@dataclass
class Topic:
    name: str
    title: str
    lines: list[list[Span]] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    anchors: dict[str, int] = field(default_factory=dict)  # slug -> line


# ------------------------------------------------------------------ books
@lru_cache(maxsize=None)
def books() -> tuple[Book, ...]:
    data = json.loads((HERE / "books.json").read_text(encoding="utf-8"))
    fields = Book.__dataclass_fields__
    return tuple(Book(**{k: v for k, v in entry.items() if k in fields}) for entry in data)


def book(book_id: str) -> Book | None:
    return next((b for b in books() if b.id == book_id), None)


def split(name: str) -> tuple[str, str]:
    """``book:Page`` -> ``(book, Page)``; a bare ``Page`` is divide's."""
    if name == LIBRARY:
        return "", LIBRARY
    book_id, sep, page = name.partition(":")
    if sep and book(book_id) is not None:
        return book_id, page
    return DEFAULT, name


def qualify(name: str) -> str:
    book_id, page = split(name)
    return f"{book_id}:{page}" if book_id else page


def book_of(name: str) -> str:
    return split(name)[0] or DEFAULT


def contents_of(book_id: str) -> str:
    return f"{book_id}:{CONTENTS}"


def index_of(book_id: str) -> str:
    return f"{book_id}:{INDEX}"


# ------------------------------------------------------------------ pages
def page_name(text: str) -> str:
    """The page a wiki link names: ``Getting Started`` -> ``Getting-Started``."""
    return text.strip().replace(" ", "-")


def slug(heading: str) -> str:
    """GitHub's anchor for a heading."""
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


@lru_cache(maxsize=None)
def _stems(book_id: str) -> tuple[str, ...]:
    b = book(book_id)
    if b is None:
        return ()
    return tuple(sorted(p.stem for p in b.dir.glob("*.md")))


def page_names(book_id: str | None = None) -> list[str]:
    """Qualified names of the pages of a book (of every book: None)."""
    ids = [book_id] if book_id else [b.id for b in books()]
    return [f"{i}:{stem}" for i in ids for stem in _stems(i) if not stem.startswith("_")]


def resolve(book_id: str, text: str) -> str | None:
    """The page of ``book_id`` that a link names, as GitHub would find it."""
    stems = _stems(book_id)
    text = unquote(text.strip()).removeprefix("./")
    if text.lower().endswith(".md"):
        text = text[:-3]
    if "/" in text:
        return None  # outside the book
    for candidate in (text, page_name(text)):
        if candidate in stems:
            return candidate
    lower = {s.lower(): s for s in stems}
    return lower.get(text.lower()) or lower.get(page_name(text).lower())


def resolve_target(here: str, target: str) -> str | None:
    """A link's target in the topic ``here`` -> ``book:Page[#anchor]`` (None: nowhere)."""
    page, _, anchor = unquote(target).partition("#")
    book_id = split(here)[0]
    if page == LIBRARY:
        found = LIBRARY
    elif not page:
        found = qualify(here)
    else:
        other, sep, rest = page.partition(":")
        if sep and book(other) is not None:
            book_id, page = other, rest
        if page in (CONTENTS, INDEX):
            found = f"{book_id}:{page}"
        else:
            stem = resolve(book_id or DEFAULT, page)
            if stem is None:
                return None
            found = f"{book_id or DEFAULT}:{stem}"
    return f"{found}#{anchor}" if anchor else found


@lru_cache(maxsize=None)
def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def source(name: str) -> str | None:
    book_id, page = split(name)
    b = book(book_id)
    if b is None or page not in _stems(book_id):
        return None
    return _read(b.dir / f"{page}.md")


def title_of(name: str) -> str:
    book_id, page = split(name)
    if page == LIBRARY:
        return "Books"
    if page == CONTENTS:
        return "Contents"
    if page == INDEX:
        return "Index"
    text = source(name) or ""
    match = re.search(r"^# (.+)$", text, re.M)
    return _plain(match.group(1)) if match else page.replace("-", " ")


def window_title(name: str) -> str:
    """The help window's title for a topic: the book, unless it is divide's."""
    book_id = split(name)[0]
    b = book(book_id)
    title = title_of(name)
    return f"Help: {title}" if not b or book_id == DEFAULT else f"Help: {b.title} · {title}"


def headings(name: str) -> list[tuple[int, str]]:
    """``(level, text)`` of the ``##`` and ``###`` headings of a page."""
    out = []
    in_code = False
    for line in (source(name) or "").splitlines():
        if line.startswith("```"):
            in_code = not in_code
        elif not in_code and (m := re.match(r"^(#{2,3}) (.+)$", line)):
            out.append((len(m.group(1)), _plain(m.group(2))))
    return out


def _wiki(label: str, target: str) -> str:
    return f"[[{label}|{target}]]"


def library_source() -> str:
    lines = ["# Books", "", "The documentation inside divide, one book each.", ""]
    for b in books():
        lines.append(f"- {_wiki(b.title, contents_of(b.id))}: {b.description}")
    return "\n".join(lines) + "\n"


def contents_source(book_id: str) -> str | None:
    """A book's table of contents: its wiki sidebar, or its list of pages."""
    b = book(book_id)
    if b is None:
        return None
    head = ["# Contents", "", f"{b.title}. {_wiki('Index', index_of(book_id))} · {_wiki('Other books', LIBRARY)}", ""]
    if b.contents.endswith(".md"):
        text = _read(b.dir / b.contents)
        if text is not None:
            return "\n".join(head) + "\n" + text
    lines = head
    order = _read(b.dir / b.contents) if b.contents else None
    stems = [Path(line.strip()).stem for line in (order or "").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    stems = [s for s in stems if s in _stems(book_id)] or [s for s in _stems(book_id) if not s.startswith("_")]
    for stem in stems:
        number = re.match(r"^(\d+(?:\.\d+)*)\s", stem)
        depth = number.group(1).count(".") if number else 0
        lines.append("  " * depth + f"- {_wiki(title_of(f'{book_id}:{stem}'), f'{book_id}:{stem}')}")
    return "\n".join(lines) + "\n"


def index_source(book_id: str = DEFAULT) -> str:
    """A book's Index in Markdown: every page and heading, alphabetically."""
    entries: list[tuple[str, str, str]] = []
    for name in page_names(book_id):
        title = title_of(name)
        entries.append((title, _wiki(title, name), ""))
        for _, text in headings(name):
            label = re.sub(r"^[\d.]+\s*", "", text)  # "1. Open the project": by its words
            entries.append((label, f"[{label}]({quote(name, safe=':')}#{slug(text)})", f" · {title}"))
    entries.sort(key=lambda e: re.sub(r"^[\d.]+\s*", "", e[0]).lower())
    lines = ["# Index", ""]
    letter = ""
    for key, link, where in entries:
        first = re.sub(r"^[\d.]+\s*", "", key)[:1].upper()
        if first != letter:
            letter = first
            lines += ["", f"### {letter}", ""]
        lines.append(f"- {link}{where}")
    return "\n".join(lines) + "\n"


def topic_source(name: str) -> str | None:
    book_id, page = split(name)
    if page == LIBRARY:
        return library_source()
    if page == INDEX:
        return index_source(book_id) if book(book_id) else None
    if page == CONTENTS:
        return contents_source(book_id)
    return source(name)


# ----------------------------------------------------------------- inline
_INLINE = re.compile(
    r"!\[[^\]]*\]\([^)]*\)"  # image: left out
    r"|\[\[(?P<wiki>[^\]]+)\]\]"
    r"|\[(?P<ltext>[^\]]+)\]\((?P<lurl>[^)\s]+)\)"
    r"|\*\*(?P<bold>.+?)\*\*"
    r"|`(?P<code>[^`]+)`"
    r"|(?<![\w*])\*(?P<em>[^*\s][^*]*?)\*(?![\w*])"
)


def _plain(text: str) -> str:
    return "".join(s.text for s in _inline(text, []))


def _inline(text: str, links: list[Link], base: str = "text", here: str | None = None) -> list[Span]:
    """Spans of one line of Markdown. Links found in the topic ``here`` are
    appended to ``links``; without ``here``, or leading nowhere, they are text."""
    spans: list[Span] = []
    pos = 0

    def link(label: str, target: str) -> None:
        found = resolve_target(here, target) if here is not None else None
        if found is None:
            spans.append(Span(label, base))
        else:
            links.append(Link(found))
            spans.append(Span(label, "link", len(links) - 1))

    for m in _INLINE.finditer(text):
        if m.start() > pos:
            spans.append(Span(text[pos:m.start()], base))
        pos = m.end()
        if m.group("wiki"):
            label, _, page = m.group("wiki").partition("|")
            link(label.strip(), (page or label).strip())
        elif m.group("ltext"):
            label, url = m.group("ltext"), m.group("lurl")
            if "://" in url or url.startswith("mailto:"):
                spans.append(Span(_plain(label), "url"))
            else:
                link(_plain(label), url)
        elif m.group("bold"):
            spans.extend(_inline(m.group("bold"), links, "bold", here))
        elif m.group("code"):
            spans.append(Span(m.group("code"), "code"))
        elif m.group("em"):
            spans.extend(_inline(m.group("em"), links, "bold" if base == "bold" else base, here))
    if pos < len(text):
        spans.append(Span(text[pos:], base))
    return spans


# ----------------------------------------------------------------- layout
class _Writer:
    def __init__(self, topic: Topic, width: int) -> None:
        self.topic = topic
        self.width = max(20, width)

    def blank(self) -> None:
        if self.topic.lines and self.topic.lines[-1]:
            self.topic.lines.append([])

    def put(self, spans: list[Span]) -> None:
        y = len(self.topic.lines)
        x = 0
        for span in spans:
            if span.link is not None:
                self.topic.links[span.link].places.append((y, x, x + len(span.text)))
            x += len(span.text)
        self.topic.lines.append(_merge(spans))

    def wrap(self, spans: list[Span], indent: int = 0, first: list[Span] | None = None) -> None:
        """Fill ``spans`` into lines of the width; ``first`` prefixes the first line
        (a bullet), the others are indented by ``indent``."""
        words: list[tuple[str, Span, bool]] = []  # (word, its span, space before)
        space = False
        for span in spans:
            for piece in re.split(r"(\s+)", span.text):
                if not piece:
                    continue
                if piece.isspace():
                    space = True
                    continue
                words.append((piece, span, space and bool(words)))
                space = False
        line: list[Span] = list(first or [Span(" " * indent)] if indent or first else [])
        used = sum(len(s.text) for s in line)
        start = used
        for word, span, gap in words:
            need = len(word) + (1 if gap and used > start else 0)
            if used > start and used + need > self.width:
                self.put(line)
                line = [Span(" " * indent)] if indent else []
                used = start = indent
                need = len(word)
            if used > start and gap:
                line.append(Span(" ", span.style, span.link))
                used += 1
            line.append(Span(word, span.style, span.link))
            used += len(word)
        if used > start or first:
            self.put(line)


def _merge(spans: list[Span]) -> list[Span]:
    out: list[Span] = []
    for span in spans:
        if not span.text:
            continue
        if out and out[-1].style == span.style and out[-1].link == span.link:
            out[-1] = Span(out[-1].text + span.text, span.style, span.link)
        else:
            out.append(span)
    return out


def _table(writer: _Writer, rows: list[str]) -> None:
    topic = writer.topic
    # cells split at the pipes that are not escaped (``\|`` is a pipe in a cell)
    cells = [[c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", re.sub(r"^\||(?<!\\)\|$", "", row.strip()))]
             for row in rows]
    cells = [r for r in cells if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
    if not cells:
        return
    head, body = cells[0], cells[1:]
    has_head = any(head)
    rows_spans = [[_inline(c, topic.links, here=topic.name) for c in row] for row in ([head] if has_head else []) + body]
    ncols = max(len(r) for r in rows_spans)
    widths = [0] * ncols
    for row in rows_spans[1:] if has_head and len(rows_spans) > 1 else rows_spans:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], sum(len(s.text) for s in cell))
    gap = 2
    # the last column wraps; the others keep their width (up to half the page)
    for i in range(ncols - 1):
        word = max((len(w) for w in _plain(head[i]).split()), default=0) if has_head and i < len(head) else 0
        widths[i] = max(1, min(max(widths[i], word), writer.width // 2))
    # too wide for the last column: narrow the widest of the others
    while ncols > 1 and sum(widths[:-1]) + gap * (ncols - 1) + 12 > writer.width:
        widest = max(range(ncols - 1), key=lambda i: widths[i])
        if widths[widest] <= 4:
            break
        widths[widest] -= 1
    lead = sum(widths[:-1]) + gap * (ncols - 1)
    if has_head:
        # the heads wrap inside their column, over as many lines as they need
        heads = [_plain(c) for c in head] + [""] * (ncols - len(head))
        last_width = max(12, writer.width - lead)
        wrapped = [textwrap.wrap(h, widths[i] if i < ncols - 1 else last_width, break_long_words=True) or [""]
                   for i, h in enumerate(heads)]
        for k in range(max(len(w) for w in wrapped)):
            parts = [(w[k] if k < len(w) else "").ljust(widths[i]) for i, w in enumerate(wrapped[:-1])]
            text = (" " * gap).join(parts + [wrapped[-1][k] if k < len(wrapped[-1]) else ""])
            writer.put([Span(text.rstrip(), "head")])
        writer.put([Span("─" * min(writer.width, lead + max(widths[-1], 1)), "rule")])
        rows_spans = rows_spans[1:]
    for row in rows_spans:
        prefix: list[Span] = []
        for i in range(ncols - 1):
            cell = row[i] if i < len(row) else []
            text_len = sum(len(s.text) for s in cell)
            if text_len > widths[i]:  # too long: cut, keep the first spans
                cut, kept = widths[i], []
                for s in cell:
                    if cut <= 0:
                        break
                    kept.append(Span(s.text[:cut], s.style, s.link))
                    cut -= len(s.text)
                cell, text_len = kept, widths[i]
            prefix += cell + [Span(" " * (widths[i] - text_len + gap))]
        last = row[ncols - 1] if len(row) >= ncols else []
        writer.wrap(last, indent=lead, first=prefix)


def layout(name: str, width: int) -> Topic | None:
    """The topic ``name`` laid out for ``width`` columns (None: no such page)."""
    name = qualify(name)
    text = topic_source(name)
    if text is None:
        return None
    topic = Topic(name, title_of(name))
    writer = _Writer(topic, width)
    lines = text.splitlines()
    i = 0
    para: list[str] = []

    def flush() -> None:
        if para:
            writer.wrap(_inline(" ".join(para), topic.links, here=topic.name))
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            writer.blank()
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                writer.put([Span("  " + lines[i].rstrip(), "code")])
                i += 1
            writer.blank()
        elif m := re.match(r"^(#{1,6}) (.+)$", line):
            flush()
            level, text_ = len(m.group(1)), m.group(2).strip()
            writer.blank()
            topic.anchors.setdefault(slug(_plain(text_)), len(topic.lines))
            style = "title" if level == 1 else "heading"
            spans = [Span(s.text, style if s.link is None else "link", s.link) for s in _inline(text_, topic.links, here=topic.name)]
            writer.wrap(spans)
            if level <= 2:
                writer.put([Span(("═" if level == 1 else "─") * min(writer.width, sum(len(s.text) for s in spans)), "rule")])
            writer.blank()
        elif stripped.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            writer.blank()
            _table(writer, rows)
            writer.blank()
            continue
        elif m := re.match(r"^(\s*)([-*+]|\d+\.) (.*)$", line):
            flush()
            depth = len(m.group(1).expandtabs(4)) // 2
            marker = "•" if not m.group(2)[0].isdigit() else m.group(2)
            text_ = m.group(3)
            # continuation lines of the item
            while i + 1 < len(lines) and lines[i + 1].startswith("  " * (depth + 1)) and lines[i + 1].strip() \
                    and not re.match(r"^\s*([-*+]|\d+\.) ", lines[i + 1]):
                i += 1
                text_ += " " + lines[i].strip()
            pad = "  " * depth + " "
            first = [Span(pad), Span(marker + " ", "text")]
            writer.wrap(_inline(text_, topic.links, here=topic.name), indent=len(pad) + len(marker) + 1, first=first)
        elif stripped.startswith(">"):
            flush()
            writer.wrap(_inline(_alert(stripped.lstrip("> ")), topic.links, here=topic.name), indent=2, first=[Span("  ")])
        elif re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            flush()
            writer.blank()
            writer.put([Span("─" * writer.width, "rule")])
            writer.blank()
        elif not stripped:
            flush()
            writer.blank()
        elif stripped.startswith("<!--") or re.fullmatch(r"!\[[^\]]*\]\([^)]*\)", stripped):
            flush()  # comments and images: left out
        else:
            para.append(stripped)
        i += 1
    flush()
    while topic.lines and not topic.lines[-1]:
        topic.lines.pop()
    # wrapped links have several places; a link with none (cut in a table) is dropped later
    return topic


def search(word: str, first: str | None = None) -> list[tuple[str, str]]:
    """Index entries (label, target) whose text contains ``word``, in every
    book (``first`` before the others): topic titles first, then headings."""
    word = word.strip().lower()
    if not word:
        return []
    order = sorted(books(), key=lambda b: b.id != first)
    names = [n for b in order for n in page_names(b.id)]
    found: list[tuple[str, str]] = []
    for name in names:
        title = title_of(name)
        if word in title.lower():
            found.append((title, name))
    for name in names:
        for _, text in headings(name):
            if word in text.lower():
                found.append((f"{text} · {title_of(name)}", f"{name}#{slug(text)}"))
    return found


def _alert(text: str) -> str:
    """GitHub's ``> [!WARNING]`` as a bold word."""
    m = re.fullmatch(r"\[!(\w+)\]\s*(.*)", text)
    return f"**{m.group(1).capitalize()}:** {m.group(2)}" if m else text
