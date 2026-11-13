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
from divide.lang import divjson
from divide.lang.divjson import DivJsonError
from divide.lang.div.diagnostics import Diagnostic, check
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


JSON_EXTENSIONS = {".json", ".dialect"}


def is_div_file(path: Path) -> bool:
    return path.suffix.lower() in DIV_EXTENSIONS


def language_of(path: Path | None) -> str | None:
    """``"div"`` for templates (and untitled buffers), ``"json"`` for Div JSON data / dialects."""
    if path is None or is_div_file(path):
        return "div"
    if path.suffix.lower() in JSON_EXTENSIONS:
        return "json"
    return None


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


class _Mark:
    """A highlight span that is not a token (diagnostic overlay)."""

    __slots__ = ("start", "end", "kind")

    def __init__(self, start: int, end: int, kind: str) -> None:
        self.start, self.end, self.kind = start, end, kind


class DivEditor(TextArea):
    """Editor for one file: Div templates and Div JSON are highlighted (and JSON validated)."""

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
        self.lang = language_of(path)
        self.json_error: DivJsonError | None = None
        self.json_refs: list[str] = []
        self.diagnostics: list[Diagnostic] = []
        self.tokens: list = []  # lexer tokens of the template (Div only)
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

    @property
    def div_enabled(self) -> bool:
        return self.lang == "div"

    def set_path(self, path: Path | None) -> None:
        """The file changed name (Save as): pick the language again and re-highlight."""
        self.path = path
        self.lang = language_of(path)
        self._build_highlight_map()
        self.refresh()

    # Textual calls this after every edit and when the document is replaced.
    def _build_highlight_map(self) -> None:
        self._line_cache.clear()
        highlights = self._highlights
        highlights.clear()
        text = self.text
        if self.lang == "div":
            self._update_dialect(text)
            tokens = self.tokens = _LEXERS.get(self.dialect).tokenize(text)
            self._set_diagnostics(check(text, tokens, self.dialect, self.path, self.roots))
            # Overlays after the syntax colours: errors on red, warnings underlined.
            tokens = tokens + [_Mark(d.start, d.end, "diag." + d.severity) for d in self.diagnostics]
        elif self.lang == "json":
            tokens = divjson.tokenize(text)
            self._check_json(text, tokens)
        else:
            return
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

    def _set_diagnostics(self, diagnostics: list[Diagnostic]) -> None:
        if diagnostics != self.diagnostics:
            self.diagnostics = diagnostics
            if self.is_mounted:
                self.post_message(self.DiagnosticsChanged(self))

    def diagnostic_at(self, offset: int) -> Diagnostic | None:
        for d in self.diagnostics:
            if d.start <= offset < d.end or (d.start == offset):
                return d
        return None

    class DiagnosticsChanged(Message):
        def __init__(self, editor: "DivEditor") -> None:
            super().__init__()
            self.editor = editor

    def _check_json(self, text: str, tokens: list) -> None:
        error = None
        if text.strip():
            try:
                divjson.loads(text)
            except divjson.DivJsonError as exc:
                error = exc
        changed = (error and str(error)) != (self.json_error and str(self.json_error))
        self.json_error = error
        self.json_refs = [text[t.start + 1 : t.end] for t in tokens if t.kind == "json.ref"]
        if changed and self.is_mounted:
            self.post_message(self.JsonChecked(self))

    class JsonChecked(Message):
        """The JSON validity of the buffer changed."""

        def __init__(self, editor: "DivEditor") -> None:
            super().__init__()
            self.editor = editor

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
