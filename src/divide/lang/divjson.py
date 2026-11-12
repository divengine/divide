"""Div's JSON dialect: tokens (highlighting), parser (diagnostics, tree) and writer.

Div decodes data with its own ``jsonDecode``, which accepts more than JSON:

- references to variables as values: ``"name": $name``, ``"who": $person.name``
  (resolved against the variables that exist when Div decodes the JSON: in a
  template's ``{= x: {...} =}`` they work; in a top-level data file nothing is
  defined yet, so they come out null);
- single-quoted strings and unquoted keys (``{name: 'Rafa'}``);
- ``//`` and ``/* */`` comments;
- ``true`` / ``false`` / ``null`` in any case.

References are kept as :class:`Ref` values so a tree editor can show and
write them back unquoted.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from divide.lang.div.lexer import Token


@dataclass(frozen=True)
class Ref:
    """A ``$path.to.var`` reference."""

    path: str

    def __str__(self) -> str:
        return "$" + self.path


class DivJsonError(ValueError):
    def __init__(self, message: str, text: str, offset: int) -> None:
        self.message = message
        self.offset = offset
        self.line = text.count("\n", 0, offset) + 1
        self.column = offset - (text.rfind("\n", 0, offset) + 1) + 1
        super().__init__(f"line {self.line}, col {self.column}: {message}")


_WS = re.compile(r"(?:\s+|//[^\n]*|/\*.*?(?:\*/|\Z))*", re.DOTALL)
_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_IDENT = re.compile(r"[A-Za-z_][\w-]*")
_REF = re.compile(r"\$[A-Za-z_][\w]*(?:\.[\w]+)*")
_CONST = {"true": True, "false": False, "null": None}
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "/": "/", "\\": "\\", '"': '"', "'": "'"}


# ------------------------------------------------------------------ tokens
_TOKEN = re.compile(
    r"""(?P<comment>//[^\n]*|/\*.*?(?:\*/|\Z))
      |(?P<string>"(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?)
      |(?P<ref>\$[A-Za-z_][\w]*(?:\.[\w]+)*)
      |(?P<number>-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
      |(?P<word>[A-Za-z_][\w-]*)
      |(?P<punct>[{}\[\],:])
      |(?P<space>\s+)
      |(?P<error>.)""",
    re.VERBOSE | re.DOTALL,
)
_KEY_AFTER = re.compile(r"\s*:")


def tokenize(text: str) -> list[Token]:
    """Tokens with kinds ``json.key|string|number|constant|ref|punct|comment|error``."""
    tokens: list[Token] = []
    for m in _TOKEN.finditer(text):
        kind = m.lastgroup
        if kind == "space":
            continue
        start, end = m.span()
        if kind in ("string", "word") and _KEY_AFTER.match(text, end):
            kind = "key"
        elif kind == "word":
            kind = "constant" if m.group().lower() in _CONST else "error"
        elif kind == "string" and (len(m.group()) < 2 or m.group()[-1] != m.group()[0]):
            kind = "error"  # unterminated
        tokens.append(Token(start, end, "json." + kind))
    return tokens


def references(text: str) -> list[str]:
    """``$refs`` used as values (outside strings and comments)."""
    return [text[t.start + 1 : t.end] for t in tokenize(text) if t.kind == "json.ref"]


# ------------------------------------------------------------------ parser
class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def fail(self, message: str, offset: int | None = None) -> DivJsonError:
        return DivJsonError(message, self.text, self.pos if offset is None else offset)

    def ws(self) -> None:
        self.pos = _WS.match(self.text, self.pos).end()

    def peek(self) -> str:
        return self.text[self.pos : self.pos + 1]

    def document(self) -> Any:
        self.ws()
        if self.pos >= len(self.text):
            raise self.fail("empty document")
        value = self.value()
        self.ws()
        if self.pos < len(self.text):
            raise self.fail(f"unexpected {self.text[self.pos]!r} after the value")
        return value

    def value(self) -> Any:
        c = self.peek()
        if c == "{":
            return self.object()
        if c == "[":
            return self.array()
        if c in "\"'" and c:
            return self.string()
        if c == "$":
            m = _REF.match(self.text, self.pos)
            if not m:
                raise self.fail("bad reference, expected $name or $name.member")
            self.pos = m.end()
            return Ref(m.group()[1:])
        m = _NUMBER.match(self.text, self.pos)
        if m and c:
            self.pos = m.end()
            n = m.group()
            return float(n) if any(ch in n for ch in ".eE") else int(n)
        m = _IDENT.match(self.text, self.pos)
        if m and m.group().lower() in _CONST:
            self.pos = m.end()
            return _CONST[m.group().lower()]
        if not c:
            raise self.fail("unexpected end, expected a value")
        raise self.fail(f"unexpected {c!r}, expected a value")

    def string(self) -> str:
        quote = self.text[self.pos]
        start = self.pos
        self.pos += 1
        out: list[str] = []
        while True:
            if self.pos >= len(self.text):
                raise self.fail("unterminated string", start)
            c = self.text[self.pos]
            if c == quote:
                self.pos += 1
                return "".join(out)
            if c == "\\":
                nxt = self.text[self.pos + 1 : self.pos + 2]
                if nxt == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", self.text[self.pos + 2 : self.pos + 6]):
                    out.append(chr(int(self.text[self.pos + 2 : self.pos + 6], 16)))
                    self.pos += 6
                    continue
                if nxt in _ESCAPES:
                    out.append(_ESCAPES[nxt])
                    self.pos += 2
                    continue
                raise self.fail(f"bad escape \\{nxt}")
            if c == "\n":
                raise self.fail("unterminated string", start)
            out.append(c)
            self.pos += 1

    def key(self) -> str:
        c = self.peek()
        if c and c in "\"'":
            return self.string()
        m = _IDENT.match(self.text, self.pos)
        if not m:
            raise self.fail(f"unexpected {c!r}, expected a key" if c else "unexpected end, expected a key")
        self.pos = m.end()
        return m.group()

    def object(self) -> dict[str, Any]:
        self.pos += 1
        result: dict[str, Any] = {}
        while True:
            self.ws()
            if self.peek() == "}":
                self.pos += 1
                return result
            key = self.key()
            self.ws()
            if self.peek() != ":":
                raise self.fail(f"expected ':' after the key {key!r}")
            self.pos += 1
            self.ws()
            result[key] = self.value()
            self.ws()
            c = self.peek()
            if c == ",":
                self.pos += 1
            elif c == "}":
                self.pos += 1
                return result
            else:
                raise self.fail("expected ',' or '}'" if c else "unexpected end, expected '}'")

    def array(self) -> list[Any]:
        self.pos += 1
        result: list[Any] = []
        while True:
            self.ws()
            if self.peek() == "]":
                self.pos += 1
                return result
            result.append(self.value())
            self.ws()
            c = self.peek()
            if c == ",":
                self.pos += 1
            elif c == "]":
                self.pos += 1
                return result
            else:
                raise self.fail("expected ',' or ']'" if c else "unexpected end, expected ']'")


def loads(text: str) -> Any:
    """Parse Div JSON. Raises :class:`DivJsonError` with line and column."""
    return _Parser(text).document()


# ------------------------------------------------------------------ writer
def dumps(value: Any, indent: int = 2, _level: int = 0) -> str:
    """Write standard JSON, with :class:`Ref` values as bare ``$refs``."""
    pad = " " * (indent * (_level + 1))
    end = " " * (indent * _level)
    if isinstance(value, Ref):
        return str(value)
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [f"{pad}{json.dumps(str(k), ensure_ascii=False)}: {dumps(v, indent, _level + 1)}" for k, v in value.items()]
        return "{\n" + ",\n".join(items) + "\n" + end + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        items = [pad + dumps(v, indent, _level + 1) for v in value]
        return "[\n" + ",\n".join(items) + "\n" + end + "]"
    return json.dumps(value, ensure_ascii=False)


def has_extensions(text: str) -> bool:
    """True when ``text`` uses comments, single quotes or unquoted keys (lost on rewrite)."""
    for tok in tokenize(text):
        if tok.kind == "json.comment":
            return True
        if tok.kind in ("json.string", "json.key") and text[tok.start] == "'":
            return True
        if tok.kind == "json.key" and text[tok.start] not in "\"'":
            return True
    return False


# ------------------------------------------------------------- tree edits
# A path is a tuple of keys (objects) and indexes (arrays) from the root.
Path_ = tuple


def get_at(root: Any, path: Path_) -> Any:
    node = root
    for step in path:
        node = node[step]
    return node


def _parent(root: Any, path: Path_) -> tuple[Any, Any]:
    if not path:
        raise ValueError("the root has no parent")
    return get_at(root, path[:-1]), path[-1]


def set_at(root: Any, path: Path_, value: Any) -> Any:
    """Replace the value at ``path``; returns the (possibly new) root."""
    if not path:
        return value
    parent, step = _parent(root, path)
    parent[step] = value
    return root


def delete_at(root: Any, path: Path_) -> None:
    parent, step = _parent(root, path)
    del parent[step]


def rename_key(root: Any, path: Path_, new_key: str) -> Path_:
    """Rename an object member keeping its position. Returns the new path."""
    parent, old = _parent(root, path)
    if new_key == old:
        return path
    if new_key in parent:
        raise ValueError(f"key {new_key!r} already exists")
    items = [(new_key if k == old else k, v) for k, v in parent.items()]
    parent.clear()
    parent.update(items)
    return path[:-1] + (new_key,)


def insert_after(root: Any, container_path: Path_, after: Any, key: str | None, value: Any) -> Path_:
    """Insert into the container at ``container_path`` after member/index ``after``
    (``None``: at the end). ``key`` is required for objects. Returns the new path."""
    container = get_at(root, container_path)
    if isinstance(container, list):
        index = len(container) if after is None else after + 1
        container.insert(index, value)
        return container_path + (index,)
    if not isinstance(container, dict):
        raise ValueError("can only insert into an object or an array")
    if not key:
        raise ValueError("an object member needs a key")
    if key in container:
        raise ValueError(f"key {key!r} already exists")
    items = list(container.items())
    index = len(items) if after is None else [k for k, _ in items].index(after) + 1
    items.insert(index, (key, value))
    container.clear()
    container.update(items)
    return container_path + (key,)


def move(root: Any, path: Path_, delta: int) -> Path_:
    """Move a member/item up (-1) or down (+1) inside its container. Returns the new path."""
    parent, step = _parent(root, path)
    if isinstance(parent, list):
        new = step + delta
        if not 0 <= new < len(parent):
            return path
        parent[step], parent[new] = parent[new], parent[step]
        return path[:-1] + (new,)
    items = list(parent.items())
    index = [k for k, _ in items].index(step)
    new = index + delta
    if not 0 <= new < len(items):
        return path
    items[index], items[new] = items[new], items[index]
    parent.clear()
    parent.update(items)
    return path


def type_name(value: Any) -> str:
    """One of: String, Number, True, False, Null, Reference, Object, Array."""
    if isinstance(value, Ref):
        return "Reference"
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return "Null"
    if isinstance(value, (int, float)):
        return "Number"
    if isinstance(value, dict):
        return "Object"
    if isinstance(value, list):
        return "Array"
    return "String"


TYPES = ["String", "Number", "True", "False", "Null", "Reference", "Object", "Array"]


def make_value(type_: str, text: str, current: Any = None) -> Any:
    """Build a value of ``type_`` from the dialog's text. Containers keep ``current`` when it already is one."""
    if type_ == "String":
        return text
    if type_ == "Number":
        try:
            return int(text) if re.fullmatch(r"-?\d+", text.strip()) else float(text)
        except ValueError:
            raise ValueError(f"{text!r} is not a number") from None
    if type_ in ("True", "False", "Null"):
        return {"True": True, "False": False, "Null": None}[type_]
    if type_ == "Reference":
        path = text.strip().lstrip("$")
        if not _REF.fullmatch("$" + path):
            raise ValueError("a reference looks like name or person.name")
        return Ref(path)
    if type_ == "Object":
        return current if isinstance(current, dict) else {}
    if type_ == "Array":
        return current if isinstance(current, list) else []
    raise ValueError(f"unknown type {type_}")


def value_text(value: Any) -> str:
    """The text shown in the dialog's value field for ``value``."""
    if isinstance(value, Ref):
        return value.path
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)) or value is None or isinstance(value, bool):
        return ""
    return json.dumps(value)
