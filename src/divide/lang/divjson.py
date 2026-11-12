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
