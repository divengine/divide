"""A Runner Flow's structure read from its YAML source, and edits that change only what they must (UI-independent).

The YAML text is the only model. :func:`parse` reads it with tree-sitter-yaml
(divide's highlighter) into Blocks and Steps that remember where each key and
value is written; nothing of the Flow is interpreted beyond that. Edits
(:func:`edit_step`, :func:`add_step`, :func:`delete_step`) are planned as one
replacement of the smallest span that holds them: a changed value replaces
the value's characters, a new attribute is one new line, a removed attribute
or Step its own lines; comments, key order, quoting and indentation elsewhere
stay as they are written. Every plan is verified by parsing its result again
(:func:`apply`). What cannot be changed in place (a Step in flow style,
anchors, aliases, tags, block scalars, several documents) is reported, not
rewritten.

Validation is Runner's: :func:`check` runs ``flowcheck.php``, which loads only
Runner's source file and calls its public ``runner::generateFlowCodeFromYaml()``
(parser, schema, call and jump targets) without evaluating the generated code,
so no condition or activity runs. Two design-time lookups add what Runner's
first error hides: targets missing from the file, and activity or condition
files missing where Runner's documented importer would look for them.
"""

from __future__ import annotations

from divide.i18n import _

import asyncio
import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from divide.lang.div.diagnostics import Diagnostic
from divide.run import children

ATTRS = ("module", "condition", "activity", "call", "jump", "context", "pause")  # editable, in this order
STEP_KEYS = ("description",) + ATTRS  # Runner's STEP_KEYS
FUNCTION_ATTRS = ("condition", "activity")
TARGET_ATTRS = ("call", "jump")
CHECKER = Path(__file__).with_name("flowcheck.php")
_MODULE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*$")  # Runner's MODULE_PATTERN
_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]+$")
_PLAIN = re.compile(r"^[A-Za-z_\\/][A-Za-z0-9_.\\/-]*(?::[A-Za-z0-9_.\\/-]+)?$")
_KEYWORDS = {"true", "false", "yes", "no", "on", "off", "null", "~"}  # what Runner reads as true, false, null
STEP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")  # what a new Step may be called here (Runner allows more)
_UNSUPPORTED = {"anchor": _("an anchor"), "alias": _("an alias"), "tag": _("a tag")}


class EditError(Exception):
    """An edit that cannot be made in place: the source stays as it is."""


# ---------------------------------------------------------------- the model
@dataclass
class Attr:
    key: str
    start: int  # the key/value pair
    end: int
    key_start: int
    key_end: int
    value_start: int  # == value_end: no value
    value_end: int
    raw: str  # the value as written
    kind: str  # scalar, mapping, flow, block_scalar, empty, other
    value: object = None  # a scalar's text (decoded), else None
    why: str | None = None  # why it cannot be edited in place

    def text(self) -> str:
        """The value as the dialog shows it."""
        if self.kind == "scalar":
            return "" if self.value is None else str(self.value)
        if self.kind == "mapping":
            return _flow_of_block(self.raw)
        return self.raw.strip()


@dataclass
class Step:
    block: str
    id: str
    start: int
    end: int
    key_start: int
    key_end: int
    attrs: dict[str, Attr] = field(default_factory=dict)
    style: str = "block"  # block, flow, empty, other
    why: str | None = None  # why it cannot be edited in place
    key_column: int = 0
    attr_column: int | None = None

    @property
    def name(self) -> str:
        return f"{self.block}.{self.id}"

    def get(self, key: str) -> str:
        attr = self.attrs.get(key)
        return attr.text() if attr is not None else ""


@dataclass
class Block:
    id: str
    start: int
    end: int
    key_start: int
    key_end: int
    steps: list[Step] = field(default_factory=list)
    description: str = ""
    steps_key: tuple[int, int] | None = None  # where ``steps:`` is written
    steps_style: str = "missing"  # block, empty, flow, missing, other
    key_column: int = 0

    def step(self, step_id: str) -> Step | None:
        return next((s for s in self.steps if s.id == step_id), None)


@dataclass
class Problem:
    start: int
    end: int
    message: str


@dataclass
class FlowDoc:
    text: str
    id: str = ""
    description: str = ""
    blocks: list[Block] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)  # what the YAML itself has wrong
    blocks_key: tuple[int, int] | None = None

    @property
    def editable(self) -> bool:
        return not self.problems

    def block(self, block_id: str) -> Block | None:
        return next((b for b in self.blocks if b.id == block_id), None)

    def step(self, block_id: str, step_id: str) -> Step | None:
        block = self.block(block_id)
        return block.step(step_id) if block is not None else None

    def steps(self) -> list[Step]:
        return [s for b in self.blocks for s in b.steps]

    def at(self, offset: int) -> Block | Step | None:
        """The Step (else the Block) written at ``offset``."""
        for block in self.blocks:
            for step in block.steps:
                if step.key_start <= offset < max(step.end, step.key_end + 1) or _same_line(self.text, step.key_start, offset):
                    return step
            if block.key_start <= offset < max(block.end, block.key_end + 1):
                return block
        return None


def _same_line(text: str, a: int, b: int) -> bool:
    return text.count("\n", 0, a) == text.count("\n", 0, b)


# ---------------------------------------------------------------- parsing
_PARSER = None


def _parser():
    global _PARSER
    if _PARSER is None:
        import tree_sitter_yaml
        from tree_sitter import Language, Parser
        _PARSER = Parser(Language(tree_sitter_yaml.language()))
    return _PARSER


class _Source:
    """The text, its UTF-8 bytes, and byte offsets turned into the editor's (character) offsets."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.data = text.encode("utf-8")
        self.ascii = len(self.data) == len(text)

    def char(self, byte: int) -> int:
        return byte if self.ascii else len(self.data[:byte].decode("utf-8", "replace"))

    def span(self, node) -> tuple[int, int]:
        return self.char(node.start_byte), self.char(node.end_byte)

    def raw(self, node) -> str:
        return self.data[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _unwrap(node):
    """The node a block_node / flow_node holds (its mapping, scalar...), skipping comments."""
    while node is not None and node.type in ("document", "block_node", "flow_node"):
        inner = [c for c in node.named_children if c.type != "comment"]
        if not inner:
            return node
        node = inner[-1]
    return node


def _odd(node) -> str | None:
    """An anchor, alias or tag inside ``node``, which divide does not edit."""
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type in _UNSUPPORTED:
            return _UNSUPPORTED[n.type]
        stack.extend(n.children)
    return None


def _scalar(src: _Source, node) -> object:
    """A scalar's text: plain as written, quoted ones decoded."""
    raw = src.raw(node).strip()
    if node.type == "double_quote_scalar":
        try:
            return json.loads(raw)
        except ValueError:
            return raw[1:-1]
    if node.type == "single_quote_scalar":
        return raw[1:-1].replace("''", "'")
    return raw


def _key(src: _Source, pair) -> tuple[str, object] | None:
    node = pair.child_by_field_name("key")
    inner = _unwrap(node) if node is not None else None
    if inner is None or inner.type not in ("plain_scalar", "double_quote_scalar", "single_quote_scalar"):
        return None
    return str(_scalar(src, inner)).strip(), node


def _pairs(mapping):
    return [c for c in mapping.named_children if c.type in ("block_mapping_pair", "flow_pair")]


def _column(text: str, offset: int) -> int:
    return offset - (text.rfind("\n", 0, offset) + 1)


def parse(text: str) -> FlowDoc:
    """The Flow written in ``text``: its Blocks and Steps and where they are, and what is wrong
    with the YAML itself (Runner says what is wrong with the Flow)."""
    src = _Source(text)
    doc = FlowDoc(text)
    tree = _parser().parse(src.data)
    root = tree.root_node
    for node in _errors(root):
        start, end = src.span(node)
        what = _('this is missing') if node.is_missing else _('this cannot be read as YAML')
        doc.problems.append(Problem(start, max(end, start + 1), _('YAML: {what} (line {line})').format(
            what=what, line=text.count("\n", 0, start) + 1)))
    documents = [c for c in root.named_children if c.type == "document"]
    if len(documents) > 1:
        start, _end = src.span(documents[1])
        doc.problems.append(Problem(start, start + 1, _('Several YAML documents: a Flow is one')))
    if not documents:
        return doc
    top = _unwrap(documents[0])
    if top is None or top.type != "block_mapping":
        return doc
    for pair in _pairs(top):
        named = _key(src, pair)
        if named is None:
            continue
        key, key_node = named
        value = _unwrap(pair.child_by_field_name("value"))
        if key == "id" and value is not None and value.type.endswith("scalar"):
            doc.id = str(_scalar(src, value))
        elif key == "description" and value is not None and value.type.endswith("scalar"):
            doc.description = str(_scalar(src, value))
        elif key == "blocks":
            doc.blocks_key = src.span(key_node)
            if value is not None and value.type == "block_mapping":
                for block_pair in _pairs(value):
                    block = _block(src, block_pair)
                    if block is not None:
                        doc.blocks.append(block)
    return doc


def _errors(root):
    out = []
    stack = [root]
    while stack:
        n = stack.pop()
        if n.type == "ERROR" or n.is_missing:
            out.append(n)
            continue
        if n.has_error:
            stack.extend(n.children)
    return sorted(out, key=lambda n: n.start_byte)


def _block(src: _Source, pair) -> Block | None:
    named = _key(src, pair)
    if named is None:
        return None
    block_id, key_node = named
    start, end = src.span(pair)
    key_start, key_end = src.span(key_node)
    block = Block(block_id, start, end, key_start, key_end, key_column=_column(src.text, key_start))
    body = _unwrap(pair.child_by_field_name("value"))
    if body is None or body.type != "block_mapping":
        return block
    for inner in _pairs(body):
        named = _key(src, inner)
        if named is None:
            continue
        key, inner_key = named
        value = _unwrap(inner.child_by_field_name("value"))
        if key == "description" and value is not None and value.type.endswith("scalar"):
            block.description = str(_scalar(src, value))
        elif key == "steps":
            block.steps_key = src.span(inner_key)
            if value is None or value.type in ("block_node", "flow_node"):
                block.steps_style = "empty"
            elif value.type == "block_mapping":
                block.steps_style = "block"
                for step_pair in _pairs(value):
                    step = _step(src, block_id, step_pair)
                    if step is not None:
                        block.steps.append(step)
            elif value.type == "flow_mapping":
                block.steps_style = "flow"
            else:
                block.steps_style = "other"
    return block


def _step(src: _Source, block_id: str, pair) -> Step | None:
    named = _key(src, pair)
    if named is None:
        return None
    step_id, key_node = named
    start, end = src.span(pair)
    key_start, key_end = src.span(key_node)
    step = Step(block_id, step_id, start, end, key_start, key_end, key_column=_column(src.text, key_start))
    value_node = pair.child_by_field_name("value")
    body = _unwrap(value_node)
    if body is None:
        step.style = "empty"
        return step
    if body.type == "flow_mapping":
        step.style, step.why = "flow", _('it is written in flow style ({...}): edit it in the code (Ctrl+T)')
    elif body.type != "block_mapping":
        step.style, step.why = "other", _('it is not a mapping: edit it in the code (Ctrl+T)')
    odd = _odd(value_node)
    if odd is not None and step.why is None:
        step.why = _('it has {what}: edit it in the code (Ctrl+T)').format(what=odd)
    for attr_pair in _pairs(body) if body.type in ("block_mapping", "flow_mapping") else []:
        attr = _attr(src, attr_pair)
        if attr is not None:
            step.attrs.setdefault(attr.key, attr)
            if step.attr_column is None and body.type == "block_mapping":
                step.attr_column = _column(src.text, attr.key_start)
    return step


def _attr(src: _Source, pair) -> Attr | None:
    named = _key(src, pair)
    if named is None:
        return None
    key, key_node = named
    start, end = src.span(pair)
    key_start, key_end = src.span(key_node)
    value_node = pair.child_by_field_name("value")
    inner = _unwrap(value_node)
    if value_node is None or inner is None:
        return Attr(key, start, end, key_start, key_end, key_end, key_end, "", "empty")
    value_start, value_end = src.span(value_node)
    raw = src.raw(value_node)
    odd = _odd(value_node)
    if odd is not None:
        return Attr(key, start, end, key_start, key_end, value_start, value_end, raw, "other",
                    why=_('{key} has {what}: edit it in the code (Ctrl+T)').format(key=key, what=odd))
    if inner.type in ("plain_scalar", "double_quote_scalar", "single_quote_scalar"):
        return Attr(key, start, end, key_start, key_end, value_start, value_end, raw, "scalar", _scalar(src, inner))
    if inner.type == "block_scalar":
        return Attr(key, start, end, key_start, key_end, value_start, value_end, raw, "block_scalar",
                    why=_('{key} is a block scalar (| or >): edit it in the code (Ctrl+T)').format(key=key))
    if inner.type == "block_mapping":  # its first line as indented as the others
        return Attr(key, start, end, key_start, key_end, value_start, value_end, " " * _column(src.text, value_start) + raw, "mapping")
    if inner.type == "flow_mapping":
        return Attr(key, start, end, key_start, key_end, value_start, value_end, raw, "flow")
    return Attr(key, start, end, key_start, key_end, value_start, value_end, raw, "other",
                why=_('{key} is written in a way divide does not edit: edit it in the code (Ctrl+T)').format(key=key))


def _flow_of_block(raw: str) -> str:
    """A block mapping's pairs, one level, as a flow mapping for one input line (``{a: 1, b: x}``);
    deeper ones as they are written, joined."""
    lines = [line for line in raw.split("\n") if line.strip() and not line.strip().startswith("#")]
    if not lines:
        return "{}"
    indent = min(len(line) - len(line.lstrip()) for line in lines)
    items = []
    for line in lines:
        if len(line) - len(line.lstrip()) != indent:
            return "{" + ", ".join(item.strip() for item in lines) + "}"
        items.append(_strip_comment(line).strip())
    return "{" + ", ".join(items) + "}"


def _strip_comment(line: str) -> str:
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line


# ---------------------------------------------------------------- targets and functions
def resolve_target(doc: FlowDoc, block_id: str, reference: str) -> tuple[Block | None, Step | None, str | None]:
    """Where a ``call`` or ``jump`` of a Step of ``block_id`` leads: (Block, Step, problem).
    ``block.step``; an empty Block is the Step's own, an empty Step the Block's first."""
    reference = reference.strip()
    if "." not in reference:
        return None, None, _("'{ref}' needs a dot: block.step").format(ref=reference)
    target_block, target_step = (part.strip() for part in reference.split(".", 1))
    block = doc.block(target_block or block_id)
    if block is None:
        return None, None, _("Block '{block}' is not in this Flow").format(block=target_block or block_id)
    if not target_step:
        return block, block.steps[0] if block.steps else None, None
    step = block.step(target_step)
    if step is None:
        return block, None, _("Step '{step}' is not in Block '{block}'").format(step=target_step, block=block.id)
    return block, step, None


@dataclass(frozen=True)
class Functions:
    """Where Runner's importer looks for activity and condition files."""

    root: Path  # the function root: --root, else the context's _root_folder, else the project
    modules: dict[str, Path] = field(default_factory=dict)  # the context's _modules

    def folder(self, module: str) -> Path:
        return self.modules.get(module) or self.root / module

    def candidates(self, name: str, module: str | None, cwd: Path) -> list[Path]:
        """The files the importer would ``require`` for ``name`` (only checked for existence here)."""
        name = name.strip()

        def php(path: Path) -> Path:
            return path if path.name.lower().endswith(".php") else path.with_name(path.name + ".php")

        if module:
            return [php(self.folder(module) / name)]
        given = Path(name)
        if given.is_absolute():
            return [php(given)]
        out = [php(self.root / name), php(cwd / name)]
        return list(dict.fromkeys(out))

    def find(self, name: str, module: str | None, cwd: Path) -> Path | None:
        return next((p for p in self.candidates(name, module, cwd) if p.is_file()), None)

    def names(self, module: str | None) -> list[str]:
        """The function files in the root (or a Module's folder), as references: ``name``, ``tax/compute``."""
        base = self.folder(module) if module else self.root
        if not base.is_dir():
            return []
        out = []
        for path in sorted(base.rglob("*.php")):
            rel = path.relative_to(base)
            if any(part.startswith(".") or part == "vendor" for part in rel.parts):
                continue
            if not module and len(rel.parts) > 1 and (base / rel.parts[0]).is_dir():
                continue  # a Module's folder
            out.append(rel.with_suffix("").as_posix())
        return out[:200]

    def module_names(self) -> list[str]:
        found = set(self.modules)
        if self.root.is_dir():
            found |= {p.name for p in self.root.iterdir() if p.is_dir() and _MODULE.match(p.name) and p.name != "vendor"
                      and not p.name.startswith(".")}
        return sorted(found)


def functions_for(project: Path, root: str = "", context: dict | None = None) -> Functions:
    """The function root and Modules a run of the Run Flow dialog would give Runner: ``--root``
    (``root``, relative to the project), else the initial context's ``_root_folder``, else the project
    (Runner runs there, and its default root is ``./``); Modules from the context's ``_modules``."""
    context = context or {}

    def at(value: str) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else project / path

    folder = root.strip() or (context.get("_root_folder") if isinstance(context.get("_root_folder"), str) else "") or ""
    modules = context.get("_modules") if isinstance(context.get("_modules"), dict) else {}
    return Functions(at(folder) if folder.strip() else project,
                     {str(k): at(v) for k, v in modules.items() if isinstance(v, str) and v.strip()})


def module_problem(module: str, name: str) -> str | None:
    """Runner's rule for a Module-qualified name, to skip the lookup of one Runner refuses anyway."""
    if not _MODULE.match(module):
        return "module"
    if any(seg in (".", "..") or not _SEGMENT.match(seg) for seg in name.split("/")):
        return "name"
    return None


# ---------------------------------------------------------------- editing
@dataclass(frozen=True)
class Change:
    start: int
    end: int
    text: str


def render_scalar(value: str) -> str:
    """A value as YAML: plain when that reads back as the same text, else double-quoted."""
    if (_PLAIN.match(value) and value.lower() not in _KEYWORDS and not re.match(r"^[-+.]?\d", value)
            and not value.endswith(":")):
        return value
    return json.dumps(value, ensure_ascii=False)


def _line_start(text: str, offset: int) -> int:
    return text.rfind("\n", 0, offset) + 1


def _line_after(text: str, offset: int) -> int:
    """Where the line holding the last written character before ``offset`` ends (past its newline)."""
    last = offset
    while last > 0 and text[last - 1] in " \t\r\n":
        last -= 1
    end = text.find("\n", max(last - 1, 0))
    return len(text) if end < 0 else end + 1


def _whole_lines(text: str, start: int, end: int) -> tuple[int, int]:
    """The lines of ``start:end``, when nothing else is written on them before it."""
    first = _line_start(text, start)
    if text[first:start].strip():
        raise EditError(_('Something else is written on its line: edit it in the code (Ctrl+T)'))
    return first, _line_after(text, end)


def _context_lines(raw: str, indent: int) -> str | None:
    """A flow mapping of plain pairs (``{a: 1, b: x}``) as block lines at ``indent``; None when it is not one."""
    src = _Source("x: " + raw.strip() + "\n")
    tree = _parser().parse(src.data)
    if tree.root_node.has_error:
        return None
    top = _unwrap(next((c for c in tree.root_node.named_children if c.type == "document"), None))
    if top is None or top.type != "block_mapping":
        return None
    value = _unwrap(_pairs(top)[0].child_by_field_name("value")) if _pairs(top) else None
    if value is None or value.type != "flow_mapping":
        return None
    lines = []
    for pair in _pairs(value):
        key, val = pair.child_by_field_name("key"), pair.child_by_field_name("value")
        inner = _unwrap(val)
        if key is None or val is None or inner is None or inner.type in ("flow_mapping", "flow_sequence"):
            return None
        lines.append(" " * indent + src.raw(key).strip() + ": " + src.raw(val).strip() + "\n")
    return "".join(lines) if lines else None


def check_context(raw: str) -> str | None:
    """Why ``raw`` is not a mapping Runner's ``context`` takes, or None."""
    src = _Source("x: " + raw.strip() + "\n")
    tree = _parser().parse(src.data)
    if tree.root_node.has_error:
        return _('The context is not YAML: write a mapping, {a: 1, b: x}')
    top = _unwrap(next((c for c in tree.root_node.named_children if c.type == "document"), None))
    value = _unwrap(_pairs(top)[0].child_by_field_name("value")) if top is not None and _pairs(top) else None
    if value is None or value.type != "flow_mapping":
        return _('The context must be a mapping: {a: 1, b: x}')
    return None


def _value_text(key: str, value) -> str:
    if key == "pause":
        return "true" if value else "false"
    if key == "context":
        return str(value).strip()
    return render_scalar(str(value).strip())


def _unchanged(attr: Attr | None, key: str, value) -> bool:
    if attr is None:
        return value is None
    if value is None:
        return False
    if key == "pause":
        return attr.kind == "scalar" and str(attr.value).lower() == ("true" if value else "false")
    if key == "context":
        return " ".join(attr.text().split()) == " ".join(str(value).split())
    return attr.kind == "scalar" and str(attr.value) == str(value).strip()


def _merge(text: str, changes: list[Change]) -> Change:
    """Several changes as one replacement (one undo step): the text between them stays as written."""
    changes = sorted(changes, key=lambda c: (c.start, c.end))
    start, end = changes[0].start, max(c.end for c in changes)
    out, at = [], start
    for c in changes:
        if c.start < at:
            raise EditError(_('Two changes overlap: edit it in the code (Ctrl+T)'))
        out.append(text[at:c.start])
        out.append(c.text)
        at = c.end
    out.append(text[at:end])
    return Change(start, end, "".join(out))


def normalize(values: dict) -> dict:
    """The dialog's fields as values: empty text (or False for pause) removes the attribute."""
    out = {}
    for key in ATTRS:
        if key not in values:
            continue
        value = values[key]
        if key == "pause":
            out[key] = True if value is True else (None if value in (None, False, "") else value)
        else:
            out[key] = str(value).strip() or None
    return out


def edit_step(doc: FlowDoc, step: Step, values: dict) -> Change | None:
    """The one replacement that gives ``step`` these attribute values (None: nothing changes).
    ``values`` maps attributes of :data:`ATTRS` to text (``context``: a YAML mapping), True for
    ``pause``, or None to remove; attributes not in it stay."""
    if not doc.editable:
        raise EditError(_('The YAML has errors: fix them in the code first (Ctrl+T)'))
    if step.why is not None:
        raise EditError(_('{step} cannot be edited here: {why}').format(step=step.name, why=step.why))
    text = doc.text
    values = normalize(values)
    changes: list[Change] = []
    added: list[str] = []
    for key in ATTRS:
        if key not in values or _unchanged(step.attrs.get(key), key, values[key]):
            continue
        value, attr = values[key], step.attrs.get(key)
        if key == "context" and value is not None and (problem := check_context(value)):
            raise EditError(problem)
        if attr is None:
            added.append(f"{key}: {_value_text(key, value)}")
            continue
        if attr.why is not None:
            raise EditError(attr.why)
        if value is None:
            start, end = _whole_lines(text, attr.start, attr.end)
            changes.append(Change(start, end, ""))
        elif attr.kind == "mapping":  # a block mapping stays in block style
            first = text.find("\n", attr.key_end) + 1
            indent = _column(text, attr.value_start) if text[_line_start(text, attr.value_start):attr.value_start].strip() == "" else (step.attr_column or 0) + 2
            lines = _context_lines(value, indent)
            if lines is None:
                changes.append(Change(attr.key_end + 1, _line_after(text, attr.end) - 1, " " + str(value).strip()))
            else:
                changes.append(Change(first, _line_after(text, attr.end), lines))
        elif attr.kind == "empty":
            changes.append(Change(attr.key_end + 1, attr.key_end + 1, " " + _value_text(key, value)))
        else:
            changes.append(Change(attr.value_start, attr.value_end, _value_text(key, value)))
    if added:
        changes.append(_insert_attrs(text, step, added))
    if not changes:
        return None
    return _merge(text, changes)


def _insert_attrs(text: str, step: Step, lines: list[str]) -> Change:
    if step.style == "empty":  # ``step:`` and nothing yet
        indent = step.key_column + _unit(text, step)
        at = _line_after(text, step.key_end)
        if text[step.key_end:at].strip(" \t\r\n:") and not text[step.key_end:at].strip(" \t\r\n:").startswith("#"):
            raise EditError(_('{step} cannot be edited here: edit it in the code (Ctrl+T)').format(step=step.name))
    else:
        indent = step.attr_column if step.attr_column is not None else step.key_column + _unit(text, step)
        last = max(step.attrs.values(), key=lambda a: a.end)
        at = _line_after(text, last.end)
    prefix = "" if at == 0 or text[at - 1] == "\n" else "\n"
    return Change(at, at, prefix + "".join(" " * indent + line + "\n" for line in lines))


def _unit(text: str, step: Step) -> int:
    """How much deeper a Step's attributes are written than the Step: as its siblings', else 2."""
    return 2


def add_step(doc: FlowDoc, block: Block, after: Step | None, step_id: str, values: dict) -> Change:
    """New lines for a Step ``step_id`` after ``after`` (else at the end of ``block``)."""
    if not doc.editable:
        raise EditError(_('The YAML has errors: fix them in the code first (Ctrl+T)'))
    step_id = step_id.strip()
    if not STEP_ID.match(step_id):
        raise EditError(_('A Step id here is letters, digits, _ and -, starting with a letter or digit'))
    if block.step(step_id) is not None:
        raise EditError(_("Block '{block}' already has a Step '{step}'").format(block=block.id, step=step_id))
    text = doc.text
    if block.steps_style == "block" and block.steps:
        sibling = after or block.steps[-1]
        column = sibling.key_column
        attr_column = sibling.attr_column if sibling.attr_column is not None else column + 2
        anchor = after if after is not None else max(block.steps, key=lambda s: s.end)
        at = _line_after(text, max(anchor.end, anchor.key_end))
    elif block.steps_style in ("empty", "missing") and block.steps_key is not None:
        column = _column(text, block.steps_key[0]) + 2
        attr_column = column + 2
        at = _line_after(text, block.steps_key[1])
        if text[block.steps_key[1]:at].strip(" \t\r\n:") and not text[block.steps_key[1]:at].strip(" \t\r\n:").startswith("#"):
            raise EditError(_("Block '{block}' has its steps written another way: add it in the code (Ctrl+T)").format(block=block.id))
    else:
        raise EditError(_("Block '{block}' has no steps mapping to add to: add it in the code (Ctrl+T)").format(block=block.id))
    values = {k: v for k, v in normalize(values).items() if v is not None}
    if values.get("context") is not None and (problem := check_context(values["context"])):
        raise EditError(problem)
    body = "".join(" " * attr_column + f"{key}: {_value_text(key, values[key])}\n" for key in ATTRS if key in values)
    if not body:
        raise EditError(_('A Step needs something to do: an activity, a call, a jump, a pause...'))
    prefix = "" if at == 0 or text[at - 1] == "\n" else "\n"
    return Change(at, at, prefix + " " * column + step_id + ":\n" + body)


def delete_step(doc: FlowDoc, step: Step) -> Change:
    if not doc.editable:
        raise EditError(_('The YAML has errors: fix them in the code first (Ctrl+T)'))
    start, end = _whole_lines(doc.text, step.key_start, max(step.end, step.key_end))
    return Change(start, end, "")


def apply(text: str, change: Change) -> str:
    return text[:change.start] + change.text + text[change.end:]


def verify(before: FlowDoc, after_text: str, block_id: str, step_id: str | None, values: dict | None) -> str | None:
    """Why the edited text is not what was meant (None: it is): it still parses, the Step holds
    the values asked for, and its other attributes are written as they were."""
    after = parse(after_text)
    if after.problems and not before.problems:
        return after.problems[0].message
    if step_id is None:
        return None
    step = after.step(block_id, step_id)
    if values is None:
        return _('{name} is still there').format(name=f"{block_id}.{step_id}") if step is not None else None
    if step is None:
        return _('{name} is not found after the edit').format(name=f"{block_id}.{step_id}")
    values = normalize(values)
    old = before.step(block_id, step_id)
    for key in ATTRS:
        attr = step.attrs.get(key)
        if key in values:
            if not _unchanged(attr, key, values[key]):
                return _('{key} reads back differently').format(key=key)
        elif old is not None and (old.attrs.get(key) is None) != (attr is None):
            return _('{key} changed without being asked').format(key=key)
        elif old is not None and attr is not None and old.attrs[key].raw != attr.raw:
            return _('{key} changed without being asked').format(key=key)
    return None


# ---------------------------------------------------------------- diagnostics
@dataclass
class CheckResult:
    ok: bool | None  # None: Runner could not be asked
    error: str | None = None
    functions: frozenset[str] = frozenset()  # names PHP knows as functions


def runner_source(bootstrap: Path) -> Path:
    """Runner's single source file next to its bin/run.php."""
    return bootstrap.parent.parent / "src" / "runner.php"


async def check(runner_bootstrap: Path | None, text: str, name: str, names: list[str], *,
                php: str | None = None, timeout: float = 15.0) -> CheckResult:
    """Runner's verdict on the Flow ``text`` (saved as ``name`` in a temporary folder): its own
    parser, schema and target resolution, the generated code not evaluated."""
    php = php or shutil.which("php")
    if not php or runner_bootstrap is None:
        return CheckResult(None)
    source = runner_source(runner_bootstrap)
    with tempfile.TemporaryDirectory(prefix="divide-flow-") as work:
        flow = Path(work) / (name or "flow.yml")
        flow.write_text(text, encoding="utf-8")
        proc = children.track(await asyncio.create_subprocess_exec(
            php, "-d", "display_errors=stderr", "-d", "log_errors=0", str(CHECKER), str(source), str(flow),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            **children.options()))
        try:
            out, err = await asyncio.wait_for(proc.communicate(json.dumps(names).encode("utf-8")), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return CheckResult(None, _('Runner did not answer in {s}s').format(s=int(timeout)))
        try:
            answer = json.loads(out.decode("utf-8", "replace").strip().splitlines()[-1])
        except (ValueError, IndexError):
            return CheckResult(None, (err or out).decode("utf-8", "replace").strip() or _('Runner gave no answer'))
        error = answer.get("error")
        if isinstance(error, str):
            error = error.replace(str(flow), flow.name)
        return CheckResult(bool(answer.get("ok")), error, frozenset(n for n in answer.get("functions") or [] if isinstance(n, str)))


def function_names(doc: FlowDoc) -> list[str]:
    """The unqualified activity and condition names, for the checker to say which are PHP functions."""
    names = []
    for step in doc.steps():
        if step.get("module"):
            continue
        for key in FUNCTION_ATTRS:
            value = step.get(key)
            if value and value not in names:
                names.append(value)
    return names


def diagnose(doc: FlowDoc, functions: Functions | None, cwd: Path, result: CheckResult | None) -> list[Diagnostic]:
    """What is wrong, where it is written: the YAML's own problems, Runner's verdict, targets missing
    from the file, and function files missing where Runner's importer would look."""
    out = [Diagnostic(p.start, p.end, "error", p.message) for p in doc.problems]
    php_functions = result.functions if result is not None else frozenset()
    for step in doc.steps():
        for key in TARGET_ATTRS:
            attr = step.attrs.get(key)
            if attr is None or attr.kind != "scalar" or not str(attr.value).strip():
                continue
            _b, _s, problem = resolve_target(doc, step.block, str(attr.value))
            if problem:
                out.append(Diagnostic(attr.value_start, attr.value_end, "error", f"{key} {attr.value}: {problem}"))
        if functions is None:
            continue
        module = step.get("module") or None
        for key in FUNCTION_ATTRS:
            attr = step.attrs.get(key)
            if attr is None or attr.kind != "scalar" or not str(attr.value).strip():
                continue
            name = str(attr.value).strip()
            if module and module_problem(module, name):
                continue  # Runner's schema says why
            if functions.find(name, module, cwd) is not None:
                continue
            tried = ", ".join(_shown(p, cwd) for p in functions.candidates(name, module, cwd))
            if module:
                out.append(Diagnostic(attr.value_start, attr.value_end, "error",
                                      _('{key} {module}:{name}: no file {tried}').format(key=key, module=module, name=name, tried=tried)))
            elif name in php_functions:
                continue
            elif result is not None and result.ok is not None and "::" not in name and "\\" not in name:
                out.append(Diagnostic(attr.value_start, attr.value_end, "error",
                                      _('{key} {name}: no file {tried}, and PHP has no function {name}').format(key=key, name=name, tried=tried)))
            else:
                out.append(Diagnostic(attr.value_start, attr.value_end, "warning",
                                      _('{key} {name}: no file {tried}; Runner will try it as a PHP callable').format(key=key, name=name, tried=tried)))
    if result is not None and result.ok is False and result.error:
        out.extend(_runner_diagnostics(doc, result.error, out))
    out.sort(key=lambda d: (d.start, d.end))
    return out


def _shown(path: Path, cwd: Path) -> str:
    try:
        return path.relative_to(cwd).as_posix()
    except ValueError:
        return str(path)


def _runner_diagnostics(doc: FlowDoc, error: str, found: list[Diagnostic]) -> list[Diagnostic]:
    """Runner's message at what it names: a step, a block, a key, a line (else the start of the Flow)."""
    head, _sep, rest = error.partition(": ")
    parts = [p.strip().rstrip(".") for p in rest.split("; ")] if error.startswith("Invalid YAML flow '") and rest else [error.rstrip(".")]
    out = []
    for part in parts:
        message = "Runner: " + part
        for start, end in _places(doc, part):
            # a lookup already says it there (a missing target): Runner's words stay in the verdict
            if not any(d.start == start and d.severity == "error" for d in found + out):
                out.append(Diagnostic(start, end, "error", message))
    return out


def _places(doc: FlowDoc, message: str) -> list[tuple[int, int]]:
    text = doc.text
    if m := re.search(r"near line (\d+)", message):
        line = int(m.group(1))
        lines = text.split("\n")
        start = sum(len(x) + 1 for x in lines[: line - 1])
        return [(start, start + max(1, len(lines[line - 1]) if line - 1 < len(lines) else 1))]
    if m := re.search(r"target (block|step) '([^']*)' not found(?: in block '([^']*)')?", message):
        kind, name, in_block = m.groups()
        kind_attr = "call" if message.lower().startswith("call") else "jump" if message.lower().startswith("jump") else None
        places = []
        for step in doc.steps():
            for key in (kind_attr,) if kind_attr else TARGET_ATTRS:
                attr = step.attrs.get(key)
                if attr is None or attr.kind != "scalar":
                    continue
                target_block, _dot, target_step = str(attr.value).partition(".")
                target_block = target_block.strip() or step.block
                if (kind == "block" and target_block == name) or (kind == "step" and target_step.strip() == name and target_block == in_block):
                    places.append((attr.value_start, attr.value_end))
        if places:
            return places
    if m := re.search(r"step '([^'.]*)\.([^']*)'", message):
        step = doc.step(*m.groups())
        if step is not None:
            if k := re.search(r"(?:unknown key|') ?'?([A-Za-z_]+)'? in step", message):
                key = k.group(1)
                attr = step.attrs.get(key)
                if attr is not None:
                    return [(attr.key_start, attr.key_end)]
                for name, attr in step.attrs.items():  # an unknown key is not one of the attributes read
                    if name == key:
                        return [(attr.key_start, attr.key_end)]
                where = text.find(key + ":", step.key_end, step.end)
                if where >= 0:
                    return [(where, where + len(key))]
            return [(step.key_start, step.key_end)]
    if m := re.search(r"Step id '([^']*)' in block '([^']*)'|Duplicate step id '([^']*)' in block '([^']*)'", message):
        step_id, block_id = (m.group(1), m.group(2)) if m.group(1) is not None else (m.group(3), m.group(4))
        block = doc.block(block_id)
        if block is not None:
            same = [s for s in block.steps if s.id == step_id]
            if same:
                return [(same[-1].key_start, same[-1].key_end)]
    if m := re.search(r"[Bb]lock(?: id)? '([^']*)'", message):
        same = [b for b in doc.blocks if b.id == m.group(1)]
        if same:
            return [(same[-1].key_start, same[-1].key_end)]
    if m := re.search(r"unknown flow key '([^']*)'", message):
        where = re.search(r"(?m)^" + re.escape(m.group(1)) + r"\s*:", text)
        if where:
            return [(where.start(), where.start() + len(m.group(1)))]
    if doc.blocks_key is not None:
        return [doc.blocks_key]
    return [(0, max(1, text.find("\n") if text.find("\n") > 0 else len(text) or 1))]
