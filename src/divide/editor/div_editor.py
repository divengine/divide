"""The editor: Div templates, Div JSON and PHP.

Textual's TextArea highlights through tree-sitter queries. Div has no
tree-sitter grammar (and its dialects change the tags at runtime), so for
templates and JSON the highlight map builder is replaced by divide's lexers.
PHP keeps Textual's own builder, with tree-sitter's PHP grammar. The map
format is Textual's: ``{line: [(start_byte, end_byte | None, name)]}``;
diagnostics are drawn over it.
"""

from __future__ import annotations

import bisect
from pathlib import Path

from rich.style import Style
from textual.message import Message
from textual.widgets import TextArea

from divide.lang.div.dialect import DEFAULT_DIALECT, Dialect, resolve_dialect, template_properties
from divide.lang import divjson
from divide.lang.divjson import DivJsonError
from divide.lang.div.diagnostics import Diagnostic, check, include_paths
from divide.lang.div.lexer import Lexer
from divide import lang as languages
from divide.lang import php, plain, treesitter

from divide import themes

from . import theme as editor_themes

DIV_EXTENSIONS = set(languages.DIV.extensions)




JSON_EXTENSIONS = set(languages.JSON.extensions)
language_of = languages.language_of


def is_div_file(path: Path) -> bool:
    return path.suffix.lower() in DIV_EXTENSIONS


class _LexerCache:
    """One Lexer per dialect, keyed by its tags. Least recently used go first."""

    LIMIT = 32

    def __init__(self) -> None:
        self._lexers: dict[object, Lexer] = {}

    def get(self, dialect: Dialect) -> Lexer:
        # By the tags themselves: the same file may be read by Div or guessed by divide.
        key: object = "default" if dialect is DEFAULT_DIALECT else ("tags", frozenset(dialect.tags.items()))
        lexer = self._lexers.pop(key, None)
        if lexer is None:
            lexer = Lexer(dialect)
            while len(self._lexers) >= self.LIMIT:
                self._lexers.pop(next(iter(self._lexers)))
        self._lexers[key] = lexer
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
        kind: str = editor_themes.EDITOR,  # or OUTPUT: the colours of the Output window
        **kwargs,
    ) -> None:
        self.path = path
        self.roots = roots or []
        self.lang = language_of(path)
        self.json_error: DivJsonError | None = None
        self.json_refs: list[str] = []
        self.diagnostics: list[Diagnostic] = []
        self.tokens: list = []  # lexer tokens of the template (Div only)
        self.blocks: list = []  # its constructs (Lexer.blocks), for the outline
        self._blocks_text: str | None = None
        self.include_targets: dict = {}  # include path -> IncludeTarget, as Div resolved it
        self.include_set: frozenset[str] = frozenset()  # literal include paths in the text
        self.forced_dialect: Dialect | None = None  # a dialect given from outside (the dialector's preview)
        self.marks: list[tuple[int, int, str]] = []  # extra highlights: (start, end, style name)
        self.dialect: Dialect = DEFAULT_DIALECT
        self._dialect_ref: str | None = None
        self.engine_dialects: dict[str, Dialect] = {}  # @_DIALECT value -> the dialect as Div loads it
        self._guess: tuple[str, Dialect] | None = None
        self._text_cache: str | None = None  # PHP: the text last sent to be checked
        self.lint_diagnostics: list[Diagnostic] = []  # from php -l
        self.server_diagnostics: list = []  # from the language server
        super().__init__(
            text,
            soft_wrap=False,
            tab_behavior="indent",
            show_line_numbers=True,
            **kwargs,
        )
        self.kind = kind
        for theme in editor_themes.all_themes():
            self.register_theme(theme)
        self.apply_palette()
        self._set_language()

    def _set_language(self) -> None:
        """PHP and the other files of a project (HTML, YAML...) are parsed by tree-sitter
        (Textual's own highlighting); Div, Div JSON, INI and CSV by divide's lexers."""
        found = php.grammar() if self.lang == "php" else treesitter.grammar(self.lang) if self.lang else None
        if found is not None:
            name = self.lang if self.lang == "php" else "divide-" + self.lang  # not Textual's builtin names
            if name not in self._languages:
                self.register_language(name, *found)
            if self.language != name:
                self.language = name
        elif self.language is not None:
            self.language = None

    @property
    def tree_sitter(self) -> bool:
        """Coloured by a tree-sitter grammar (PHP, HTML, YAML...)."""
        return self.language is not None

    def on_mount(self) -> None:
        self.app.theme_changed_signal.subscribe(self, lambda _theme: self.apply_palette())
        if self.lang == "php":
            self.post_message(self.CheckRequested(self))

    def div_blocks(self) -> list:
        """The constructs of the template as it is now (lexed again if the colours lag behind)."""
        if self._blocks_text != self.text:
            self._update_dialect(self.text)
            lexer = _LEXERS.get(self.dialect)
            lexer.tokenize(self.text)
            self.blocks, self._blocks_text = lexer.blocks, self.text
        return self.blocks

    def apply_palette(self) -> None:
        """The colours of the current palette (Options > Colors)."""
        self.theme = editor_themes.theme_name(themes.current(), self.kind)

    @property
    def checked(self) -> bool:
        """Its errors are listed in the Messages window (Div, PHP)."""
        info = languages.language(self.lang)
        return bool(info and info.checked)

    def set_lint(self, diagnostics: list[Diagnostic]) -> None:
        """The errors a checker outside the editor found (PHP's ``php -l``)."""
        self.lint_diagnostics = list(diagnostics)
        self._merge_outside_diagnostics()

    def set_server_diagnostics(self, diagnostics: list) -> None:
        """What the language server says about the text (``divide.lsp``)."""
        self.server_diagnostics = list(diagnostics)
        self._merge_outside_diagnostics()

    def _merge_outside_diagnostics(self) -> None:
        # The language's own checker first; the server adds what is not on the same line.
        merged = list(self.lint_diagnostics)
        lines = {self.text.count("\n", 0, d.start) for d in merged}
        for d in self.server_diagnostics:
            if d.end > len(self.text):
                continue
            if d.severity == "error" and self.text.count("\n", 0, d.start) in lines:
                continue
            merged.append(Diagnostic(d.start, d.end, d.severity, " ".join(d.message.split())))
        merged.sort(key=lambda d: (d.start, d.end))
        if merged != self.diagnostics:
            self._set_diagnostics(merged)
            self._build_highlight_map()
            self.refresh()

    class CheckRequested(Message):
        """The text changed: a checker outside the editor (php -l) should look again."""

        def __init__(self, editor: "DivEditor") -> None:
            super().__init__()
            self.editor = editor

    @property
    def div_enabled(self) -> bool:
        return self.lang == "div"

    def set_path(self, path: Path | None) -> None:
        """The file changed name (Save as): pick the language again and re-highlight."""
        self.path = path
        lang = language_of(path)
        if lang != self.lang:
            self.lang = lang
            self.diagnostics = []
            self.lint_diagnostics, self.server_diagnostics = [], []
            self._set_language()
            if lang == "php" and self.is_mounted:
                self.post_message(self.CheckRequested(self))
        self._build_highlight_map()
        self.refresh()

    # Textual calls this after every edit and when the document is replaced.
    def _build_highlight_map(self) -> None:
        if self.lang == "php":
            super()._build_highlight_map()  # tree-sitter's colours
            if self._text_cache != self.text:
                self._text_cache = self.text
                if self.is_mounted:
                    self.post_message(self.CheckRequested(self))
            self._overlay([_Mark(d.start, d.end, "diag." + d.severity) for d in self.diagnostics])
            return
        self._line_cache.clear()
        highlights = self._highlights
        highlights.clear()
        text = self.text
        if self.lang == "div":
            self._update_dialect(text)
            lexer = _LEXERS.get(self.dialect)
            tokens = self.tokens = lexer.tokenize(text)
            self.blocks, self._blocks_text = lexer.blocks, text
            includes = frozenset(raw for _, _, raw in include_paths(text, tokens, self.dialect))
            if includes != self.include_set:
                self.include_set = includes
                if self.is_mounted:
                    self.post_message(self.IncludesChanged(self))
            self._set_diagnostics(check(text, tokens, self.dialect, self.include_targets))
            # Overlays after the syntax colours: errors on red, warnings underlined.
            tokens = tokens + [_Mark(d.start, d.end, "diag." + d.severity) for d in self.diagnostics]
            tokens += [_Mark(start, end, kind) for start, end, kind in self.marks if end > start]
        elif self.lang == "json":
            tokens = divjson.tokenize(text)
            self._check_json(text, tokens)
        elif self.lang == "ini":
            tokens = plain.ini_tokens(text)
        elif self.lang == "csv":
            tsv = self.path is not None and self.path.suffix.lower() == ".tsv"
            tokens = plain.csv_tokens(text, plain.csv_separator(text, tsv))
        elif self.tree_sitter:
            super()._build_highlight_map()  # tree-sitter's colours (HTML, YAML...)
            return
        else:
            return
        self._overlay(tokens)

    def _overlay(self, tokens: list) -> None:
        """Add spans (by text offset) to the highlight map."""
        if not tokens:
            return
        highlights = self._highlights
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

    def set_include_targets(self, targets: dict) -> None:
        """Div's answers for the includes (from the app); re-checks when they change."""
        if targets != self.include_targets:
            self.include_targets = targets
            if self.lang == "div":
                self._build_highlight_map()
                self.refresh()

    class IncludesChanged(Message):
        """The literal include paths of the template changed: ask Div about them."""

        def __init__(self, editor: "DivEditor") -> None:
            super().__init__()
            self.editor = editor

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

    def set_marks(self, marks: list[tuple[int, int, str]]) -> None:
        if marks != self.marks:
            self.marks = marks
            self._build_highlight_map()
            self.refresh()

    def _update_dialect(self, text: str) -> None:
        """The template's dialect: Div's answer for its ``@_DIALECT`` when the app has
        one (``set_engine_dialect``), else a quick guess that only colours (no errors)."""
        if self.forced_dialect is not None:
            self.dialect = self.forced_dialect
            return
        prop = template_properties(text).get("DIALECT")
        ref = prop[0].strip() if prop and prop[0].strip() else None
        if ref != self._dialect_ref:
            self._dialect_ref = ref
            if ref is not None and self.is_mounted:
                self.post_message(self.DialectRefChanged(self))
        if ref is None:
            new = DEFAULT_DIALECT
        elif ref in self.engine_dialects:
            new = self.engine_dialects[ref]
        else:
            new = self._guess_dialect(ref, text)
        changed = new is not self.dialect and (new.name, new.error, new.tags) != (self.dialect.name, self.dialect.error, self.dialect.tags)
        self.dialect = new
        if changed and self.is_mounted:
            self.post_message(self.DialectChanged(self, new))

    def _guess_dialect(self, ref: str, text: str) -> Dialect:
        """Until Div answers (or without Div): look for the file in Python, to colour."""
        if self._guess is not None and self._guess[0] == ref:
            return self._guess[1]
        guess = resolve_dialect(text, self.path, self.roots)
        if guess.error is not None:
            guess = Dialect(name=ref)  # Div's defaults; whether the file is fine is Div's to say
        self._guess = (ref, guess)
        return guess

    def set_engine_dialect(self, ref: str, dialect: Dialect) -> None:
        """Div's answer for ``@_DIALECT = ref`` (from the app); re-highlights."""
        if self.engine_dialects.get(ref) == dialect:
            return
        self.engine_dialects[ref] = dialect
        if ref == self._dialect_ref:
            self._build_highlight_map()
            self.refresh()

    class DialectRefChanged(Message):
        """The template's ``@_DIALECT`` value changed: ask Div which dialect it is."""

        def __init__(self, editor: "DivEditor") -> None:
            super().__init__()
            self.editor = editor
