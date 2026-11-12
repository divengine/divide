"""A TextArea that highlights Div templates with the divide lexer.

Textual's TextArea highlights through tree-sitter queries. Div has no
tree-sitter grammar (and its dialects change the tags at runtime), so we
replace the highlight map builder with the dialect-aware lexer. The map
format is Textual's: ``{line: [(start_byte, end_byte | None, name)]}``.
"""

from __future__ import annotations

import bisect
import dataclasses
from pathlib import Path

from rich.style import Style
from textual._text_area_theme import TextAreaTheme
from textual.message import Message
from textual.widgets import TextArea

from divide.lang.div.dialect import DEFAULT_DIALECT, Dialect, resolve_dialect, template_properties
from divide.lang.div.lexer import Lexer

from .theme import CGA, DIV_STYLES, TURBO_STYLES

DIV_EXTENSIONS = {".tpl", ".div"}


def divide_theme() -> TextAreaTheme:
    """Dark, Monokai-based theme."""
    base = TextAreaTheme.get_builtin_theme("monokai")
    assert base is not None
    return dataclasses.replace(base, name="divide", syntax_styles={**base.syntax_styles, **DIV_STYLES})


def turbo_theme() -> TextAreaTheme:
    """Yellow on blue, like the Borland editors (selection: blue on light gray)."""
    return TextAreaTheme(
        name="turbo",
        base_style=Style(color=CGA["yellow"], bgcolor=CGA["blue"]),
        gutter_style=Style(color=CGA["cyan"], bgcolor=CGA["blue"]),
        cursor_style=Style(color=CGA["blue"], bgcolor=CGA["yellow"]),
        cursor_line_gutter_style=Style(color=CGA["yellow"], bgcolor=CGA["blue"]),
        bracket_matching_style=Style(color=CGA["white"], bgcolor=CGA["cyan"], bold=True),
        selection_style=Style(color=CGA["blue"], bgcolor=CGA["lightgray"]),
        syntax_styles=dict(TURBO_STYLES),
    )


EDITOR_THEMES = {"turbo": turbo_theme, "divide": divide_theme}


def is_div_file(path: Path) -> bool:
    return path.suffix.lower() in DIV_EXTENSIONS


class _LexerCache:
    """One Lexer per dialect file (keyed by path + mtime)."""

    def __init__(self) -> None:
        self._lexers: dict[object, Lexer] = {}

    def get(self, dialect: Dialect) -> Lexer:
        key: object = "default"
        if dialect.source is not None:
            try:
                key = (str(dialect.source), dialect.source.stat().st_mtime_ns)
            except OSError:
                key = str(dialect.source)
        elif dialect is not DEFAULT_DIALECT:
            key = ("broken", dialect.name)
        lexer = self._lexers.get(key)
        if lexer is None:
            lexer = self._lexers[key] = Lexer(dialect)
        return lexer


_LEXERS = _LexerCache()


class DivEditor(TextArea):
    """Editor for one file. Div highlighting is on for Div templates."""

    class DialectChanged(Message):
        def __init__(self, editor: "DivEditor", dialect: Dialect) -> None:
            super().__init__()
            self.editor = editor
            self.dialect = dialect

    def __init__(
        self,
        text: str = "",
        *,
        path: Path | None = None,
        roots: list[Path] | None = None,
        editor_theme: str = "turbo",
        **kwargs,
    ) -> None:
        self.path = path
        self.roots = roots or []
        self.div_enabled = path is None or is_div_file(path)
        self.dialect: Dialect = DEFAULT_DIALECT
        self._dialect_ref: str | None = None
        super().__init__(
            text,
            soft_wrap=False,
            tab_behavior="indent",
            show_line_numbers=True,
            **kwargs,
        )
        for factory in EDITOR_THEMES.values():
            self.register_theme(factory())
        self.theme = editor_theme

    # Textual calls this after every edit and when the document is replaced.
    def _build_highlight_map(self) -> None:
        self._line_cache.clear()
        highlights = self._highlights
        highlights.clear()
        if not self.div_enabled:
            return
        text = self.text
        self._update_dialect(text)
        tokens = _LEXERS.get(self.dialect).tokenize(text)
        if not tokens:
            return
        lines = self.document.lines
        starts = [0]
        for line in lines[:-1]:
            starts.append(starts[-1] + len(line) + 1)

        def to_byte(row: int, col: int) -> int:
            line = lines[row]
            return col if line.isascii() else len(line[:col].encode("utf-8"))

        for tok in tokens:
            row = bisect.bisect_right(starts, tok.start) - 1
            start, end = tok.start, tok.end
            while start < end and row < len(lines):
                line_start = starts[row]
                line_end = line_start + len(lines[row])
                col = start - line_start
                if end <= line_end:
                    highlights[row].append((to_byte(row, col), to_byte(row, end - line_start), tok.kind))
                    break
                highlights[row].append((to_byte(row, col), None, tok.kind))
                row += 1
                start = line_end + 1

    def _update_dialect(self, text: str) -> None:
        prop = template_properties(text).get("DIALECT")
        ref = prop[0] if prop else None
        if ref == self._dialect_ref and (ref is None or self.dialect.error is None):
            return
        self._dialect_ref = ref
        new = resolve_dialect(text, self.path, self.roots) if ref else DEFAULT_DIALECT
        changed = new.name != self.dialect.name or new.error != self.dialect.error
        self.dialect = new
        if changed and self.is_mounted:
            self.post_message(self.DialectChanged(self, new))
