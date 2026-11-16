"""Colours from tree-sitter for the other files of a PHP project: HTML, CSS,
JavaScript, Markdown, SQL, XML, YAML, TOML and shell scripts.

Each one is a tree-sitter grammar (the ``tree-sitter-<name>`` packages, the
same ones Textual's ``syntax`` extra installs) with the highlight query
Textual ships for its TextArea; the grammar's own query is the fallback when
Textual's does not fit the grammar installed. The query's capture names go
into divide's namespace (``@string`` -> ``@ts.string``), so the palettes
colour them by role (divide.themes.TOKENS), as they colour PHP and Div.

A grammar is loaded the first time a file of its language opens, and kept:
the editor and its queries point into it (a grammar freed under them would
crash tree-sitter).
"""

from __future__ import annotations

import importlib
import re
from functools import lru_cache
from pathlib import Path

PREFIX = "ts."  # highlight names: ts.string, ts.tag... (the theme styles them)
_CAPTURE = re.compile(r"[A-Za-z_][\w.\-]*")

# divide's language name -> the tree-sitter package's name and its loader
GRAMMARS: dict[str, tuple[str, str]] = {
    "html": ("html", "language"),
    "css": ("css", "language"),
    "javascript": ("javascript", "language"),
    "markdown": ("markdown", "language"),
    "sql": ("sql", "language"),
    "xml": ("xml", "language_xml"),
    "yaml": ("yaml", "language"),
    "toml": ("toml", "language"),
    "shell": ("bash", "language"),
}


def _textual_query(name: str) -> str | None:
    try:
        import textual
    except ImportError:
        return None
    path = Path(textual.__file__).parent / "tree-sitter" / "highlights" / f"{name}.scm"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def prefixed(query: str) -> str:
    """The query's captures in divide's namespace (its predicates name them too); quoted
    node names stay as they are (``"@media"`` is CSS's keyword, not a capture)."""
    out: list[str] = []
    i, n = 0, len(query)
    while i < n:
        ch = query[i]
        if ch == '"':  # a string, with its escapes
            j = i + 1
            while j < n and query[j] != '"':
                j += 2 if query[j] == "\\" else 1
            out.append(query[i:j + 1])
            i = j + 1
        elif ch == ";":  # a comment, to the end of the line
            j = query.find("\n", i)
            j = n if j < 0 else j
            out.append(query[i:j])
            i = j
        elif ch == "@" and (m := _CAPTURE.match(query, i + 1)):
            out.append("@" + PREFIX + m.group())
            i = m.end()
        else:
            out.append(ch)
            i += 1
    return "".join(out)


@lru_cache(maxsize=None)
def grammar(lang: str) -> tuple[object, str] | None:
    """``(tree-sitter Language, highlight query)`` for one of ``GRAMMARS``; None when its
    package is not installed or no query fits it."""
    if lang not in GRAMMARS:
        return None
    package, loader = GRAMMARS[lang]
    try:
        from tree_sitter import Language, Query

        module = importlib.import_module(f"tree_sitter_{package}")
        language = Language(getattr(module, loader)())
    except (ImportError, AttributeError, OSError, ValueError):
        return None
    for query in (_textual_query(package), getattr(module, "HIGHLIGHTS_QUERY", None)):
        if not query:
            continue
        try:
            Query(language, query)
        except Exception:  # noqa: BLE001 - a query written for another version of the grammar
            continue
        return language, prefixed(query)
    return None
