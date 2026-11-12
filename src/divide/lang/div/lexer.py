"""Dialect-aware lexer for Div templates.

Div is not parsed top-down by the engine (it rewrites the whole template
until a fixed point), so an editor cannot fully "evaluate" a template. This
lexer instead recognises every tag form documented for Div 6.x and built
from the active dialect, mirroring the engine's matching rules where they
matter for an editor:

* keyed blocks (lists, capsules, conditional parts, locations, sub-parsers,
  multi replacements) are only recognised when their closing tag exists,
  with balanced nesting, as ``div::getRanges`` does;
* blocks whose begin suffix is empty (``?$var``, ``[[var``, ``{{var``) take
  the longest key that has a matching closing tag, which is how the engine
  resolves ``?$showYES@else@NO$show?`` with a known ``show`` variable;
* containers whose content is code (``{= =}``, ``{@ @}``, ``(# #)``,
  ``{?( )?}``, ``<? ?>``, includes, iterations) are lexed recursively, so
  replacements nested inside them are highlighted too.

Plain text between Div tags is lexed as light HTML, because most templates
generate HTML; the state of an HTML tag/string survives across Div tags so
``<option value="{$val}">`` colours correctly.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from typing import Callable

from .dialect import DEFAULT_DIALECT, SCOPE_VARS, SYSTEM_VAR_PREFIX, Dialect


@dataclass(frozen=True, slots=True)
class Token:
    start: int
    end: int
    kind: str


# Token kinds (also the names used by editor themes).
DELIM = "div.delim"
LOOP = "div.loop"
COND = "div.cond"
CAPSULE = "div.capsule"
LOCATION = "div.location"
SUBPARSER = "div.subparser"
MULTIREP = "div.multirep"
INCLUDE = "div.include"
TPLVAR = "div.tplvar"
REPLACE = "div.replace"
MODIFIER = "div.modifier"
VAR = "div.var"
VAR_BUILTIN = "div.var.builtin"
VAR_DEF = "div.var.def"
FORMAT = "div.format"
KEYWORD = "div.keyword"
SPECIAL = "div.special"
COMMENT = "div.comment"
DOC = "div.doc"
IGNORED = "div.ignored"
MACRO = "div.macro"
FRIENDLY = "div.friendly"
PROPERTY = "div.property"
PROPERTY_VALUE = "div.property.value"
PATH = "div.path"
STRING = "div.string"
NUMBER = "div.number"
CONSTANT = "div.constant"
OPERATOR = "div.operator"
FUNCTION = "div.function"
PUNCT = "div.punct"
KEY = "div.key"
ERROR = "div.error"
HTML_TAG = "html.tag"
HTML_ATTR = "html.attr"
HTML_STRING = "html.string"
HTML_COMMENT = "html.comment"
HTML_ENTITY = "html.entity"

MODIFIER_KEYS = (
    "DIV_TAG_MODIFIER_SIMPLE",
    "DIV_TAG_MODIFIER_CAPITALIZE_FIRST",
    "DIV_TAG_MODIFIER_CAPITALIZE_WORDS",
    "DIV_TAG_MODIFIER_UPPERCASE",
    "DIV_TAG_MODIFIER_LOWERCASE",
    "DIV_TAG_MODIFIER_LENGTH",
    "DIV_TAG_MODIFIER_COUNT_WORDS",
    "DIV_TAG_MODIFIER_COUNT_SENTENCES",
    "DIV_TAG_MODIFIER_COUNT_PARAGRAPHS",
    "DIV_TAG_MODIFIER_ENCODE_URL",
    "DIV_TAG_MODIFIER_ENCODE_RAW_URL",
    "DIV_TAG_MODIFIER_ENCODE_JSON",
    "DIV_TAG_MODIFIER_HTML_ENTITIES",
    "DIV_TAG_MODIFIER_NL2BR",
    "DIV_TAG_MODIFIER_SINGLE_QUOTES",
    "DIV_TAG_MODIFIER_JS",
)
SPECIAL_KEYS = (
    "DIV_TAG_SPECIAL_REPLACE_NEW_LINE",
    "DIV_TAG_SPECIAL_REPLACE_CAR_RETURN",
    "DIV_TAG_SPECIAL_REPLACE_HORIZONTAL_TAB",
    "DIV_TAG_SPECIAL_REPLACE_VERTICAL_TAB",
    "DIV_TAG_SPECIAL_REPLACE_NEXT_PAGE",
    "DIV_TAG_SPECIAL_REPLACE_DOLLAR_SYMBOL",
    "DIV_TAG_SPECIAL_REPLACE_SPACE",
)
AGGREGATE_KEYS = (
    "DIV_TAG_AGGREGATE_FUNCTION_COUNT",
    "DIV_TAG_AGGREGATE_FUNCTION_MAX",
    "DIV_TAG_AGGREGATE_FUNCTION_MIN",
    "DIV_TAG_AGGREGATE_FUNCTION_SUM",
    "DIV_TAG_AGGREGATE_FUNCTION_AVG",
)

# Mode names for the text between Div tags.
TEXT, VALUE, EXPR, PATHM, ITER, VARM, STRM = "text", "value", "expr", "path", "iter", "var", "string"

_EXPR_RE = re.compile(
    r"""(?P<str>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')
      |(?P<num>\b\d+(?:\.\d+)?\b)
      |(?P<const>\b(?:true|false|null|TRUE|FALSE|NULL)\b)
      |(?P<kw>\b(?:and|or|xor|not|foreach|as|if|else|elseif|for|while|echo|return|array|new|isset|empty)\b)
      |(?P<fn>\b[A-Za-z_]\w*(?=\s*\())
      |(?P<var>\$[A-Za-z_]\w*)
      |(?P<cmt>//[^\n]*|\#[^\n]*|/\*[\s\S]*?\*/)
      |(?P<op>===|!==|==|!=|<=|>=|&&|\|\||->|=>|\+\+|--|[-+*/%<>=!?:.])""",
    re.X,
)
_VALUE_RE = re.compile(
    r"""(?P<str>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
      |(?P<call>->\s*[A-Za-z_][\w.]*)
      |(?P<ref>\$[A-Za-z_][\w.\-]*)
      |(?P<key>\b[A-Za-z_][\w\-]*(?=\s*:))
      |(?P<const>\b(?:true|false|null)\b)
      |(?P<num>-?\b\d+(?:\.\d+)?(?:[eE][-+]?\d+)?\b)
      |(?P<punct>[\[\]{}(),:])""",
    re.X,
)
_ITER_RE = re.compile(r"(?P<num>-?\d+)|(?P<var>[A-Za-z_]\w*)|(?P<punct>[,])")
_HTML_TAG_START = re.compile(r"<!--[\s\S]*?(?:-->|$)|</?[A-Za-z][\w:.\-]*|&#?\w+;")
_HTML_IN_TAG = re.compile(r"""(?P<end>/?>)|(?P<q>["'])|(?P<attr>[A-Za-z_:@\-][\w:.\-@]*)|(?P<eq>=)""")


class Lexer:
    def __init__(self, dialect: Dialect | None = None, html: bool = True) -> None:
        self.d = dialect or DEFAULT_DIALECT
        self.html = html
        self._build()

    # ------------------------------------------------------------------ setup
    def _build(self) -> None:
        T = self.d.tags
        self.T = T
        delim = re.escape(T["DIV_TAG_VAR_MEMBER_DELIMITER"] or ".")
        self.var_re = rf"[\w\-]+(?:{delim}[\w\-]+)*"
        self.key_re = re.compile(rf"(?:[\w\-]|{delim})+")
        # A var that may embed a nested replacement: [${$object}]
        nested = rf"(?:[\w\-]|{delim}|\{{[^{{}}\n]*\}})+"
        self.nested_var_re = nested

        mods = sorted({T[k] for k in MODIFIER_KEYS if T.get(k)}, key=len, reverse=True)
        mod_alt = "|".join(map(re.escape, mods))
        pre, suf = re.escape(T["DIV_TAG_REPLACEMENT_PREFIX"]), re.escape(T["DIV_TAG_REPLACEMENT_SUFFIX"])
        sub = re.escape(T["DIV_TAG_SUBMATCH_SEPARATOR"])
        suf_first = re.escape(T["DIV_TAG_REPLACEMENT_SUFFIX"][:1] or "}")
        self.rep_re = re.compile(
            rf"{pre}(?P<mod>{mod_alt})(?P<var>{nested})(?:(?P<sep>{sub})(?P<sub>[^\n{suf_first}]*?))?{suf}"
        )
        self.custom_rep_re = re.compile(
            rf"{pre}(?P<mod>[A-Za-z]\w*{sub})(?P<var>{self.var_re})(?:(?P<sep>{sub})(?P<sub>[^\n{suf_first}]*?))?{suf}"
        )
        mm_pre = re.escape(T["DIV_TAG_MULTI_MODIFIERS_PREFIX"])
        mm_sep = re.escape(T["DIV_TAG_MULTI_MODIFIERS_SEPARATOR"])
        mm_suf = re.escape(T["DIV_TAG_MULTI_MODIFIERS_SUFFIX"])
        self.multi_re = re.compile(rf"{mm_pre}(?P<var>{nested})(?P<mods>(?:{mm_sep}[^\n{{}}]*?)+){mm_suf}")
        self.aggregates = {T[k] for k in AGGREGATE_KEYS if T.get(k)}

        def fmt_re(p: str, s: str, sep: str) -> re.Pattern:
            return re.compile(
                rf"{re.escape(T[p])}(?P<var>{nested}){re.escape(T[sep])}(?P<fmt>[^\n]*?){re.escape(T[s])}"
            )

        self.date_re = fmt_re("DIV_TAG_DATE_FORMAT_PREFIX", "DIV_TAG_DATE_FORMAT_SUFFIX", "DIV_TAG_DATE_FORMAT_SEPARATOR")
        self.number_re = fmt_re("DIV_TAG_NUMBER_FORMAT_PREFIX", "DIV_TAG_NUMBER_FORMAT_SUFFIX", "DIV_TAG_NUMBER_FORMAT_SEPARATOR")
        self.tplvar_head = re.compile(
            rf"\s*(?P<prot>{re.escape(T['DIV_TAG_TPLVAR_PROTECTOR'])})?\s*(?P<name>{self.var_re})\s*(?P<op>{re.escape(T['DIV_TAG_TPLVAR_ASSIGN_OPERATOR'])})"
        )
        self.loop_item = re.compile(rf"[ \t]*(?P<item>[A-Za-z_]\w*)[ \t]*(?P<op>{re.escape(T['DIV_TAG_LOOP_VAR_SEPARATOR'])})")
        self.txt_width = re.compile(rf"[ \t]*(?P<w>\d+)[ \t]*(?P<op>{re.escape(T['DIV_TAG_TXT_WIDTH_SEPARATOR'])})")
        self.subparser_name = re.compile(r"(?P<name>[A-Za-z_][\w\-]*)(?::(?P<event>[A-Za-z_]\w*))?")
        self.location_re = re.compile(
            rf"{re.escape(T['DIV_TAG_LOCATION_BEGIN'])}(?P<name>{self.var_re}){re.escape(T['DIV_TAG_LOCATION_END'])}"
        )
        self.formula_fmt = re.compile(
            rf"{re.escape(T['DIV_TAG_FORMULA_FORMAT_SEPARATOR'])}\s*\d[^\s{re.escape(T['DIV_TAG_FORMULA_FORMAT_SEPARATOR'])}]*\s*$"
        )
        self._doc_re = re.compile(r"(?:^|(?<=\n)|(?<=" + re.escape(T["DIV_TAG_COMMENT_BEGIN"][-1:] or "{") + r"))[ \t]*(@[A-Za-z_]\w*:?)")
        self.property_re = re.compile(r"@_(?P<name>[A-Za-z_]\w*)(?P<sp>[ \t]*=[ \t]*)(?P<val>[^\n]*)")

        rules: list[tuple[str, Callable[[int, int, str], int | None]]] = [
            (T["DIV_TAG_COMMENT_BEGIN"], self._r_comment),
            (T["DIV_TAG_IGNORE_BEGIN"], self._r_ignore),
            (T["DIV_TAG_FRIENDLY_BEGIN"], self._r_lit(FRIENDLY)),
            (T["DIV_TAG_FRIENDLY_END"], self._r_lit(FRIENDLY)),
            (T["DIV_TAG_TEASER_BREAK"], self._r_lit(KEYWORD)),
            (T["DIV_TAG_MACRO_BEGIN"], self._r_macro),
            *[(T[k], self._r_lit(SPECIAL)) for k in SPECIAL_KEYS],
            (T["DIV_TAG_TPLVAR_BEGIN"], self._r_tplvar),
            (T["DIV_TAG_DEFAULT_REPLACEMENT_BEGIN"], self._r_default),
            (T["DIV_TAG_PREPROCESSED_BEGIN"], self._r_include(T["DIV_TAG_PREPROCESSED_BEGIN"], T["DIV_TAG_PREPROCESSED_END"])),
            (T["DIV_TAG_INCLUDE_BEGIN"], self._r_include(T["DIV_TAG_INCLUDE_BEGIN"], T["DIV_TAG_INCLUDE_END"])),
            (T["DIV_TAG_CONDITIONS_BEGIN_PREFIX"], self._r_conditions),
            (T["DIV_TAG_CONDITIONS_END"], self._r_lit(COND)),
            (T["DIV_TAG_FORMULA_BEGIN"], self._r_formula),
            (T["DIV_TAG_STRIP_BEGIN"], self._r_lit(KEYWORD)),
            (T["DIV_TAG_STRIP_END"], self._r_lit(KEYWORD)),
            (T["DIV_TAG_TXT_BEGIN"], self._r_txt),
            (T["DIV_TAG_TXT_END"], self._r_lit(KEYWORD)),
            (T["DIV_TAG_DATE_FORMAT_PREFIX"], self._r_format(self.date_re)),
            (T["DIV_TAG_NUMBER_FORMAT_PREFIX"], self._r_format(self.number_re)),
            (T["DIV_TAG_MULTI_REPLACEMENT_BEGIN_PREFIX"], self._r_multirep),
            (T["DIV_TAG_MULTI_MODIFIERS_PREFIX"], self._r_multi),
            (T["DIV_TAG_REPLACEMENT_PREFIX"], self._r_replacement),
            (T["DIV_TAG_SUBPARSER_BEGIN_PREFIX"], self._r_subparser),
            (T["DIV_TAG_LOOP_END_PREFIX"], self._r_orphan_end),
            (T["DIV_TAG_LOOP_BEGIN_PREFIX"], self._r_loop),
            (T["DIV_TAG_ITERATION_BEGIN_PREFIX"], self._r_iteration),
            (T["DIV_TAG_ITERATION_END"], self._r_lit(LOOP)),
            (T["DIV_TAG_EMPTY"], self._r_lit(KEYWORD)),
            (T["DIV_TAG_BREAK"], self._r_lit(KEYWORD)),
            (T["DIV_TAG_ELSE"], self._r_lit(KEYWORD)),
            (T["DIV_TAG_CAPSULE_BEGIN_PREFIX"], self._r_keyed(
                "DIV_TAG_CAPSULE_BEGIN_PREFIX", "DIV_TAG_CAPSULE_BEGIN_SUFFIX",
                "DIV_TAG_CAPSULE_END_PREFIX", "DIV_TAG_CAPSULE_END_SUFFIX", CAPSULE)),
            (T["DIV_TAG_LOCATION_BEGIN"], self._r_location),
            (T["DIV_TAG_LOCATION_CONTENT_BEGIN_PREFIX"], self._r_keyed(
                "DIV_TAG_LOCATION_CONTENT_BEGIN_PREFIX", "DIV_TAG_LOCATION_CONTENT_BEGIN_SUFFIX",
                "DIV_TAG_LOCATION_CONTENT_END_PREFIX", "DIV_TAG_LOCATION_CONTENT_END_SUFFIX", LOCATION)),
            (T["DIV_TAG_CONDITIONAL_TRUE_BEGIN_PREFIX"], self._r_keyed(
                "DIV_TAG_CONDITIONAL_TRUE_BEGIN_PREFIX", "DIV_TAG_CONDITIONAL_TRUE_BEGIN_SUFFIX",
                "DIV_TAG_CONDITIONAL_TRUE_END_PREFIX", "DIV_TAG_CONDITIONAL_TRUE_END_SUFFIX", COND)),
            (T["DIV_TAG_CONDITIONAL_FALSE_BEGIN_PREFIX"], self._r_keyed(
                "DIV_TAG_CONDITIONAL_FALSE_BEGIN_PREFIX", "DIV_TAG_CONDITIONAL_FALSE_BEGIN_SUFFIX",
                "DIV_TAG_CONDITIONAL_FALSE_END_PREFIX", "DIV_TAG_CONDITIONAL_FALSE_END_SUFFIX", COND)),
            ("@_", self._r_property),
            ('"', self._r_string),
            ("'", self._r_string),
        ]
        # Drop rules whose start tag is empty in this dialect; group by tag.
        self.rules: dict[str, list[Callable]] = {}
        for lit, fn in rules:
            if lit:
                self.rules.setdefault(lit, []).append(fn)
        self.lits = sorted(self.rules, key=len, reverse=True)
        self.cand_re = re.compile("|".join(map(re.escape, self.lits)))

    # --------------------------------------------------------------- driver
    def tokenize(self, text: str) -> list[Token]:
        self.text = text
        self.out: list[Token] = []
        self.pending: dict[int, list[tuple[int, str]]] = {}
        self.pending_pos: list[int] = []
        self.html_state: str | None = None  # None | "tag" | quote char
        self._scan(0, len(text), TEXT)
        self.out.sort(key=lambda t: t.start)
        return self.out

    def _emit(self, start: int, end: int, kind: str) -> None:
        if end > start:
            self.out.append(Token(start, end, kind))

    def _parts(self, pos: int, *parts: tuple[int, str]) -> int:
        for length, kind in parts:
            self._emit(pos, pos + length, kind)
            pos += length
        return pos

    def _add_pending(self, pos: int, parts: list[tuple[int, str]]) -> None:
        if pos not in self.pending:
            bisect.insort(self.pending_pos, pos)
        self.pending[pos] = parts

    def _next_pending(self, lo: int, hi: int) -> int | None:
        i = bisect.bisect_left(self.pending_pos, lo)
        if i < len(self.pending_pos) and self.pending_pos[i] < hi:
            return self.pending_pos[i]
        return None

    def _scan(self, lo: int, hi: int, mode: str) -> None:
        text = self.text
        gap = pos = lo
        while pos < hi:
            m = self.cand_re.search(text, pos, hi)
            cand = m.start() if m else hi
            pend = self._next_pending(pos, hi)
            if pend is not None and pend <= cand:
                self._gap(gap, pend, mode)
                parts = self.pending.pop(pend)
                self.pending_pos.remove(pend)
                pos = gap = self._parts(pend, *parts)
                continue
            if m is None:
                break
            end = None
            for lit in self._lits_at(cand):
                for fn in self.rules[lit]:
                    mark = len(self.out)
                    end = fn(cand, hi, mode)
                    if end is not None:
                        break
                    del self.out[mark:]
                if end is not None:
                    break
            if end is None:
                pos = cand + 1
                continue
            # The rule's tokens are emitted already; the final sort restores order.
            self._gap(gap, cand, mode)
            pos = gap = end
        self._gap(gap, hi, mode)

    def _lits_at(self, pos: int) -> list[str]:
        t = self.text
        return [lit for lit in self.lits if t.startswith(lit, pos)] if pos < len(t) else []

    # ------------------------------------------------------------------ gaps
    def _gap(self, lo: int, hi: int, mode: str) -> None:
        if hi <= lo:
            return
        if mode == TEXT:
            if self.html:
                self._gap_html(lo, hi)
        elif mode == PATHM:
            s = self.text[lo:hi]
            stripped = s.strip()
            if stripped:
                a = lo + s.index(stripped)
                self._emit(a, a + len(stripped), PATH)
        elif mode == VALUE:
            self._gap_regex(_VALUE_RE, lo, hi, {
                "str": STRING, "call": FUNCTION, "ref": VAR, "key": KEY,
                "const": CONSTANT, "num": NUMBER, "punct": PUNCT,
            })
        elif mode == EXPR:
            self._gap_regex(_EXPR_RE, lo, hi, {
                "str": STRING, "num": NUMBER, "const": CONSTANT, "kw": KEYWORD, "fn": FUNCTION,
                "var": VAR, "cmt": COMMENT, "op": OPERATOR,
            })
        elif mode == VARM:
            self._emit(lo, hi, VAR)
        elif mode == STRM:
            self._emit(lo, hi, STRING)
        elif mode == ITER:
            self._gap_regex(_ITER_RE, lo, hi, {"num": NUMBER, "var": VAR_DEF, "punct": PUNCT})

    def _gap_regex(self, rx: re.Pattern, lo: int, hi: int, kinds: dict[str, str]) -> None:
        for m in rx.finditer(self.text, lo, hi):
            self._emit(m.start(), m.end(), kinds[m.lastgroup])

    def _gap_html(self, lo: int, hi: int) -> None:
        t = self.text
        pos = lo
        while pos < hi:
            st = self.html_state
            if st is None:
                m = _HTML_TAG_START.search(t, pos, hi)
                if not m:
                    return
                s = m.group(0)
                if s.startswith("<!--"):
                    self._emit(m.start(), m.end(), HTML_COMMENT)
                elif s.startswith("&"):
                    self._emit(m.start(), m.end(), HTML_ENTITY)
                else:
                    self._emit(m.start(), m.end(), HTML_TAG)
                    self.html_state = "tag"
                pos = m.end()
            elif st == "tag":
                m = _HTML_IN_TAG.search(t, pos, hi)
                if not m:
                    return
                g = m.lastgroup
                if g == "end":
                    self._emit(m.start(), m.end(), HTML_TAG)
                    self.html_state = None
                elif g == "q":
                    self.html_state = m.group(0)
                    self._emit(m.start(), m.end(), HTML_STRING)
                elif g == "attr":
                    self._emit(m.start(), m.end(), HTML_ATTR)
                pos = m.end()
            else:  # inside an attribute string
                q = t.find(st, pos, hi)
                if q < 0:
                    self._emit(pos, hi, HTML_STRING)
                    return
                self._emit(pos, q + 1, HTML_STRING)
                self.html_state = "tag"
                pos = q + 1

    # --------------------------------------------------------------- helpers
    def _balanced_close(self, open_tag: str, close_tag: str, start: int) -> int:
        t = self.text
        depth, i = 1, start
        while True:
            c = t.find(close_tag, i)
            if c < 0:
                return -1
            o = t.find(open_tag, i, c) if open_tag else -1
            if o >= 0:
                depth += 1
                i = o + len(open_tag)
                continue
            depth -= 1
            if depth == 0:
                return c
            i = c + len(close_tag)

    def _var_kind(self, name: str) -> str:
        root = name.split(self.T["DIV_TAG_VAR_MEMBER_DELIMITER"] or ".", 1)[0]
        if root in SCOPE_VARS or name.startswith(SYSTEM_VAR_PREFIX):
            return VAR_BUILTIN
        return VAR

    def _emit_var(self, start: int, end: int, kind: str | None = None) -> None:
        """Emit a variable name, lexing nested replacements (``{$x}``) inside."""
        name = self.text[start:end]
        if "{" in name or "<" in name:
            self._scan(start, end, VARM)
            return
        self._emit(start, end, kind or self._var_kind(name))

    def _r_lit(self, kind: str) -> Callable[[int, int, str], int]:
        def rule(pos: int, hi: int, mode: str) -> int | None:
            for lit in self._lits_at(pos):
                if self.rules[lit] and rule in self.rules[lit]:
                    self._emit(pos, pos + len(lit), kind)
                    return pos + len(lit)
            return None

        return rule

    # ----------------------------------------------------------------- rules
    def _r_comment(self, pos: int, hi: int, mode: str) -> int | None:
        b, e = self.T["DIV_TAG_COMMENT_BEGIN"], self.T["DIV_TAG_COMMENT_END"]
        close = self.text.find(e, pos + len(b))
        if close < 0:
            return None
        end = close + len(e)
        # Documentation properties (02.34) split the comment into pieces.
        cur = pos
        for m in self._doc_re.finditer(self.text, pos + len(b), close):
            self._emit(cur, m.start(1), COMMENT)
            self._emit(m.start(1), m.end(1), DOC)
            cur = m.end(1)
        self._emit(cur, end, COMMENT)
        return end

    def _r_ignore(self, pos: int, hi: int, mode: str) -> int | None:
        b, e = self.T["DIV_TAG_IGNORE_BEGIN"], self.T["DIV_TAG_IGNORE_END"]
        close = self.text.find(e, pos + len(b))
        if close < 0:
            self._emit(pos, pos + len(b), ERROR)
            return pos + len(b)
        self._emit(pos, pos + len(b), KEYWORD)
        self._emit(pos + len(b), close, IGNORED)
        self._emit(close, close + len(e), KEYWORD)
        return close + len(e)

    def _r_macro(self, pos: int, hi: int, mode: str) -> int | None:
        b, e = self.T["DIV_TAG_MACRO_BEGIN"], self.T["DIV_TAG_MACRO_END"]
        if self.text.startswith(b + "xml", pos):
            return None
        close = self.text.find(e, pos + len(b))
        if close < 0:
            return None
        self._emit(pos, pos + len(b), MACRO)
        self._scan(pos + len(b), close, EXPR)
        self._emit(close, close + len(e), MACRO)
        return close + len(e)

    def _r_tplvar(self, pos: int, hi: int, mode: str) -> int | None:
        b, e = self.T["DIV_TAG_TPLVAR_BEGIN"], self.T["DIV_TAG_TPLVAR_END"]
        close = self._balanced_close(b, e, pos + len(b))
        if close < 0:
            return None
        self._emit(pos, pos + len(b), TPLVAR)
        inner = pos + len(b)
        m = self.tplvar_head.match(self.text, inner, close)
        if m:
            if m.group("prot"):
                self._emit(m.start("prot"), m.end("prot"), OPERATOR)
            self._emit(m.start("name"), m.end("name"), VAR_DEF)
            self._emit(m.start("op"), m.end("op"), TPLVAR)
            inner = m.end()
        self._scan(inner, close, VALUE)
        self._emit(close, close + len(e), TPLVAR)
        return close + len(e)

    def _r_default(self, pos: int, hi: int, mode: str) -> int | None:
        b, e = self.T["DIV_TAG_DEFAULT_REPLACEMENT_BEGIN"], self.T["DIV_TAG_DEFAULT_REPLACEMENT_END"]
        close = self.text.find(e, pos + len(b))
        if close < 0:
            return None
        self._emit(pos, pos + len(b), TPLVAR)
        self._scan(pos + len(b), close, VALUE)
        self._emit(close, close + len(e), TPLVAR)
        return close + len(e)

    def _r_include(self, b: str, e: str) -> Callable[[int, int, str], int | None]:
        def rule(pos: int, hi: int, mode: str) -> int | None:
            eol = self.text.find("\n", pos)
            eol = len(self.text) if eol < 0 else eol
            close = self.text.find(e, pos + len(b), eol)
            if close < 0 or not self.text[pos + len(b) : close].strip():
                return None
            self._emit(pos, pos + len(b), INCLUDE)
            self._scan(pos + len(b), close, PATHM)
            self._emit(close, close + len(e), INCLUDE)
            return close + len(e)

        return rule

    def _r_conditions(self, pos: int, hi: int, mode: str) -> int | None:
        b, e = self.T["DIV_TAG_CONDITIONS_BEGIN_PREFIX"], self.T["DIV_TAG_CONDITIONS_BEGIN_SUFFIX"]
        close = self.text.find(e, pos + len(b))
        if close < 0:
            return None
        self._emit(pos, pos + len(b), COND)
        self._scan(pos + len(b), close, EXPR)
        self._emit(close, close + len(e), COND)
        return close + len(e)

    def _r_formula(self, pos: int, hi: int, mode: str) -> int | None:
        b, e = self.T["DIV_TAG_FORMULA_BEGIN"], self.T["DIV_TAG_FORMULA_END"]
        close = self._balanced_close(b, e, pos + len(b))
        if close < 0:
            return None
        self._emit(pos, pos + len(b), OPERATOR)
        body_end = close
        # Optional number format after the last nested tag: (# expr :2. #)
        last_brace = self.text.rfind(self.T["DIV_TAG_REPLACEMENT_SUFFIX"] or "}", pos, close)
        m = self.formula_fmt.search(self.text, max(last_brace + 1, pos + len(b)), close)
        if m:
            body_end = m.start()
            fmt = m.group(0)[1:].strip()
            fpos = self.text.index(fmt, m.start() + 1)
            self._emit(m.start(), m.start() + 1, OPERATOR)
            self._emit(fpos, fpos + len(fmt), FORMAT)
        self._scan(pos + len(b), body_end, EXPR)
        self._emit(close, close + len(e), OPERATOR)
        return close + len(e)

    def _r_txt(self, pos: int, hi: int, mode: str) -> int | None:
        b = self.T["DIV_TAG_TXT_BEGIN"]
        end = pos + len(b)
        self._emit(pos, end, KEYWORD)
        m = self.txt_width.match(self.text, end)
        if m:
            self._emit(m.start("w"), m.end("w"), NUMBER)
            self._emit(m.start("op"), m.end("op"), OPERATOR)
            end = m.end()
        return end

    def _r_format(self, rx: re.Pattern) -> Callable[[int, int, str], int | None]:
        def rule(pos: int, hi: int, mode: str) -> int | None:
            m = rx.match(self.text, pos)
            if not m:
                return None
            self._emit(pos, m.start("var"), REPLACE)
            self._emit_var(m.start("var"), m.end("var"))
            self._emit(m.end("var"), m.start("fmt"), REPLACE)
            self._emit(m.start("fmt"), m.end("fmt"), FORMAT)
            self._emit(m.end("fmt"), m.end(), REPLACE)
            return m.end()

        return rule

    def _r_multi(self, pos: int, hi: int, mode: str) -> int | None:
        m = self.multi_re.match(self.text, pos)
        if not m:
            return None
        self._emit(pos, m.start("var"), REPLACE)
        self._emit_var(m.start("var"), m.end("var"))
        sep = self.T["DIV_TAG_MULTI_MODIFIERS_SEPARATOR"]
        i = m.start("mods")
        for piece in m.group("mods").split(sep):
            if piece:
                self._emit(i, i + len(piece), MODIFIER)
            i += len(piece) + len(sep)
        # separators between modifiers
        j = m.start("mods")
        while True:
            k = self.text.find(sep, j, m.end("mods"))
            if k < 0:
                break
            self._emit(k, k + len(sep), REPLACE)
            j = k + len(sep)
        self._emit(m.end("mods"), m.end(), REPLACE)
        return m.end()

    def _emit_replacement(self, m: re.Match) -> int:
        self._emit(m.start(), m.start("mod"), REPLACE)
        mod = m.group("mod")
        simple = mod == self.T["DIV_TAG_MODIFIER_SIMPLE"]
        self._emit(m.start("mod"), m.end("mod"), REPLACE if simple else MODIFIER)
        var = m.group("var")
        if m.group("sep") is not None and simple and var in self.aggregates:
            self._emit(m.start("var"), m.end("var"), FUNCTION)
            self._emit(m.start("sep"), m.end("sep"), REPLACE)
            self._emit_var(m.start("sub"), m.end("sub"))
        else:
            self._emit_var(m.start("var"), m.end("var"))
            if m.group("sep") is not None:
                self._emit(m.start("sep"), m.end("sep"), REPLACE)
                sub = m.group("sub")
                t = self.T
                is_mod = re.fullmatch(
                    rf"(?:{re.escape(t['DIV_TAG_MODIFIER_TRUNCATE'])}|{re.escape(t['DIV_TAG_MODIFIER_WORDWRAP'])})\d+"
                    rf"|\d+(?:{re.escape(t['DIV_TAG_MODIFIER_SUBSTRING_SEPARATOR'])}\d+)?",
                    sub,
                )
                self._emit(m.start("sub"), m.end("sub"), MODIFIER if is_mod else FORMAT)
        end_var = m.end("sub") if m.group("sep") is not None else m.end("var")
        self._emit(end_var, m.end(), REPLACE)
        return m.end()

    def _r_replacement(self, pos: int, hi: int, mode: str) -> int | None:
        m = self.rep_re.match(self.text, pos)
        if m:
            return self._emit_replacement(m)
        if mode == TEXT:
            m = self.custom_rep_re.match(self.text, pos)
            if m and not self._subparser_close(pos):
                return self._emit_replacement(m)
        return None

    def _subparser_close(self, pos: int) -> tuple[re.Match, int, str, str] | None:
        T = self.T
        b, bs = T["DIV_TAG_SUBPARSER_BEGIN_PREFIX"], T["DIV_TAG_SUBPARSER_BEGIN_SUFFIX"]
        m = self.subparser_name.match(self.text, pos + len(b))
        if not m or not self.text.startswith(bs, m.end()):
            return None
        open_tag = self.text[pos : m.end() + len(bs)]
        close_tag = T["DIV_TAG_SUBPARSER_END_PREFIX"] + m.group(0) + T["DIV_TAG_SUBPARSER_END_SUFFIX"]
        close = self._balanced_close(open_tag, close_tag, m.end() + len(bs))
        if close < 0:
            return None
        return m, close, open_tag, close_tag

    def _r_subparser(self, pos: int, hi: int, mode: str) -> int | None:
        found = self._subparser_close(pos)
        if not found:
            return None
        m, close, open_tag, close_tag = found
        T = self.T
        self._emit(pos, m.start(), SUBPARSER)
        self._emit(m.start("name"), m.end("name"), SUBPARSER)
        if m.group("event"):
            self._emit(m.end("name"), m.start("event"), SUBPARSER)
            self._emit(m.start("event"), m.end("event"), CONSTANT)
        end = m.end() + len(T["DIV_TAG_SUBPARSER_BEGIN_SUFFIX"])
        self._emit(m.end(), end, SUBPARSER)
        ep = len(T["DIV_TAG_SUBPARSER_END_PREFIX"])
        name_len = len(m.group(0))
        self._add_pending(close, [(ep, SUBPARSER), (name_len, SUBPARSER), (len(T["DIV_TAG_SUBPARSER_END_SUFFIX"]), SUBPARSER)])
        return end

    def _r_multirep(self, pos: int, hi: int, mode: str) -> int | None:
        T = self.T
        b, bs = T["DIV_TAG_MULTI_REPLACEMENT_BEGIN_PREFIX"], T["DIV_TAG_MULTI_REPLACEMENT_BEGIN_SUFFIX"]
        m = self.key_re.match(self.text, pos + len(b))
        if not m or not self.text.startswith(bs, m.end()):
            return None
        key = m.group(0)
        open_tag = b + key + bs
        close_tag = T["DIV_TAG_MULTI_REPLACEMENT_END_PREFIX"] + key + T["DIV_TAG_MULTI_REPLACEMENT_END_SUFFIX"]
        close = self._balanced_close(open_tag, close_tag, pos + len(open_tag))
        if close < 0:
            return None
        self._parts(pos, (len(b), MULTIREP), (len(key), VAR), (len(bs), MULTIREP))
        self._add_pending(close, [
            (len(T["DIV_TAG_MULTI_REPLACEMENT_END_PREFIX"]), MULTIREP), (len(key), VAR),
            (len(T["DIV_TAG_MULTI_REPLACEMENT_END_SUFFIX"]), MULTIREP),
        ])
        return pos + len(open_tag)

    def _r_loop(self, pos: int, hi: int, mode: str) -> int | None:
        T = self.T
        b, bs = T["DIV_TAG_LOOP_BEGIN_PREFIX"], T["DIV_TAG_LOOP_BEGIN_SUFFIX"]
        ep, es = T["DIV_TAG_LOOP_END_PREFIX"], T["DIV_TAG_LOOP_END_SUFFIX"]
        m = re.compile(self.nested_var_re).match(self.text, pos + len(b))
        if not m or not self.text.startswith(bs, m.end()):
            return None
        key = m.group(0)
        open_tag = b + key + bs
        close_tag = ep + key + es
        end = pos + len(open_tag)
        close = self._balanced_close(open_tag, close_tag, end)
        kind = LOOP if close >= 0 else ERROR
        self._emit(pos, pos + len(b), kind)
        self._emit_var(m.start(), m.end())
        self._emit(m.end(), end, kind)
        if close < 0:
            return end
        it = self.loop_item.match(self.text, end)
        if it:
            self._emit(it.start("item"), it.end("item"), VAR_DEF)
            self._emit(it.start("op"), it.end("op"), LOOP)
            end = it.end()
        self._add_pending(close, [(len(ep), LOOP), (len(key), self._var_kind(key)), (len(es), LOOP)])
        return end

    def _r_orphan_end(self, pos: int, hi: int, mode: str) -> int | None:
        T = self.T
        b, bs = T["DIV_TAG_LOOP_END_PREFIX"], T["DIV_TAG_LOOP_END_SUFFIX"]
        m = re.compile(self.nested_var_re).match(self.text, pos + len(b))
        if not m or not self.text.startswith(bs, m.end()):
            return None
        end = m.end() + len(bs)
        self._emit(pos, end, ERROR)
        return end

    def _r_iteration(self, pos: int, hi: int, mode: str) -> int | None:
        b, e = self.T["DIV_TAG_ITERATION_BEGIN_PREFIX"], self.T["DIV_TAG_ITERATION_BEGIN_SUFFIX"]
        eol = self.text.find("\n", pos)
        eol = len(self.text) if eol < 0 else eol
        close = self.text.find(e, pos + len(b), eol)
        if close < 0:
            return None
        params = self.text[pos + len(b) : close]
        if "[" in params or "]" in params or not params.strip():
            return None
        self._emit(pos, pos + len(b), LOOP)
        self._scan(pos + len(b), close, ITER)
        self._emit(close, close + len(e), LOOP)
        return close + len(e)

    def _r_location(self, pos: int, hi: int, mode: str) -> int | None:
        m = self.location_re.match(self.text, pos)
        if not m:
            return None
        self._emit(pos, m.start("name"), LOCATION)
        self._emit(m.start("name"), m.end("name"), VAR_DEF)
        self._emit(m.end("name"), m.end(), LOCATION)
        return m.end()

    def _r_keyed(self, bp: str, bs: str, ep: str, es: str, kind: str) -> Callable[[int, int, str], int | None]:
        def rule(pos: int, hi: int, mode: str) -> int | None:
            T = self.T
            b, s, e1, e2 = T[bp], T[bs], T[ep], T[es]
            start = pos + len(b)
            if s:
                stop = self.text.find(s, start)
                if stop < 0:
                    return None
                key = self.text[start:stop]
                if not key or re.search(r"\s", key):
                    return None
                candidates = [key]
            else:
                m = self.key_re.match(self.text, start)
                if not m:
                    return None
                key = m.group(0)
                candidates = [key[:i] for i in range(len(key), 0, -1)]
            for k in candidates:
                open_tag = b + k + s
                close_tag = e1 + k + e2
                close = self._balanced_close(open_tag, close_tag, pos + len(open_tag))
                if close < 0:
                    continue
                self._parts(pos, (len(b), kind), (len(k), self._var_kind(k)), (len(s), kind))
                self._add_pending(close, [(len(e1), kind), (len(k), self._var_kind(k)), (len(e2), kind)])
                return pos + len(open_tag)
            return None

        return rule

    def _r_string(self, pos: int, hi: int, mode: str) -> int | None:
        """Quoted strings inside code containers may embed Div tags: "{$role}"."""
        if mode not in (EXPR, VALUE):
            return None
        t, q = self.text, self.text[pos]
        i = pos + 1
        while i < hi:
            c = t[i]
            if c == "\\":
                i += 2
                continue
            if c == q:
                break
            if c == "\n" and mode == EXPR:
                return None
            i += 1
        else:
            return None
        self._emit(pos, pos + 1, STRING)
        self._scan(pos + 1, i, STRM)
        self._emit(i, i + 1, STRING)
        return i + 1

    def _r_property(self, pos: int, hi: int, mode: str) -> int | None:
        line_start = self.text.rfind("\n", 0, pos) + 1
        if self.text[line_start:pos].strip() or mode != TEXT:
            return None
        m = self.property_re.match(self.text, pos)
        if not m:
            return None
        self._emit(pos, m.end("name"), PROPERTY)
        self._emit(m.start("sp"), m.end("sp"), OPERATOR)
        self._emit(m.start("val"), m.end("val"), PROPERTY_VALUE)
        return m.end()


def tokenize(text: str, dialect: Dialect | None = None, html: bool = True) -> list[Token]:
    return Lexer(dialect, html=html).tokenize(text)
