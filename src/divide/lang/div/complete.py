"""Completion of Div templates (UI-independent).

``complete()`` looks at the text before the cursor and returns what can be
inserted there:

- variables after ``{$``, ``{^$`` (any modifier), ``[$``, ``?$`` / ``!$`` and
  inside conditions and formulas: from the data JSON, the open loops (the item
  fields, the item name and Div's ``_key``, ``_index``... ), the template
  variables (``{= name: ... =}``) and the variables already used in the text;
- the name of the open loop after ``[/$``;
- template paths after ``{% `` / ``{%% ``;
- Div tags (snippets) when asked explicitly with nothing more specific.

Everything is taken from the template's dialect. Positions are code-point
offsets into the text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from divide.lang.div.dialect import SCOPE_VARS, Dialect
from divide.lang.div.lexer import Token

CARET = "\x00"  # marks the cursor inside a snippet's text

_MODIFIERS = ("^^^", "^^", "^", "_", "%%%%", "%%%", "%%", "%", "&&", "&", "~", "/", "'")
_NAME = r"[A-Za-z_][\w.\-]*"


@dataclass(frozen=True)
class Completion:
    label: str
    insert: str  # replaces text[start:cursor]; may contain CARET
    detail: str = ""
    after: str = ""  # inserted after the cursor unless already there
    retrigger: bool = False  # complete again right after inserting (snippet that opens a context)
    extra: tuple = ()  # other edits (start, end, text) in the text as it was, e.g. a `use` line to import a class
    data: object = None  # where it came from (a language server's item: its documentation is asked for later)


@dataclass
class CompletionResult:
    start: int
    prefix: str
    items: list[Completion] = field(default_factory=list)
    context: str = ""  # "var" | "loop" | "close" | "path" | "tag"


# ------------------------------------------------------------------ variables
def type_label(value: object) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return f"array[{len(value)}]"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return "ref"


def flatten(data: object, prefix: str = "", sep: str = ".", depth: int = 3) -> dict[str, object]:
    """``{"a": {"b": 1}}`` -> ``{"a": {...}, "a.b": 1}`` (dotted member paths)."""
    out: dict[str, object] = {}
    if not isinstance(data, dict):
        return out
    for key, value in data.items():
        name = f"{prefix}{key}"
        out[name] = value
        if depth > 1 and isinstance(value, dict):
            out.update(flatten(value, name + sep, sep, depth - 1))
    return out


def _lookup(data: object, path: str, sep: str) -> object:
    cur = data
    for part in path.split(sep):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
    return cur


def _sample_item(value: object) -> object:
    """What one iteration sees: the merged fields of the items (lists of objects)."""
    items = list(value.values()) if isinstance(value, dict) else value if isinstance(value, list) else []
    merged: dict = {}
    for item in items[:50]:
        if not isinstance(item, dict):
            return items[0] if items else None
        for k, v in item.items():
            merged.setdefault(k, v)
    return merged if merged else (items[0] if items else None)


@dataclass
class _Loop:
    name: str
    item: str = "value"


def open_loops(text: str, tokens: list[Token], offset: int, dialect: Dialect) -> list[_Loop]:
    """The loops that enclose ``offset``, outermost first (unclosed ones included)."""
    begin, end = dialect["DIV_TAG_LOOP_BEGIN_PREFIX"], dialect["DIV_TAG_LOOP_END_PREFIX"]
    suffix = dialect["DIV_TAG_LOOP_BEGIN_SUFFIX"]
    sep = dialect["DIV_TAG_LOOP_VAR_SEPARATOR"]
    item_re = re.compile(r"[ \t]*([A-Za-z_]\w*)[ \t]*" + re.escape(sep)) if sep else None
    stack: list[_Loop] = []
    n = len(tokens)
    for i, tok in enumerate(tokens):
        if tok.start >= offset:
            break
        if tok.kind not in ("div.loop", "div.error") or i + 1 >= n:
            continue
        frag = text[tok.start : tok.end]
        nxt = tokens[i + 1]
        if frag not in (begin, end) or nxt.start != tok.end:
            continue
        name = text[nxt.start : nxt.end]
        if frag == end:
            for j in range(len(stack) - 1, -1, -1):
                if stack[j].name == name:
                    del stack[j:]
                    break
            continue
        loop = _Loop(name)
        after = nxt.end + len(suffix)
        if item_re is not None and text.startswith(suffix, nxt.end):
            m = item_re.match(text, after)
            if m and m.end() <= offset:
                loop.item = m.group(1)
        stack.append(loop)
    return stack


def scope_variables(
    text: str, tokens: list[Token], offset: int, dialect: Dialect, data: object = None
) -> list[tuple[str, str]]:
    """(name, detail) of every variable visible at ``offset``, the closest scope first."""
    sep = dialect["DIV_TAG_VAR_MEMBER_DELIMITER"] or "."
    out: dict[str, str] = {}

    def add(name: str, detail: str) -> None:
        if name and name not in out:
            out[name] = detail

    # open loops, innermost first; each one's list is looked up in the scope around it
    loops = open_loops(text, tokens, offset, dialect)
    scopes: list[object] = [data]
    for loop in loops:
        value = None
        for scope in reversed(scopes):
            value = _lookup(scope, loop.name, sep)
            if value is not None:
                break
        item = _sample_item(value)
        scopes.append({**(item if isinstance(item, dict) else {}), loop.item: item})
    for loop, scope in zip(reversed(loops), reversed(scopes[1:])):
        assert isinstance(scope, dict)
        item = scope.get(loop.item)
        add(loop.item, f"item of {loop.name}" + (f" · {type_label(item)}" if item is not None else ""))
        for name, value in flatten(item, loop.item + sep, sep).items():
            add(name, type_label(value))
        if isinstance(item, dict):
            for name, value in flatten(item, "", sep).items():
                add(name, type_label(value))
        for name in sorted(SCOPE_VARS - {"value"}):
            add(name, f"loop {loop.name}")

    for name, value in flatten(data, "", sep).items():
        add(name, type_label(value))

    # template variables and the variables already used
    for i, tok in enumerate(tokens):
        if tok.kind == "div.var.def" and i and text[tokens[i - 1].start : tokens[i - 1].end] == dialect["DIV_TAG_TPLVAR_BEGIN"]:
            add(text[tok.start : tok.end].lstrip(dialect["DIV_TAG_TPLVAR_PROTECTOR"] or "*"), "template var")
    for tok in tokens:
        if tok.kind == "div.var" and not (tok.start <= offset <= tok.end):
            name = text[tok.start : tok.end].lstrip("$")
            if re.fullmatch(_NAME, name):
                add(name, "used")
    return list(out.items())


def _filter(items: list[Completion], prefix: str, key=lambda c: c.label) -> list[Completion]:
    if not prefix:
        return items
    low = prefix.lower()
    head = [c for c in items if key(c).lower().startswith(low)]
    rest = [c for c in items if low in key(c).lower() and c not in head]
    return head + rest


# ---------------------------------------------------------------------- paths
def template_paths(prefix: str, template: Path | None, roots: list[Path]) -> list[Completion]:
    """Folders (``dir/``) and ``.tpl`` files (without extension) matching a typed path."""
    folder, _, _ = prefix.rpartition("/")
    bases = ([template.parent] if template is not None else []) + list(roots)
    seen: set[str] = set()
    out: list[Completion] = []
    for base in bases:
        directory = base / folder if folder else base
        try:
            children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            continue
        for child in children:
            if child.name.startswith("."):
                continue
            rel = f"{folder}/{child.name}" if folder else child.name
            if child.is_dir():
                if rel + "/" not in seen:
                    seen.add(rel + "/")
                    out.append(Completion(rel + "/", rel + "/", "folder", retrigger=True))
            elif child.suffix.lower() == ".tpl":
                name = rel[: -len(child.suffix)]
                if name not in seen:
                    seen.add(name)
                    out.append(Completion(name, name, "template"))
    return out


# --------------------------------------------------------------------- tags
def tag_snippets(T: Dialect) -> list[Completion]:
    """Div constructs, written with the dialect's tags (CARET: where the cursor goes)."""
    c = CARET
    snippets: list[tuple[str, str, str, bool]] = []  # label, insert, detail, retrigger

    def add(label: str, insert: str, detail: str, retrigger: bool = False, *needs: str) -> None:
        if all(T[k] for k in needs):
            snippets.append((label, insert, detail, retrigger))

    rp, rs, simple = T["DIV_TAG_REPLACEMENT_PREFIX"], T["DIV_TAG_REPLACEMENT_SUFFIX"], T["DIV_TAG_MODIFIER_SIMPLE"]
    add(f"{rp}{simple}var{rs}", f"{rp}{simple}{c}{rs}", "replacement", True, "DIV_TAG_REPLACEMENT_PREFIX")
    lb, ls, le = T["DIV_TAG_LOOP_BEGIN_PREFIX"], T["DIV_TAG_LOOP_BEGIN_SUFFIX"], T["DIV_TAG_LOOP_END_PREFIX"]
    add(f"{lb}list{ls} ... {le}list{ls}", f"{lb}{c}", "loop", True, "DIV_TAG_LOOP_BEGIN_PREFIX")
    cb, cs, ce = T["DIV_TAG_CONDITIONS_BEGIN_PREFIX"], T["DIV_TAG_CONDITIONS_BEGIN_SUFFIX"], T["DIV_TAG_CONDITIONS_END"]
    add(f"{cb} expr {cs} ... {ce}", f"{cb} {c} {cs}{ce}", "condition", False, "DIV_TAG_CONDITIONS_BEGIN_PREFIX")
    if T["DIV_TAG_ELSE"]:
        add(f"{cb} expr {cs} ... {T['DIV_TAG_ELSE']} ... {ce}", f"{cb} {c} {cs}{T['DIV_TAG_ELSE']}{ce}", "condition with else", False, "DIV_TAG_CONDITIONS_BEGIN_PREFIX")
    tp, tf = T["DIV_TAG_CONDITIONAL_TRUE_BEGIN_PREFIX"], T["DIV_TAG_CONDITIONAL_FALSE_BEGIN_PREFIX"]
    add(f"{tp}var ... {T['DIV_TAG_CONDITIONAL_TRUE_END_PREFIX']}var{T['DIV_TAG_CONDITIONAL_TRUE_END_SUFFIX']}", f"{tp}{c}", "if var is true", True, "DIV_TAG_CONDITIONAL_TRUE_BEGIN_PREFIX")
    add(f"{tf}var ... {T['DIV_TAG_CONDITIONAL_FALSE_END_PREFIX']}var{T['DIV_TAG_CONDITIONAL_FALSE_END_SUFFIX']}", f"{tf}{c}", "if var is false", True, "DIV_TAG_CONDITIONAL_FALSE_BEGIN_PREFIX")
    vb, ve, op = T["DIV_TAG_TPLVAR_BEGIN"], T["DIV_TAG_TPLVAR_END"], T["DIV_TAG_TPLVAR_ASSIGN_OPERATOR"]
    add(f"{vb} name{op} value {ve}", f"{vb} {c}{op}  {ve}", "template variable", False, "DIV_TAG_TPLVAR_BEGIN")
    add(f"{T['DIV_TAG_INCLUDE_BEGIN']}path{T['DIV_TAG_INCLUDE_END']}", f"{T['DIV_TAG_INCLUDE_BEGIN']}{c}", "include", True, "DIV_TAG_INCLUDE_BEGIN")
    add(f"{T['DIV_TAG_PREPROCESSED_BEGIN']}path{T['DIV_TAG_PREPROCESSED_END']}", f"{T['DIV_TAG_PREPROCESSED_BEGIN']}{c}", "preprocessed include", True, "DIV_TAG_PREPROCESSED_BEGIN")
    add(f"{T['DIV_TAG_FORMULA_BEGIN']} expr {T['DIV_TAG_FORMULA_END']}", f"{T['DIV_TAG_FORMULA_BEGIN']} {c} {T['DIV_TAG_FORMULA_END']}", "formula", False, "DIV_TAG_FORMULA_BEGIN")
    add(f"{T['DIV_TAG_DEFAULT_REPLACEMENT_BEGIN']} ... {T['DIV_TAG_DEFAULT_REPLACEMENT_END']}", f"{T['DIV_TAG_DEFAULT_REPLACEMENT_BEGIN']}{c}{T['DIV_TAG_DEFAULT_REPLACEMENT_END']}", "default replacement", False, "DIV_TAG_DEFAULT_REPLACEMENT_BEGIN")
    add(f"{T['DIV_TAG_COMMENT_BEGIN']} ... {T['DIV_TAG_COMMENT_END']}", f"{T['DIV_TAG_COMMENT_BEGIN']} {c} {T['DIV_TAG_COMMENT_END']}", "comment", False, "DIV_TAG_COMMENT_BEGIN")
    ib, ie = T["DIV_TAG_ITERATION_BEGIN_PREFIX"], T["DIV_TAG_ITERATION_BEGIN_SUFFIX"]
    add(f"{ib}1,10{ie} ... {T['DIV_TAG_ITERATION_END']}", f"{ib}1,10{ie}{c}{T['DIV_TAG_ITERATION_END']}", "iteration", False, "DIV_TAG_ITERATION_BEGIN_PREFIX")
    for key, name in (("IGNORE", "ignore block"), ("TXT", "text block"), ("STRIP", "strip block")):
        b, e = T[f"DIV_TAG_{key}_BEGIN"], T[f"DIV_TAG_{key}_END"]
        add(f"{b} ... {e}", f"{b}{c}{e}", name, False, f"DIV_TAG_{key}_BEGIN")
    add(f"{T['DIV_TAG_LOCATION_BEGIN']}name{T['DIV_TAG_LOCATION_END']}", f"{T['DIV_TAG_LOCATION_BEGIN']}{c}{T['DIV_TAG_LOCATION_END']}", "location", False, "DIV_TAG_LOCATION_BEGIN")
    add(f"{T['DIV_TAG_MACRO_BEGIN']} php {T['DIV_TAG_MACRO_END']}", f"{T['DIV_TAG_MACRO_BEGIN']} {c} {T['DIV_TAG_MACRO_END']}", "macro", False, "DIV_TAG_MACRO_BEGIN")
    for key, name in (("ELSE", "else"), ("EMPTY", "loop is empty"), ("BREAK", "break the loop")):
        add(T[f"DIV_TAG_{key}"], T[f"DIV_TAG_{key}"], name, False, f"DIV_TAG_{key}")
    return [Completion(label, insert, detail, retrigger=r) for label, insert, detail, r in snippets]


# ---------------------------------------------------------------- contexts
def _ends_with_any(text: str, tags: list[str]) -> str | None:
    for tag in sorted((t for t in tags if t), key=len, reverse=True):
        if text.endswith(tag):
            return tag
    return None


def _inside(before: str, begin: str, end: str) -> bool:
    """``before`` (the current line up to the cursor) has an unclosed ``begin``."""
    if not begin or not end:
        return False
    pos = before.rfind(begin)
    return pos >= 0 and before.find(end, pos + len(begin)) < 0


def complete(
    text: str,
    offset: int,
    tokens: list[Token],
    dialect: Dialect,
    *,
    data: object = None,
    template: Path | None = None,
    roots: list[Path] | None = None,
    explicit: bool = False,
) -> CompletionResult | None:
    """Completions at ``offset``; ``explicit`` (Ctrl+Space) also offers tags anywhere."""
    T = dialect
    roots = roots or []
    line_start = text.rfind("\n", 0, offset) + 1
    before = text[line_start:offset]
    rest = text[offset:]

    # include paths: {% path   {%% path
    for begin_key, end_key in (("DIV_TAG_PREPROCESSED_BEGIN", "DIV_TAG_PREPROCESSED_END"), ("DIV_TAG_INCLUDE_BEGIN", "DIV_TAG_INCLUDE_END")):
        begin, end = T[begin_key], T[end_key]
        if not begin:
            continue
        m = re.search(re.escape(begin) + r"([\w./\-]*)$", before)
        if m:
            prefix = m.group(1)
            items = template_paths(prefix, template, roots)
            closed = rest.startswith(end.lstrip()) or rest.startswith(end)
            items = [it if it.retrigger or closed else Completion(it.label, it.insert, it.detail, after=end) for it in items]
            return CompletionResult(offset - len(prefix), prefix, _filter(items, prefix), "path")

    simple = T["DIV_TAG_MODIFIER_SIMPLE"] or "$"
    m = re.search(re.escape(simple) + r"(" + _NAME + r")?$", before)
    if m:
        prefix = m.group(1) or ""
        pre = before[: m.start()]
        start = offset - len(prefix)
        lb, ls = T["DIV_TAG_LOOP_BEGIN_PREFIX"], T["DIV_TAG_LOOP_BEGIN_SUFFIX"]
        le, les = T["DIV_TAG_LOOP_END_PREFIX"], T["DIV_TAG_LOOP_END_SUFFIX"]
        rp, rs = T["DIV_TAG_REPLACEMENT_PREFIX"], T["DIV_TAG_REPLACEMENT_SUFFIX"]
        modifiers = [rp + mod for mod in _MODIFIERS] + [rp + T[k] for k in ("DIV_TAG_MODIFIER_ENCODE_JSON", "DIV_TAG_MODIFIER_HTML_ENTITIES", "DIV_TAG_MODIFIER_NL2BR", "DIV_TAG_MODIFIER_JS") if T[k]]

        # [/$ : the loop to close
        if le.endswith(simple) and (pre + simple).endswith(le):
            loops = open_loops(text, tokens, offset - len(prefix) - len(le), dialect)
            items = [Completion(loop.name, loop.name, "close loop", after="" if rest.startswith(les) else les) for loop in reversed(loops)]
            return CompletionResult(start, prefix, _filter(items, prefix), "close") if items or explicit else None

        variables = scope_variables(text, tokens, offset, dialect, data)

        # [$ : a list to loop over, closed after the cursor
        if lb.endswith(simple) and (pre + simple).endswith(lb):
            ordered = sorted(variables, key=lambda v: 0 if v[1].startswith("array") else 1 if v[1] == "object" else 2)
            items = []
            for name, detail in ordered:
                opened = text.count(lb + name + ls, offset)
                closes = text.count(le + name + les, offset)
                tail = ls if not rest.startswith(ls) else ""
                closing = "" if closes > opened else le + name + les
                items.append(Completion(name, name + tail, detail, after=closing))
            return CompletionResult(start, prefix, _filter(items, prefix), "loop") if items or explicit else None

        tp, tf = T["DIV_TAG_CONDITIONAL_TRUE_BEGIN_PREFIX"], T["DIV_TAG_CONDITIONAL_FALSE_BEGIN_PREFIX"]
        cond = None
        for begin, end_prefix, end_suffix in (
            (tp, T["DIV_TAG_CONDITIONAL_TRUE_END_PREFIX"], T["DIV_TAG_CONDITIONAL_TRUE_END_SUFFIX"]),
            (tf, T["DIV_TAG_CONDITIONAL_FALSE_END_PREFIX"], T["DIV_TAG_CONDITIONAL_FALSE_END_SUFFIX"]),
        ):
            if begin.endswith(simple) and (pre + simple).endswith(begin):
                cond = (end_prefix, end_suffix)
        in_expression = (
            _inside(before, T["DIV_TAG_CONDITIONS_BEGIN_PREFIX"], T["DIV_TAG_CONDITIONS_BEGIN_SUFFIX"])
            or _inside(before, T["DIV_TAG_FORMULA_BEGIN"], T["DIV_TAG_FORMULA_END"])
            or _inside(before, T["DIV_TAG_TPLVAR_BEGIN"], T["DIV_TAG_TPLVAR_END"])
        )
        replacement = rp and (_ends_with_any(pre, modifiers + [rp]) is not None or (pre + simple).endswith(T["DIV_TAG_MULTI_MODIFIERS_PREFIX"] or "\0"))
        if cond is not None:
            items = [Completion(n, n, d, after="" if (cond[0] + n + cond[1]) in rest else cond[0] + n + cond[1]) for n, d in variables]
        elif replacement:
            tail = "" if rest.startswith(rs) else rs
            items = [Completion(n, n + tail, d) for n, d in variables]
        elif in_expression or explicit:
            items = [Completion(n, n, d) for n, d in variables]
        else:
            return None
        return CompletionResult(start, prefix, _filter(items, prefix), "var") if items or explicit else None

    if not explicit:
        return None
    # tags: the punctuation (or word) typed just before the cursor narrows them
    m = re.search(r"([^\s\w]+|\w+)$", before)
    prefix = m.group(1) if m else ""
    snippets = tag_snippets(T)
    if prefix and not prefix[0].isalnum():
        items = [s for s in snippets if s.insert.replace(CARET, "").startswith(prefix)]
    elif prefix:
        items = [s for s in snippets if s.detail.startswith(prefix.lower())]
    else:
        items = snippets
    if not items:
        prefix, items = "", snippets
    return CompletionResult(offset - len(prefix), prefix, items, "tag")
