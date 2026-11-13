"""The user manual inside divide: the wiki's pages, read as help topics.

The pages in ``pages/`` are a copy of the GitHub wiki (``tools/sync_manual.py``
refreshes them), so the manual is written once. This module turns their
Markdown into help topics: lines of styled spans, cross references between
topics (``[[Page]]``, ``[[text|Page]]``, ``[text](Page#section)``) and anchors
for the headings. Images are left out; external links are plain text.

Topics are laid out for a width: paragraphs, list items and the last column
of tables wrap, code blocks do not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PAGES = Path(__file__).with_name("pages")
CONTENTS = "_Sidebar"  # the wiki's sidebar is the table of contents
INDEX = "Index"  # generated: every topic and heading, alphabetically
HOME = "Home"


@dataclass(frozen=True)
class Span:
    text: str
    style: str = "text"  # text, bold, code, link, url, heading, title, rule, head
    link: int | None = None  # index into Topic.links


@dataclass
class Link:
    target: str  # "Page" or "Page#anchor"
    places: list[tuple[int, int, int]] = field(default_factory=list)  # (line, x0, x1)


@dataclass
class Topic:
    name: str
    title: str
    lines: list[list[Span]] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    anchors: dict[str, int] = field(default_factory=dict)  # slug -> line


# ------------------------------------------------------------------ pages
def page_name(text: str) -> str:
    """The page a wiki link names: ``Getting Started`` -> ``Getting-Started``."""
    return text.strip().replace(" ", "-")


def slug(heading: str) -> str:
    """GitHub's anchor for a heading."""
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


def page_names() -> list[str]:
    return sorted(p.stem for p in PAGES.glob("*.md") if not p.stem.startswith("_"))


@lru_cache(maxsize=None)
def source(name: str) -> str | None:
    path = PAGES / f"{name}.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def title_of(name: str) -> str:
    if name == CONTENTS:
        return "Contents"
    if name == INDEX:
        return "Index"
    text = source(name) or ""
    match = re.search(r"^# (.+)$", text, re.M)
    return _plain(match.group(1)) if match else name.replace("-", " ")


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


def index_source() -> str:
    """The Index topic in Markdown: every page and heading, alphabetically."""
    entries: list[tuple[str, str, str]] = []
    for name in page_names():
        title = title_of(name)
        entries.append((title, f"[[{title}|{name}]]", ""))
        for _, text in headings(name):
            label = re.sub(r"^\d+\.\s*", "", text)  # "1. Open the project": by its words
            entries.append((label, f"[{label}]({name}#{slug(text)})", f" · {title}"))
    entries.sort(key=lambda e: e[0].lower())
    lines = ["# Index", ""]
    letter = ""
    for key, link, where in entries:
        first = key[:1].upper()
        if first != letter:
            letter = first
            lines += ["", f"### {letter}", ""]
        lines.append(f"- {link}{where}")
    return "\n".join(lines) + "\n"


def topic_source(name: str) -> str | None:
    if name == INDEX:
        return index_source()
    text = source(name)
    if text is not None and name == CONTENTS:
        text = "# Contents\n\n" + text
    return text


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


def _inline(text: str, links: list[Link], base: str = "text") -> list[Span]:
    """Spans of one line of Markdown; links found are appended to ``links``."""
    spans: list[Span] = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            spans.append(Span(text[pos:m.start()], base))
        pos = m.end()
        if m.group("wiki"):
            label, _, page = m.group("wiki").partition("|")
            target = page_name(page or label)
            links.append(Link(target))
            spans.append(Span(label.strip(), "link", len(links) - 1))
        elif m.group("ltext"):
            label, url = m.group("ltext"), m.group("lurl")
            if "://" in url or url.startswith("mailto:"):
                spans.append(Span(_plain(label), "url"))
            else:
                links.append(Link(url))
                spans.append(Span(_plain(label), "link", len(links) - 1))
        elif m.group("bold"):
            spans.extend(_inline(m.group("bold"), links, "bold"))
        elif m.group("code"):
            spans.append(Span(m.group("code"), "code"))
        elif m.group("em"):
            spans.extend(_inline(m.group("em"), links, "bold" if base == "bold" else base))
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
    cells = [[c.strip() for c in row.strip().strip("|").split("|")] for row in rows]
    cells = [r for r in cells if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
    if not cells:
        return
    head, body = cells[0], cells[1:]
    has_head = any(head)
    rows_spans = [[_inline(c, topic.links) for c in row] for row in ([head] if has_head else []) + body]
    ncols = max(len(r) for r in rows_spans)
    widths = [0] * ncols
    for row in rows_spans:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], sum(len(s.text) for s in cell))
    gap = 2
    # the last column wraps; the others keep their width (up to half the page)
    for i in range(ncols - 1):
        widths[i] = min(widths[i], writer.width // 2)
    lead = sum(widths[:-1]) + gap * (ncols - 1)
    for r, row in enumerate(rows_spans):
        prefix: list[Span] = []
        for i in range(ncols - 1):
            cell = row[i] if i < len(row) else []
            style = "head" if has_head and r == 0 else None
            text_len = sum(len(s.text) for s in cell)
            cell = [Span(s.text, style or s.style, s.link) for s in cell]
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
        if has_head and r == 0:
            last = [Span(s.text, "head", s.link) for s in last]
        writer.wrap(last, indent=lead, first=prefix)
        if has_head and r == 0:
            writer.put([Span("─" * min(writer.width, lead + widths[-1]), "rule")])


def layout(name: str, width: int) -> Topic | None:
    """The topic ``name`` laid out for ``width`` columns (None: no such page)."""
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
            writer.wrap(_inline(" ".join(para), topic.links))
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
            spans = [Span(s.text, style if s.link is None else "link", s.link) for s in _inline(text_, topic.links)]
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
            writer.wrap(_inline(text_, topic.links), indent=len(pad) + len(marker) + 1, first=first)
        elif stripped.startswith(">"):
            flush()
            writer.wrap(_inline(stripped.lstrip("> "), topic.links), indent=2, first=[Span("  ")])
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


def search(word: str) -> list[tuple[str, str]]:
    """Index entries (label, target) whose text contains ``word``: topics first."""
    word = word.strip().lower()
    if not word:
        return []
    found: list[tuple[str, str]] = []
    for name in page_names():
        title = title_of(name)
        if word in title.lower():
            found.append((title, name))
    for name in page_names():
        for _, text in headings(name):
            if word in text.lower():
                found.append((f"{text} · {title_of(name)}", f"{name}#{slug(text)}"))
    return found
