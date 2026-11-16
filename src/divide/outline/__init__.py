"""The outline of a file: its parts as a tree, for Search > Outline.

Every language divide colours has one: the declarations of a PHP or
JavaScript file, the constructs of a Div template, the headings of Markdown,
the elements of HTML and XML, the rules of CSS, the keys of JSON, YAML and
TOML, the tables of SQL... A builder (one module per family) turns the text
into ``Node``s: a kind (its icon), a label, where it is, and what it holds.

The label is made of spans, each with the token kind the editor colours that
text with (``php.type``, ``ts.tag``, ``div.var``...): a painter runs the
language's own highlighting over the part of the text a label shows, so the
outline reads like the code. Icons are one ASCII letter each, coloured by
kind; class members carry UML's visibility marks, + # -, coloured too.
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from rich.style import Style
from rich.text import Text

from divide import themes

Span = tuple[str, "str | None"]  # (text, token kind or None)
MAX_LABEL = 70


@dataclass
class Node:
    """One part of the file: ``start``..``end`` is what Enter selects (a name, a tag)."""

    kind: str
    label: list[Span]
    start: int
    end: int
    mark: str = ""  # UML's visibility: + public, # protected, - private
    children: list["Node"] = field(default_factory=list)

    @property
    def text(self) -> str:
        """The label as plain text, its mark first: ``+ add(string $name): self``."""
        name = "".join(t for t, _ in self.label)
        return f"{self.mark} {name}" if self.mark else name

    @property
    def key(self) -> str:
        """What finds the same node again after an edit: its kind and its label."""
        return f"{self.kind}:{self.text}"


# kind -> (letter, colour slot). Slots, like the project window's file marks:
# every palette gives each one a colour that reads on its windows.
TYPE, CALL, FIELD, CONST, MODULE, MARKUP, BLOCK, OTHER = (
    "lightcyan", "yellow", "lightgreen", "lightmagenta", "cyan", "lightred", "white", "lightgray")
ICONS: dict[str, tuple[str, str]] = {
    # code: PHP, JavaScript, shell
    "namespace": ("n", MODULE), "class": ("C", TYPE), "interface": ("I", TYPE), "trait": ("T", TYPE),
    "enum": ("E", TYPE), "method": ("m", CALL), "function": ("f", CALL), "property": ("p", FIELD),
    "const": ("k", CONST), "case": ("k", CONST), "variable": ("v", FIELD), "import": ("u", MODULE),
    # Div
    "definition": ("v", FIELD), "dialect": ("d", MODULE), "include": ("i", MODULE), "loop": ("l", CALL),
    "iteration": ("r", CALL), "condition": ("?", CALL), "capsule": ("c", TYPE), "location": ("o", CONST),
    "subparser": ("s", MARKUP), "multirep": ("x", MARKUP), "ignore": ("g", OTHER), "macro": ("a", MARKUP),
    # documents and data
    "heading": ("#", BLOCK), "element": ("<", MARKUP), "rule": ("s", TYPE), "at-rule": ("@", CONST),
    "key": ("k", FIELD), "object": ("o", TYPE), "array": ("a", CONST), "table": ("t", TYPE),
    "column": ("c", FIELD), "view": ("w", TYPE), "index": ("x", CONST), "section": ("[", TYPE),
}
VISIBILITY = {"public": "+", "protected": "#", "private": "-"}  # UML's marks
MARK_COLOURS = {"+": "lightgreen", "#": "yellow", "-": "lightred"}


def icon(kind: str) -> tuple[str, str]:
    return ICONS.get(kind, ("-", OTHER))


def walk(nodes: list[Node], level: int = 0) -> Iterator[tuple[int, Node]]:
    """Every node, depth first, with its level."""
    for node in nodes:
        yield level, node
        yield from walk(node.children, level + 1)


def rich_label(node: Node, palette: themes.Palette | None = None, plain: bool = False) -> Text:
    """``icon mark label``: the icon and the mark in their colours, the label in the editor's."""
    palette = palette or themes.current()
    letter, slot = icon(node.kind)
    if plain:
        return Text(f"{letter} {node.text}")
    styles = palette.token_styles()
    parts: list[tuple[str, Style] | str] = [(letter, Style(color=palette.hex(slot), bold=True)), " "]
    if node.mark:
        parts += [(node.mark, Style(color=palette.hex(MARK_COLOURS.get(node.mark, OTHER)), bold=True)), " "]
    for text, kind in node.label:
        style = token_style(styles, kind)
        parts.append((text, Style(color=style.color, bold=style.bold, italic=style.italic)) if style else text)
    return Text.assemble(*parts)


def token_style(styles: dict[str, Style], kind: str | None) -> Style | None:
    """The style of a token kind, or of the nearest kind it refines
    (``php.function.method`` -> ``php.function``); only its colour and weight:
    the outline keeps its own background."""
    while kind:
        if kind in styles:
            return styles[kind]
        kind = kind.rpartition(".")[0]
    return None


# ------------------------------------------------------------------ painters
_SPACE = re.compile(r"\s+")


def tidy(spans: list[Span], limit: int = MAX_LABEL) -> list[Span]:
    """The spans on one line: runs of white space as one space, the ends
    trimmed, cut with ``...`` past ``limit`` characters."""
    out: list[Span] = []
    for text, kind in spans:
        text = _SPACE.sub(" ", text)
        if not text:
            continue
        if out and out[-1][1] == kind:
            out[-1] = (out[-1][0] + text, kind)
        else:
            out.append((text, kind))
    if out:
        out[0] = (out[0][0].lstrip(), out[0][1])
        out[-1] = (out[-1][0].rstrip(), out[-1][1])
    total, cut = 0, []
    for text, kind in out:
        if total + len(text) > limit:
            cut.append((text[: max(0, limit - total - 3)] + "...", kind))
            break
        cut.append((text, kind))
        total += len(text)
    return [(t, k) for t, k in cut if t]


def default_kind(spans: list[Span], kind: str) -> list[Span]:
    """The words no highlighting coloured, in ``kind`` (a declared class's name:
    the grammar colours where it is used, not where it is declared)."""
    return [(text, kind if k is None and any(c.isalnum() for c in text) else k) for text, k in spans]


class Painter:
    """The token kinds of a text, by character offset, from a list of tokens
    (``.start``, ``.end``, ``.kind``: Div's lexer, INI's, CSV's)."""

    def __init__(self, text: str, tokens: list) -> None:
        self.text = text
        self.tokens = tokens
        self._kinds: list[str | None] | None = None

    def kinds(self) -> list[str | None]:
        if self._kinds is None:
            kinds: list[str | None] = [None] * len(self.text)
            for tok in self.tokens:
                for i in range(max(0, tok.start), min(len(kinds), tok.end)):
                    kinds[i] = tok.kind
            self._kinds = kinds
        return self._kinds

    def spans(self, start: int, end: int) -> list[Span]:
        kinds = self.kinds()
        out: list[Span] = []
        i = start
        while i < end:
            j = i + 1
            while j < end and kinds[j] == kinds[i]:
                j += 1
            out.append((self.text[i:j], kinds[i]))
            i = j
        return tidy(out)


class TreePainter:
    """The token kinds of a text parsed by tree-sitter: the language's highlight
    query, run over the bytes a label shows (later captures win, as in the editor)."""

    def __init__(self, source: bytes, tree, query) -> None:
        self.source = source
        self.tree = tree
        self.query = query

    def spans(self, start_byte: int, end_byte: int) -> list[Span]:
        from tree_sitter import QueryCursor

        length = end_byte - start_byte
        kinds: list[str | None] = [None] * length
        if self.query is not None:
            cursor = QueryCursor(self.query)
            cursor.set_byte_range(start_byte, end_byte)
            for name, nodes in cursor.captures(self.tree.root_node).items():
                for node in nodes:
                    for b in range(max(node.start_byte, start_byte), min(node.end_byte, end_byte)):
                        kinds[b - start_byte] = name
        out: list[Span] = []
        i = 0
        while i < length:
            j = i + 1
            while j < length and kinds[j] == kinds[i]:
                j += 1
            out.append((self.source[start_byte + i:start_byte + j].decode("utf-8", "replace"), kinds[i]))
            i = j
        return tidy(out)

    def node_spans(self, *nodes) -> list[Span]:
        """The spans of one or more nodes, one after the other (a space between gaps)."""
        nodes = [n for n in nodes if n is not None]
        if not nodes:
            return []
        out: list[Span] = []
        for n, node in enumerate(nodes):
            if n and node.start_byte > nodes[n - 1].end_byte:
                gap = self.source[nodes[n - 1].end_byte:node.start_byte].decode("utf-8", "replace")
                out.append((" " if gap.strip() == "" and gap else gap, None))
            out.extend(self.spans(node.start_byte, node.end_byte))
        return tidy(out)


class Offsets:
    """Byte offsets of a UTF-8 text as character offsets (tree-sitter counts bytes)."""

    def __init__(self, source: bytes) -> None:
        self.source = source
        self.ascii = source.isascii()
        self._starts: list[int] | None = None  # the byte where each character starts

    def __call__(self, byte: int) -> int:
        if self.ascii:
            return byte
        if self._starts is None:
            starts, at = [], 0
            for ch in self.source.decode("utf-8", "replace"):
                starts.append(at)
                at += len(ch.encode("utf-8"))
            self._starts = starts
        return bisect.bisect_left(self._starts, byte)


@dataclass
class Parsed:
    """A text parsed by one of tree-sitter's grammars, with what the builders need."""

    source: bytes
    tree: object
    paint: TreePainter
    offset: Offsets

    def text(self, node) -> str:
        return self.source[node.start_byte:node.end_byte].decode("utf-8", "replace")

    def line(self, node, end=None) -> list[Span]:
        """The spans of ``node`` (up to ``end``, a byte or a node's start) on its first line."""
        stop = node.end_byte if end is None else end if isinstance(end, int) else end.start_byte
        newline = self.source.find(b"\n", node.start_byte, stop)
        return self.paint.spans(node.start_byte, newline if newline >= 0 else stop)

    def node(self, kind: str, select, label: list[Span], children: list[Node] | None = None, mark: str = "") -> Node:
        """A Node whose Enter selects ``select`` (a tree-sitter node)."""
        return Node(kind, label, self.offset(select.start_byte), self.offset(select.end_byte), mark, children or [])


def parse(lang: str, text: str) -> Parsed | None:
    """``text`` parsed with the grammar divide colours ``lang`` with; None without it."""
    from divide.lang import treesitter

    found = treesitter.grammar(lang)
    if found is None:
        return None
    from tree_sitter import Parser

    language, query_source = found
    source = text.encode("utf-8")
    tree = Parser(language).parse(source)  # type: ignore[arg-type]
    return Parsed(source, tree, TreePainter(source, tree, treesitter.query(language, query_source)), Offsets(source))


def named(node, *types: str) -> list:
    """The named children of ``node`` of these types (all of them without types)."""
    return [c for c in node.named_children if not types or c.type in types]


def first(node, *types: str):
    return next(iter(named(node, *types)), None)


# ------------------------------------------------------------------ builders
Builder = Callable[..., "list[Node] | None"]


def _builders() -> dict[str, Builder]:
    from divide.outline import code, data, div, markup, php

    return {"php": php.outline, "div": div.outline,
            "html": markup.html, "xml": markup.xml, "markdown": markup.markdown,
            "javascript": code.javascript, "css": code.css, "sql": code.sql, "shell": code.shell,
            "json": data.json, "yaml": data.yaml, "toml": data.toml, "ini": data.ini, "csv": data.csv}


def languages() -> frozenset[str]:
    """The languages (``editor.lang``) with an outline."""
    return frozenset(_builders())


def has_outline(lang: str | None) -> bool:
    return lang in _builders() if lang else False


def outline(lang: str | None, text: str, **context) -> list[Node] | None:
    """The outline of ``text`` in ``lang``; None when the language has none
    (or its grammar is missing). ``context`` passes what a builder can reuse
    (Div: the lexer's ``tokens`` and ``blocks``)."""
    builder = _builders().get(lang or "")
    return builder(text, **context) if builder is not None else None
