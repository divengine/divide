"""Static checks of Div templates (UI-independent).

Works on the lexer's tokens plus the text, with the template's dialect, and
reports what Div would trip over or silently leave as text:

- blocks the lexer could not close (unclosed loops, orphan ``[/$x]``, an
  ``{ignore}`` without its end) and begin tags left as plain text because
  their end tag is missing (``<!--{``, ``{=``, ``{?(``, ``(#``, ``{% `` ...);
- ``{?( ... )?}`` / ``{/?}`` balance;
- ``{% path %}`` / ``{%% path %%}`` includes that do not exist;
- a broken ``@_DIALECT``;
- malformed JSON in ``{= name: {...} =}``.

Positions are code-point offsets into the text.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from pathlib import Path

from divide.lang import divjson
from divide.lang.div.dialect import Dialect
from divide.lang.div.lexer import Token

ERROR, WARNING = "error", "warning"

# Begin tag -> end tag pairs whose begin stays plain text when the end is missing.
# (name, begin key, end key)
_PAIRS = [
    ("comment", "DIV_TAG_COMMENT_BEGIN", "DIV_TAG_COMMENT_END"),
    ("template variable", "DIV_TAG_TPLVAR_BEGIN", "DIV_TAG_TPLVAR_END"),
    ("default replacement", "DIV_TAG_DEFAULT_REPLACEMENT_BEGIN", "DIV_TAG_DEFAULT_REPLACEMENT_END"),
    ("condition", "DIV_TAG_CONDITIONS_BEGIN_PREFIX", "DIV_TAG_CONDITIONS_BEGIN_SUFFIX"),
    ("formula", "DIV_TAG_FORMULA_BEGIN", "DIV_TAG_FORMULA_END"),
    ("number format", "DIV_TAG_NUMBER_FORMAT_PREFIX", "DIV_TAG_NUMBER_FORMAT_SUFFIX"),
    ("include", "DIV_TAG_INCLUDE_BEGIN", "DIV_TAG_INCLUDE_END"),
    ("preprocessed include", "DIV_TAG_PREPROCESSED_BEGIN", "DIV_TAG_PREPROCESSED_END"),
    ("iteration", "DIV_TAG_ITERATION_BEGIN_PREFIX", "DIV_TAG_ITERATION_BEGIN_SUFFIX"),
    ("location", "DIV_TAG_LOCATION_BEGIN", "DIV_TAG_LOCATION_END"),
    ("txt block", "DIV_TAG_TXT_BEGIN", "DIV_TAG_TXT_END"),
    ("strip block", "DIV_TAG_STRIP_BEGIN", "DIV_TAG_STRIP_END"),
    ("friendly tag", "DIV_TAG_FRIENDLY_BEGIN", "DIV_TAG_FRIENDLY_END"),
]

# Inside these, begin tags are not Div code (or are already explained). HTML
# comments are not here: Div ignores HTML, so its tags inside them still run.
_OPAQUE = {"div.comment", "div.doc", "div.ignored", "div.friendly", "div.string", "html.string", "div.error"}


@dataclass(frozen=True)
class Diagnostic:
    start: int
    end: int
    severity: str  # "error" | "warning"
    message: str


def _line_end(text: str, pos: int) -> int:
    eol = text.find("\n", pos)
    return len(text) if eol < 0 else eol


class _Checker:
    def __init__(self, text: str, tokens: list[Token], dialect: Dialect, template: Path | None, roots: list[Path]):
        self.text = text
        self.tokens = tokens
        self.T = dialect
        self.dialect = dialect
        self.template = template
        self.roots = roots
        self.out: list[Diagnostic] = []
        self.starts = {t.start for t in tokens if t.kind.startswith("div.")}
        self.opaque = sorted((t.start, t.end) for t in tokens if t.kind in _OPAQUE)
        self.opaque_starts = [s for s, _ in self.opaque]
        self._exists: dict[Path, bool] = {}

    def add(self, start: int, end: int, severity: str, message: str) -> None:
        self.out.append(Diagnostic(start, max(end, start + 1), severity, message))

    def _in_opaque(self, pos: int) -> bool:
        i = bisect.bisect_right(self.opaque_starts, pos) - 1
        return i >= 0 and pos < self.opaque[i][1]

    def run(self) -> list[Diagnostic]:
        self.lexer_errors()
        self.unclosed_pairs()
        self.condition_balance()
        self.includes()
        self.dialect_error()
        self.tplvar_json()
        self.out.sort(key=lambda d: (d.start, d.severity != ERROR))
        return self.out

    # ---------------------------------------------------------------- checks
    def lexer_errors(self) -> None:
        T, text = self.T, self.text
        loop_b, loop_e = T["DIV_TAG_LOOP_BEGIN_PREFIX"], T["DIV_TAG_LOOP_END_PREFIX"]
        loop_bs, loop_es = T["DIV_TAG_LOOP_BEGIN_SUFFIX"], T["DIV_TAG_LOOP_END_SUFFIX"]
        ignore_b, ignore_e = T["DIV_TAG_IGNORE_BEGIN"], T["DIV_TAG_IGNORE_END"]
        tokens = self.tokens
        for i, tok in enumerate(tokens):
            if tok.kind != "div.error":
                continue
            frag = text[tok.start : tok.end]
            if loop_e and frag.startswith(loop_e):
                key = frag[len(loop_e) : len(frag) - len(loop_es)] if loop_es else frag[len(loop_e) :]
                self.add(tok.start, tok.end, ERROR, f"{frag} closes a loop that was never opened ({loop_b}{key}{loop_bs})")
            elif loop_b and frag == loop_b:
                # [$ <var> ] : the variable and the suffix are the next tokens
                end = tok.end
                key = ""
                if i + 1 < len(tokens) and tokens[i + 1].start == tok.end:
                    key = text[tokens[i + 1].start : tokens[i + 1].end]
                    end = tokens[i + 1].end + len(loop_bs)
                opened = text[tok.start : end]
                self.add(tok.start, end, ERROR, f"loop {opened} is never closed with {loop_e}{key}{loop_es}")
            elif ignore_b and frag == ignore_b:
                self.add(tok.start, tok.end, ERROR, f"{ignore_b} is never closed with {ignore_e}")
            elif frag.strip() == loop_bs:
                continue  # suffix of an unclosed loop, already reported
            else:
                self.add(tok.start, tok.end, ERROR, f"Div syntax error at {frag!r}")

    def unclosed_pairs(self) -> None:
        text = self.text
        for name, bkey, ekey in _PAIRS:
            begin, end = self.T[bkey], self.T[ekey]
            if len(begin.strip()) < 2 or not end:
                continue
            single_line = bkey in ("DIV_TAG_INCLUDE_BEGIN", "DIV_TAG_PREPROCESSED_BEGIN", "DIV_TAG_ITERATION_BEGIN_PREFIX")
            pos = text.find(begin)
            while pos >= 0:
                if pos not in self.starts and not self._in_opaque(pos):
                    limit = _line_end(text, pos) if single_line else len(text)
                    if text.find(end, pos + len(begin), limit) < 0:
                        where = " on the same line" if single_line else ""
                        self.add(pos, pos + len(begin), ERROR, f"{name} {begin.strip()} has no closing {end.strip()}{where}")
                pos = text.find(begin, pos + len(begin))

    def condition_balance(self) -> None:
        text = self.text
        head, close = self.T["DIV_TAG_CONDITIONS_BEGIN_PREFIX"], self.T["DIV_TAG_CONDITIONS_END"]
        if not head or not close:
            return
        stack: list[Token] = []
        for tok in self.tokens:
            if tok.kind != "div.cond":
                continue
            frag = text[tok.start : tok.end]
            if frag == head:
                stack.append(tok)
            elif frag == close:
                if stack:
                    stack.pop()
                else:
                    self.add(tok.start, tok.end, ERROR, f"{close} closes a condition that was never opened")
        suffix = self.T["DIV_TAG_CONDITIONS_BEGIN_SUFFIX"]
        for tok in stack:
            eol = _line_end(text, tok.start)
            stop = text.find(suffix, tok.start, eol) if suffix else -1
            shown = text[tok.start : stop + len(suffix)] if stop >= 0 else text[tok.start : min(eol, tok.start + 40)].strip()
            self.add(tok.start, tok.end, ERROR, f"condition {shown} is never closed with {close}")

    def include_candidates(self, path: str) -> list[Path]:
        bases: list[Path] = []
        if self.template is not None:
            bases.append(self.template.parent)
        bases.extend(self.roots)
        bases.append(Path.cwd())
        ext = ".tpl"
        out: list[Path] = []
        for base in bases:
            p = base / path
            out.extend([p, p.with_name(p.name + ext)])
        return out

    def _is_file(self, path: Path) -> bool:
        if path not in self._exists:
            self._exists[path] = path.is_file()
        return self._exists[path]

    def includes(self) -> None:
        text = self.text
        sep = self.T["DIV_TAG_PREPROCESSED_SEPARATOR"]
        for tok in self.tokens:
            if tok.kind != "div.path":
                continue
            raw = text[tok.start : tok.end].strip()
            before = text[tok.start - 1 : tok.start] if tok.start else " "
            after = text[tok.end : tok.end + 1] or " "
            glued = not before.isspace() or not (after.isspace() or after == sep)
            if not raw or glued or any(c in raw for c in "{}$<>[]"):
                continue  # dynamic path ({$dir}/file, file{$n}): only Div knows
            path = raw.split(sep, 1)[0] if sep and sep in raw and not re.match(r"^[A-Za-z]:[\\/]", raw) else raw
            if Path(path).is_absolute():
                found = Path(path).exists() or Path(path + ".tpl").exists()
            else:
                found = any(self._is_file(c) for c in self.include_candidates(path))
            if not found:
                self.add(tok.start, tok.end, WARNING, f"include not found: {path}")

    def dialect_error(self) -> None:
        if not self.dialect.error:
            return
        m = re.search(r"@_DIALECT\b[^\n]*", self.text)
        start, end = (m.start(), m.end()) if m else (0, 1)
        self.add(start, end, ERROR, f"dialect: {self.dialect.error}")

    def tplvar_json(self) -> None:
        text = self.text
        begin, end_tag = self.T["DIV_TAG_TPLVAR_BEGIN"], self.T["DIV_TAG_TPLVAR_END"]
        op = self.T["DIV_TAG_TPLVAR_ASSIGN_OPERATOR"]
        tokens = self.tokens
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok.kind == "div.tplvar" and text[tok.start : tok.end] == begin:
                # find the operator after the variable name, and the end tag
                j, value_start, close = i + 1, None, None
                depth = 1
                while j < len(tokens):
                    t = tokens[j]
                    frag = text[t.start : t.end]
                    if t.kind == "div.tplvar":
                        if frag == begin:
                            depth += 1
                        elif frag == end_tag:
                            depth -= 1
                            if depth == 0:
                                close = t.start
                                break
                        elif frag.strip() == op and value_start is None:
                            value_start = t.end
                    j += 1
                if value_start is not None and close is not None:
                    self._check_json_value(value_start, close)
                i = j
            i += 1

    def _check_json_value(self, start: int, end: int) -> None:
        raw = self.text[start:end]
        value = raw.strip()
        if not value or value[0] not in "{[":
            return
        if any(t.kind == "json.error" for t in divjson.tokenize(value)):
            return  # not plain JSON (a Div expression or template); Div decides
        offset = start + (len(raw) - len(raw.lstrip()))
        try:
            divjson.loads(value)
        except divjson.DivJsonError as exc:
            at = offset + exc.offset
            self.add(at, min(at + 1, end), WARNING, f"JSON in template variable: {exc.message}")


def check(
    text: str,
    tokens: list[Token],
    dialect: Dialect,
    template: Path | None = None,
    roots: list[Path] | None = None,
) -> list[Diagnostic]:
    return _Checker(text, tokens, dialect, template, roots or []).run()


def line_col(text: str, offset: int) -> tuple[int, int]:
    """1-based line and column of ``offset``."""
    line = text.count("\n", 0, offset) + 1
    return line, offset - (text.rfind("\n", 0, offset) + 1) + 1
