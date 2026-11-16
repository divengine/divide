#!/usr/bin/env python3
"""Mark divide's interface texts for translation: ``"Open a file"`` -> ``_("Open a file")``.

A one-off codemod (kept for modules written later): it finds the string
literals that read as interface text and wraps them; f-strings become
``_("... {name} ...").format(name=...)`` so the translator sees whole
sentences with named places. It leaves alone what is not shown: docstrings,
CSS, comparisons and ``case`` patterns, regular expressions, arguments of
``startswith`` / ``split`` / ``replace``..., dictionary keys, key bindings'
descriptions, Div code (``{$``, ``DIV_TAG``), and single words that are not
the text of a widget (``"Outline"`` is also a help topic's name).

    tools/i18n_mark.py src/divide/ui/palette.py ...   # rewrites the files
    tools/i18n_mark.py --dry-run FILES                 # lists what it would mark
"""

from __future__ import annotations

import argparse
import ast
import keyword
import re
import sys
from pathlib import Path

UI_CALLS = {
    "MenuItem", "SubMenu", "Label", "Button", "StatusItem", "information", "confirm", "InputDialog", "MessageBox",
    "notify", "set_hint", "ProgressDialog", "Static", "MessageItem", "CheckBoxes", "RadioButtons", "FileDialog",
    "finish", "start_busy", "busy", "relabel_busy", "Item", "_Dialog", "PickButtons", "Palette", "Section",
    "Completion", "Diagnostic", "ScriptMessage", "RenderMessage", "show", "set", "update", "TextArea",
}
SKIP_METHODS = {
    "startswith", "endswith", "split", "rsplit", "partition", "rpartition", "replace", "join", "find", "rfind",
    "index", "count", "strip", "lstrip", "rstrip", "removeprefix", "removesuffix", "get", "pop", "setdefault",
    "compile", "search", "match", "fullmatch", "sub", "subn", "finditer", "findall", "escape", "Binding",
    "getattr", "setattr", "hasattr", "query", "query_one", "add_class", "remove_class", "set_class", "has_class",
    "run_worker", "set_value", "environ", "Path", "open", "run", "create_subprocess_exec", "format_map",
}
PROSE = re.compile(r"[A-Za-z]{2,}[,.:!?…'’]* +\(?[A-Za-z(]|~\w")
WORD = re.compile(r"[A-Z][a-z]+(?: [a-z]+)?[.!…]*")
CODE = re.compile(r"DIV_TAG|\{\$|<\?|\(\?|\\[dswb]|^\s*[{\[<]|[{}]\s*$|\$\w+")
NAMED = re.compile(r"(TITLE|HINT|LABEL|LABELS|MESSAGE|TEXT|EMPTY|NAME)S?$")


def is_docstring(node: ast.AST, parents: dict[int, ast.AST]) -> bool:
    expr = parents.get(id(node))
    owner = parents.get(id(expr)) if isinstance(expr, ast.Expr) else None
    return isinstance(owner, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and owner.body[0] is expr


def call_name(call: ast.Call) -> str:
    f = call.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def wanted(node: ast.AST, text: str, parents: dict[int, ast.AST]) -> bool:
    if not text.strip() or CODE.search(text) or ("{" in text and ";" in text):
        return False
    if text.lstrip().startswith(("/*", "//", "#")) or (text.count("\n") >= 3 and "{" in text):
        return False  # code, or a template written with placeholders (the dialector's examples)
    single = not PROSE.search(text)
    if single and not WORD.fullmatch(text):
        return False
    child, p, depth, ui = node, parents.get(id(node)), 0, False
    while p is not None and depth < 6:
        if isinstance(p, ast.Call):
            name = call_name(p)
            if name == "_" or name in SKIP_METHODS:
                return False
            if name in UI_CALLS:
                ui = True
                break
        if isinstance(p, (ast.Compare, ast.MatchValue, ast.Subscript, ast.JoinedStr)):
            return False
        if isinstance(p, ast.Dict) and any(k is child for k in p.keys):
            return False
        if isinstance(p, (ast.Assign, ast.AnnAssign)):
            targets = p.targets if isinstance(p, ast.Assign) else [p.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)] + [t.attr for t in targets if isinstance(t, ast.Attribute)]
            if any(n in ("DEFAULT_CSS", "CSS", "__all__", "COMPONENT_CLASSES") for n in names):
                return False
            if any(NAMED.search(n.upper()) for n in names):
                ui = True
            break
        if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            break
        child, p, depth = p, parents.get(id(p)), depth + 1
    return ui or not single


def placeholder(expr: ast.AST, source: str, used: dict[str, str]) -> str:
    seg = ast.get_source_segment(source, expr) or "value"
    if seg in used:
        return used[seg]
    if isinstance(expr, ast.Call) and call_name(expr) == "len":
        base = "count"
    else:
        words = re.findall(r"[A-Za-z_]\w*", seg)
        base = (words[-1] if words else "value").strip("_").lower() or "value"
        if keyword.iskeyword(base):
            base = "value"
    name, n = base, 2
    while name in used.values():
        name, n = f"{base}{n}", n + 1
    used[seg] = name
    return name


def fstring(node: ast.JoinedStr, source: str) -> str | None:
    template, args, used = [], [], {}
    for v in node.values:
        if isinstance(v, ast.Constant):
            template.append(v.value.replace("{", "{{").replace("}", "}}"))
            continue
        if not isinstance(v, ast.FormattedValue) or isinstance(v.value, ast.IfExp):
            return None  # a plural made with an if: by hand, with ngettext
        name = placeholder(v.value, source, used)
        spec = ""
        if v.conversion != -1:
            spec += "!" + chr(v.conversion)
        if v.format_spec is not None:
            parts = v.format_spec.values
            if not all(isinstance(x, ast.Constant) for x in parts):
                return None
            spec += ":" + "".join(x.value for x in parts)
        template.append("{" + name + spec + "}")
        seg = ast.get_source_segment(source, v.value)
        if seg is None or "\n" in seg:
            return None
        if (name, seg) not in args:
            args.append((name, seg))
    text = "".join(template)
    call = f"_({text!r})"
    return call + (".format(" + ", ".join(f"{n}={s}" for n, s in args) + ")" if args else "")


def mark(path: Path, dry: bool) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents = {id(c): n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
    edits: list[tuple[int, int, int, int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if is_docstring(node, parents) or isinstance(parents.get(id(node)), (ast.JoinedStr, ast.FormattedValue)):
                continue
            if wanted(node, node.value, parents):
                edits.append((node.lineno, node.col_offset, node.end_lineno, node.end_col_offset,
                              f"_({node.value!r})", node.value))
        elif isinstance(node, ast.JoinedStr):
            text = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
            if isinstance(parents.get(id(node)), ast.FormattedValue) or not PROSE.search(text):
                continue
            if text.count("\n") >= 3:
                continue  # a template written with placeholders (the dialector's examples)
            if wanted(node, text, parents) and (new := fstring(node, source)) is not None:
                edits.append((node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, new, text))
    if dry or not edits:
        return [f"{path}:{e[0]}: {e[5]!r}" for e in sorted(edits)]
    lines = source.encode("utf-8").splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    data = source.encode("utf-8")
    for l1, c1, l2, c2, new, _text in sorted(edits, reverse=True):
        a, b = starts[l1 - 1] + c1, starts[l2 - 1] + c2
        data = data[:a] + new.encode("utf-8") + data[b:]
    text = data.decode("utf-8")
    ast.parse(text)  # before writing anything
    if not re.search(r"^from divide\.i18n import .*\b_\b", text, re.M):
        m = re.search(r"^from __future__ import annotations\n", text, re.M)
        at = m.end() if m else 0
        text = text[:at] + "\nfrom divide.i18n import _\n" + text[at:]
    path.write_text(text, encoding="utf-8")
    ast.parse(text)
    return [f"{path}:{e[0]}: {e[5]!r}" for e in sorted(edits)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    total = 0
    for path in args.files:
        found = mark(path, args.dry_run)
        total += len(found)
        print("\n".join(found))
    print(f"{total} texts", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
