"""PHP: colours from tree-sitter's PHP grammar, errors from PHP itself.

The grammar (``tree-sitter-php``, with its own highlight query) only colours
the code. Whether the code is right is PHP's answer: ``php -l`` parses the
buffer and reports the first error, as it would when the file runs.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass
from functools import lru_cache

from divide.lang.div.diagnostics import Diagnostic

PREFIX = "php."  # highlight names: php.keyword, php.string… (the theme styles them)


@lru_cache(maxsize=1)
def grammar() -> tuple[object, str] | None:
    """``(tree-sitter Language, highlight query)``; None without tree-sitter-php."""
    try:
        import tree_sitter_php
        from tree_sitter import Language
    except ImportError:
        return None
    query = tree_sitter_php.HIGHLIGHTS_QUERY
    # the grammar's capture names, in our own namespace (predicates name them too)
    query = re.sub(r"@([a-z][a-z.]*)", lambda m: "@" + PREFIX + m.group(1), query)
    return Language(tree_sitter_php.language_php()), query


_ERROR = re.compile(r"^(?:PHP )?(Parse error|Fatal error|Warning|Deprecated|Notice):\s*(.*?) in Standard input code on line (\d+)", re.M)


def parse_lint(output: str, text: str) -> list[Diagnostic]:
    """The errors of ``php -l`` as diagnostics over their whole line."""
    lines = text.split("\n")
    starts = [0]
    for line in lines[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    found: list[Diagnostic] = []
    for kind, message, number in _ERROR.findall(output):
        row = min(max(int(number) - 1, 0), len(lines) - 1)
        start = starts[row]
        line = lines[row]
        indent = len(line) - len(line.lstrip())
        end = start + len(line)
        severity = "error" if kind.endswith("error") else "warning"
        # "Error: syntax error…" in the Messages window; warnings keep PHP's word for them
        text_ = message if severity == "error" else f"{kind}: {message}"
        found.append(Diagnostic(start + indent if indent < len(line) else start, max(end, start + 1), severity, text_))
    return found


async def lint(text: str, php: str | None = None, timeout: float = 10.0) -> list[Diagnostic] | None:
    """PHP's verdict on ``text`` (None: no php to ask)."""
    php = php or shutil.which("php")
    if not php:
        return None
    proc = await asyncio.create_subprocess_exec(
        php, "-d", "display_errors=stderr", "-d", "log_errors=0", "-l",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(text.encode("utf-8")), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return None
    if proc.returncode == 0:
        return []
    return parse_lint(err.decode("utf-8", "replace") + out.decode("utf-8", "replace"), text)


def in_parentheses(text: str, offset: int, window: int = 4000) -> bool:
    """Is ``offset`` inside a parenthesis still open (a call's arguments)? Strings
    and comments are skipped. Language servers may answer a signature for the
    call next to the cursor even after it is closed: this tells them apart."""
    start = max(0, offset - window)
    if start:
        start = text.find("\n", start) + 1 or start
    depth = 0
    i = start
    while i < offset:
        ch = text[i]
        if ch in "'\"":
            i += 1
            while i < offset and text[i] != ch:
                i += 2 if text[i] == "\\" else 1
        elif ch == "#" or (ch == "/" and text.startswith("//", i)):
            end = text.find("\n", i)
            i = offset if end < 0 or end >= offset else end
            continue
        elif ch == "/" and text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = offset if end < 0 or end >= offset else end + 2
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        i += 1
    return depth > 0


# ---------------------------------------------------------------- outline
@dataclass(frozen=True)
class Symbol:
    """A declaration of the file: what Search > Outline lists."""

    kind: str  # namespace, class, interface, trait, enum, function, method, property, const, case
    name: str
    detail: str  # "(array $items): float" for a function, "private static" for a member
    level: int  # 0 the file, 1 inside a class
    start: int  # the name, as offsets into the text
    end: int

    @property
    def text(self) -> str:
        """``class Cart``, ``+ add(string $name): self``, ``- $items``, ``const TAX``."""
        indent = "  " * self.level
        if self.kind in ("namespace", "class", "interface", "trait", "enum", "const", "case"):
            return f"{indent}{self.kind} {self.name}{self.detail if self.kind == 'class' else ''}"
        mark = "" if self.level == 0 else VISIBILITY.get(self.detail.split(" ")[0], "+") + " "
        if self.kind == "property":
            return f"{indent}{mark}{self.name}"
        return f"{indent}{mark}{self.name}{self.signature}"

    @property
    def signature(self) -> str:
        return self.detail.split("|", 1)[1] if "|" in self.detail else ""


VISIBILITY = {"public": "+", "protected": "#", "private": "-"}  # UML's marks
_CLASSES = {"class_declaration": "class", "interface_declaration": "interface",
            "trait_declaration": "trait", "enum_declaration": "enum"}


def outline(text: str) -> list[Symbol] | None:
    """The declarations of ``text``, in order, from tree-sitter's PHP grammar
    (None without it). Closures and anonymous classes are left out."""
    found = grammar()
    if found is None:
        return None
    from tree_sitter import Parser

    source = text.encode("utf-8")
    tree = Parser(found[0]).parse(source)  # type: ignore[arg-type]

    def offset(byte: int) -> int:
        return len(source[:byte].decode("utf-8", "replace"))

    def flat(node) -> str:
        return re.sub(r"\s+", " ", source[node.start_byte:node.end_byte].decode("utf-8", "replace")).strip()

    symbols: list[Symbol] = []

    def add(kind: str, name_node, detail: str, level: int) -> None:
        symbols.append(Symbol(kind, flat(name_node), detail, level, offset(name_node.start_byte), offset(name_node.end_byte)))

    def modifiers(node) -> str:
        words = [flat(c) for c in node.named_children if c.type.endswith("_modifier")]
        return " ".join(words) or "public"

    def signature(node) -> str:
        params = node.child_by_field_name("parameters")
        returns = node.child_by_field_name("return_type")
        return (flat(params) if params is not None else "()") + (f": {flat(returns)}" if returns is not None else "")

    def members(body, level: int) -> None:
        for member in body.named_children:
            if member.type == "method_declaration" and member.child_by_field_name("name") is not None:
                add("method", member.child_by_field_name("name"), f"{modifiers(member)}|{signature(member)}", level)
            elif member.type == "property_declaration":
                for element in member.named_children:
                    if element.type == "property_element" and element.named_children:
                        add("property", element.named_children[0], modifiers(member), level)
            elif member.type == "const_declaration":
                for element in member.named_children:
                    if element.type == "const_element" and element.named_children:
                        add("const", element.named_children[0], "", level)
            elif member.type == "enum_case" and member.child_by_field_name("name") is not None:
                add("case", member.child_by_field_name("name"), "", level)

    def top(container, level: int) -> None:
        for node in container.named_children:
            name = node.child_by_field_name("name")
            if node.type == "namespace_definition":
                if name is not None:
                    add("namespace", name, "", level)
                body = node.child_by_field_name("body")
                if body is not None:  # namespace X { ... }
                    top(body, level)
            elif node.type in _CLASSES and name is not None:
                extends = next((c for c in node.named_children if c.type == "base_clause"), None)
                add(_CLASSES[node.type], name, f" {flat(extends)}" if extends is not None else "", level)
                body = node.child_by_field_name("body")
                if body is not None:
                    members(body, level + 1)
            elif node.type == "function_definition" and name is not None:
                add("function", name, f"|{signature(node)}", level)
            elif node.type == "const_declaration":
                for element in node.named_children:
                    if element.type == "const_element" and element.named_children:
                        add("const", element.named_children[0], "", level)
            elif node.type in ("compound_statement", "declare_statement", "if_statement"):
                top(node, level)  # function_exists() guards, declare(...) { }

    top(tree.root_node, 0)
    return symbols
