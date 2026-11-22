"""Structural edits of a Runner Flow: Blocks and Steps added, renamed, moved and deleted in the YAML text (UI-independent).

The Flow Designer's operations, on top of :mod:`divide.run.flowmodel`: the YAML
text stays the only model, and each operation is planned as one replacement
(:class:`Plan`) that changes only what it must, then verified by reading the
result back (:meth:`Plan.check`), so a plan that would read back differently is
never kept.

- **A unit** is what is written for a Block or a Step: its lines, the comment
  lines right above it at its own indentation, and the comment lines after it
  indented deeper (:func:`unit`). Moving swaps two neighbouring units, text for
  text: nothing in them is rewritten, the blank lines and comments between
  them stay where they are.
- **Renaming** replaces the key's characters, and the characters of each
  ``call`` and ``jump`` value that leads to the renamed Block or Step
  (``block.step``, ``.step`` from its own Block, ``block.`` for a Block), in
  the quoting they are written in; their comments stay.
- **Deleting** removes the unit; the comments in it are counted, for the user
  to be told. A ``call`` or ``jump`` that leads to what is deleted is either
  removed with it (its own lines, when that removes no comment and leaves its
  Step with something to do) or the deletion is refused.
- **Adding** writes new lines, indented as their siblings.

What cannot be done that way (a key with something else on its line, a
reference written in flow style, a value with an anchor...) raises
:class:`~divide.run.flowmodel.EditError` and nothing is changed.
"""

from __future__ import annotations

from divide.i18n import _

from dataclasses import dataclass, field
from typing import Callable

from divide.run import flowmodel as fm
from divide.run.flowmodel import Block, Change, EditError, FlowDoc, Step

ID = fm.STEP_ID  # what a new Block or Step may be called here (Runner: no leading _, no dot)


# ---------------------------------------------------------------- references
@dataclass(frozen=True)
class Ref:
    """A ``call`` or ``jump`` written in a Step, and where it leads."""

    step: Step
    key: str  # call, jump
    attr: fm.Attr
    block_part: str  # as written, stripped: "" is the Step's own Block
    step_part: str  # "" is the Block's first Step
    block: Block | None  # where it leads (None: nowhere)
    target: Step | None

    @property
    def text(self) -> str:
        return f"{self.block_part}.{self.step_part}"

    def describe(self) -> str:
        return f"{self.step.name} ({self.key} {self.attr.value})"


def references(doc: FlowDoc) -> list[Ref]:
    """Every ``call`` and ``jump`` written as a plain value, in the order they are written."""
    out = []
    for step in doc.steps():
        for key in fm.TARGET_ATTRS:
            attr = step.attrs.get(key)
            if attr is None or attr.kind != "scalar" or not str(attr.value).strip():
                continue
            value = str(attr.value).strip()
            block_part, _dot, step_part = value.partition(".")
            block, target, _problem = fm.resolve_target(doc, step.block, value)
            out.append(Ref(step, key, attr, block_part.strip(), step_part.strip(), block, target))
    return out


def incoming(doc: FlowDoc, item: Block | Step) -> list[Ref]:
    """The references that lead to ``item``: to a Step by its name (``block.step``, ``.step``), or
    to a Block by any of them (``block.``, ``block.step``)."""
    if isinstance(item, Block):
        return [r for r in references(doc) if r.block is item]
    return [r for r in references(doc) if r.target is item]


# ---------------------------------------------------------------- plans
Outline = list  # [(block id, ((key, raw), ...), [(step id, ((key, raw), ...)), ...]), ...]


def _written(raw: str) -> str:
    """A value as written, without the blank and comment lines after it (tree-sitter gives the last
    value of a mapping the comment lines that follow it, which belong to what comes next; the
    comments are counted on their own)."""
    lines = raw.rstrip().split("\n")
    while len(lines) > 1 and (not lines[-1].strip() or lines[-1].strip().startswith("#")):
        lines.pop()
    return "\n".join(lines).rstrip()


def outline(doc: FlowDoc) -> Outline:
    """What the Flow holds, as written: each Block's own keys and Steps, each Step's keys and values."""
    return [[b.id, tuple((k, _written(a.raw)) for k, a in b.attrs.items()),
             [[s.id, tuple((k, _written(a.raw)) for k, a in s.attrs.items())] for s in b.steps]] for b in doc.blocks]


@dataclass
class Plan:
    """One replacement of the text, and what the text must read back as once it is made."""

    change: Change
    check: Callable[[str], str | None]  # the edited text -> why it is not what was meant (None: it is)
    lost_comments: int = 0  # comments written in what is deleted (said before, never silently)
    notes: list[str] = field(default_factory=list)  # what else changes: references rewritten or removed


def _verifier(before: FlowDoc, expected: Outline, lost: int = 0, *,
              described: tuple[str, str | None] | None = None) -> Callable[[str], str | None]:
    """The check of a plan: the text still parses, no comment is lost but the ``lost`` ones, and the
    Flow reads back as ``expected``. ``described``: (Block, description) whose description is new or
    gone, compared by value, its other keys as written."""
    def check(after_text: str) -> str | None:
        after = fm.parse(after_text)
        if after.problems and not before.problems:
            return after.problems[0].message
        if len(after.comments) != len(before.comments) - lost:
            return _('a comment would be lost')
        if (after.id, after.description) != (before.id, before.description):
            return _("the Flow's id or description would change")
        got = outline(after)
        if [b[0] for b in got] != [b[0] for b in expected]:
            return _('the Blocks would read back as {got}').format(got=", ".join(b[0] for b in got) or "-")
        for mine, theirs in zip(got, expected):
            if described is not None and mine[0] == described[0]:
                block = after.block(mine[0])
                if (block.description or None) != described[1] or ("description" in block.attrs) != (described[1] is not None):
                    return _("{block}'s description reads back differently").format(block=mine[0])
                mine = [mine[0], tuple(p for p in mine[1] if p[0] != "description"), mine[2]]
                theirs = [theirs[0], tuple(p for p in theirs[1] if p[0] != "description"), theirs[2]]
            if list(mine) != list(theirs):
                return _('Block {block} would read back differently').format(block=mine[0])
        return None
    return check


def _expected(doc: FlowDoc) -> Outline:
    return [[b, attrs, [list(s) for s in steps]] for b, attrs, steps in outline(doc)]


def _set_raw(expected: Outline, block_id: str, step_id: str, key: str, raw: str | None) -> None:
    for b in expected:
        if b[0] != block_id:
            continue
        for s in b[2]:
            if s[0] == step_id:
                pairs = [(k, v) for k, v in s[1] if k != key or raw is not None]
                s[1] = tuple((k, raw if k == key else v) for k, v in pairs)
                return


def as_change(before: str, after: str) -> Change | None:
    """The one replacement that turns ``before`` into ``after``: what lies between their common start and end."""
    if before == after:
        return None
    start = 0
    limit = min(len(before), len(after))
    while start < limit and before[start] == after[start]:
        start += 1
    end = 0
    while end < limit - start and before[len(before) - 1 - end] == after[len(after) - 1 - end]:
        end += 1
    return Change(start, len(before) - end, after[start:len(after) - end])


def chain(doc: FlowDoc, *steps: Callable[[FlowDoc], Plan | None]) -> Plan | None:
    """Several plans made one after the other, as one replacement (one undo step). Each one is
    checked on its own result before the next one is planned; the last one checks the whole."""
    text = doc.text
    current = doc
    last: Plan | None = None
    lost, notes = 0, []
    for make in steps:
        plan = make(current)
        if plan is None:
            continue
        after = fm.apply(current.text, plan.change)
        problem = plan.check(after)
        if problem is not None:
            raise EditError(_('The edit was not made: {problem}').format(problem=problem))
        lost += plan.lost_comments
        notes += plan.notes
        current, last = fm.parse(after), plan
    if last is None:
        return None
    change = as_change(text, current.text)
    if change is None:
        return None
    return Plan(change, last.check, lost, notes)


# ---------------------------------------------------------------- units
def _editable(doc: FlowDoc) -> None:
    if not doc.editable:
        raise EditError(_('The YAML has errors: fix them in the code first (Ctrl+T)'))


def _line_end(text: str, offset: int) -> int:
    end = text.find("\n", offset)
    return len(text) if end < 0 else end + 1


def unit(doc: FlowDoc, item: Block | Step) -> tuple[int, int]:
    """Where ``item`` is written: its lines, the comment lines right above it at its indentation
    and the comment lines after it indented deeper."""
    text = doc.text
    start = fm._line_start(text, item.key_start)
    if text[start:item.key_start].strip():
        raise EditError(_('{name} has something else written on its line: change it in the code (Ctrl+T)').format(
            name=_name(item)))
    column = item.key_column
    while start > 0:
        above = fm._line_start(text, start - 1)
        line = text[above:start].rstrip("\r\n")
        words = line.lstrip(" ")
        if words.startswith("#") and len(line) - len(words) == column:
            start = above
        else:
            break
    end = fm._line_after(text, _content_end(doc, item))
    while end < len(text):
        line_end = _line_end(text, end)
        line = text[end:line_end].rstrip("\r\n")
        words = line.lstrip(" ")
        if words.startswith("#") and len(line) - len(words) > column:
            end = line_end
        else:
            break
    return start, end


def _content_end(doc: FlowDoc, item: Block | Step) -> int:
    """Where what is written for ``item`` ends: tree-sitter counts the comment lines after it in its
    span, but one at its own indentation (or less) is about what follows."""
    text = doc.text
    end = max(item.end, item.key_end)
    while True:
        last = end
        while last > 0 and text[last - 1] in " \t\r\n":
            last -= 1
        comment = next((c for c in doc.comments if c[0] < last <= c[1]), None)
        if comment is None:
            return last
        line = fm._line_start(text, comment[0])
        if text[line:comment[0]].strip() or comment[0] - line > item.key_column or line <= item.key_start:
            return last
        end = line


def _name(item: Block | Step) -> str:
    return item.name if isinstance(item, Step) else item.id


def _between(text: str) -> bool:
    """Only blank lines and comments: what may lie between two neighbours that swap places."""
    return all(not line.strip() or line.strip().startswith("#") for line in text.split("\n"))


def _swap(doc: FlowDoc, first: Block | Step, second: Block | Step) -> Change:
    """``first`` and ``second`` (written in that order, neighbours) trade places, text for text."""
    if first.key_column != second.key_column:
        raise EditError(_('{a} and {b} are not indented alike: move them in the code (Ctrl+T)').format(
            a=_name(first), b=_name(second)))
    text = doc.text
    a0, a1 = unit(doc, first)
    b0, b1 = unit(doc, second)
    if not a1 <= b0:
        raise EditError(_('{a} and {b} overlap: move them in the code (Ctrl+T)').format(a=_name(first), b=_name(second)))
    a, mid, b = text[a0:a1], text[a1:b0], text[b0:b1]
    if not _between(mid):
        raise EditError(_('Something is written between {a} and {b}: move them in the code (Ctrl+T)').format(
            a=_name(first), b=_name(second)))
    if not b.endswith("\n"):  # the last line of the file: it keeps having no newline
        b += "\n"
        a = a[:-1] if a.endswith("\n") else a
    return Change(a0, b1, b + mid + a)


def _quoted_like(raw: str, value: str) -> str:
    """``value`` in the quoting ``raw`` is written in (plain when that reads back the same)."""
    raw = raw.strip()
    if raw.startswith('"'):
        import json
        return json.dumps(value, ensure_ascii=False)
    if raw.startswith("'"):
        return "'" + value.replace("'", "''") + "'"
    return fm.render_scalar(value)


def _check_id(new_id: str, what: str) -> str:
    new_id = new_id.strip()
    if not ID.match(new_id):
        raise EditError(_('A {what} id here is letters, digits, _ and -, starting with a letter or digit').format(what=what))
    return new_id


def _retarget(ref: Ref, value: str) -> Change:
    if ref.attr.why is not None or ref.step.why is not None:
        raise EditError(_('{ref} cannot be changed here: {why}').format(ref=ref.describe(), why=ref.attr.why or ref.step.why))
    raw = ref.attr.raw.strip()
    return Change(ref.attr.value_start, ref.attr.value_end,
                  _quoted_like(raw, value) if raw[:1] in "'\"" else fm.render_target(value))


def _unlink(doc: FlowDoc, ref: Ref) -> Change:
    """The lines of a reference, removed: only when they carry no comment and the Step keeps something to do."""
    if ref.step.why is not None or ref.attr.why is not None:
        raise EditError(_('{ref} cannot be removed here: {why}').format(ref=ref.describe(), why=ref.step.why or ref.attr.why))
    if not [k for k in ref.step.attrs if k != ref.key and k != "description"]:
        raise EditError(_('{step} would have nothing left to do: change or delete it first').format(step=ref.step.name))
    start, end = fm._whole_lines(doc.text, ref.attr.start, ref.attr.end)
    if fm.comments_in(doc, start, end):
        raise EditError(_('{ref} has a comment on its line: remove it in the code (Ctrl+T)').format(ref=ref.describe()))
    return Change(start, end, "")


# ---------------------------------------------------------------- moving
def move_step(doc: FlowDoc, step: Step, delta: int) -> Plan:
    """``step`` one place earlier (-1) or later (+1) in its Block: execution order."""
    _editable(doc)
    block = doc.block(step.block)
    if block is None or block.steps_style != "block":
        raise EditError(_("Block '{block}' has its steps written another way: move it in the code (Ctrl+T)").format(block=step.block))
    index = block.steps.index(step)
    other = index + delta
    if not 0 <= other < len(block.steps):
        raise EditError((_('{step} is already the first Step') if delta < 0 else _('{step} is already the last Step')).format(step=step.name))
    first, second = sorted((index, other))
    change = _swap(doc, block.steps[first], block.steps[second])
    expected = _expected(doc)
    for b in expected:
        if b[0] == block.id:
            b[2][first], b[2][second] = b[2][second], b[2][first]
    return Plan(change, _verifier(doc, expected))


def move_block(doc: FlowDoc, block: Block, delta: int) -> Plan:
    """``block`` one place earlier or later: the first Block is where the Flow starts."""
    _editable(doc)
    index = doc.blocks.index(block)
    other = index + delta
    if not 0 <= other < len(doc.blocks):
        raise EditError((_('{block} is already the first Block') if delta < 0 else _('{block} is already the last Block')).format(block=block.id))
    first, second = sorted((index, other))
    change = _swap(doc, doc.blocks[first], doc.blocks[second])
    expected = _expected(doc)
    expected[first], expected[second] = expected[second], expected[first]
    return Plan(change, _verifier(doc, expected))


def first_step_refs(doc: FlowDoc, block: Block) -> list[Ref]:
    """The references written ``block.`` (the Block's first Step, whichever it is)."""
    return [r for r in references(doc) if r.block is block and not r.step_part]


# ---------------------------------------------------------------- renaming
def rename_step(doc: FlowDoc, step: Step, new_id: str) -> Plan | None:
    """``step`` called ``new_id``, and every ``call`` and ``jump`` that names it with it."""
    _editable(doc)
    new_id = _check_id(new_id, _('Step'))
    if new_id == step.id:
        return None
    block = doc.block(step.block)
    if block is None:
        raise EditError(_('{step} is not found').format(step=step.name))
    if block.step(new_id) is not None:
        raise EditError(_("Block '{block}' already has a Step '{step}'").format(block=block.id, step=new_id))
    if sum(1 for s in block.steps if s.id == step.id) > 1:
        raise EditError(_("Block '{block}' has two Steps '{step}': rename them in the code (Ctrl+T)").format(block=block.id, step=step.id))
    key_raw = doc.text[step.key_start:step.key_end]
    changes = [Change(step.key_start, step.key_end, _quoted_like(key_raw, new_id))]
    expected = _expected(doc)
    notes = []
    for ref in references(doc):
        if ref.target is step and ref.step_part == step.id:
            value = f"{ref.block_part}.{new_id}"
            change = _retarget(ref, value)
            changes.append(change)
            _set_raw(expected, ref.step.block, ref.step.id, ref.key, change.text)
            notes.append(f"{ref.step.name} {ref.key} {value}")
    for b in expected:
        if b[0] == block.id:
            for s in b[2]:
                if s[0] == step.id:
                    s[0] = new_id
    return Plan(fm._merge(doc.text, changes), _verifier(doc, expected), notes=notes)


def rename_block(doc: FlowDoc, block: Block, new_id: str) -> Plan | None:
    """``block`` called ``new_id``, and every ``call`` and ``jump`` that names it with it (``.step``
    from inside it names no Block and stays)."""
    _editable(doc)
    new_id = _check_id(new_id, _('Block'))
    if new_id == block.id:
        return None
    if doc.block(new_id) is not None:
        raise EditError(_("The Flow already has a Block '{block}'").format(block=new_id))
    if sum(1 for b in doc.blocks if b.id == block.id) > 1:
        raise EditError(_("The Flow has two Blocks '{block}': rename them in the code (Ctrl+T)").format(block=block.id))
    key_raw = doc.text[block.key_start:block.key_end]
    changes = [Change(block.key_start, block.key_end, _quoted_like(key_raw, new_id))]
    expected = _expected(doc)
    notes = []
    for ref in references(doc):
        if ref.block is block and ref.block_part == block.id:
            value = f"{new_id}.{ref.step_part}"
            change = _retarget(ref, value)
            changes.append(change)
            _set_raw(expected, ref.step.block, ref.step.id, ref.key, change.text)
            notes.append(f"{ref.step.name} {ref.key} {value}")
    for b in expected:
        if b[0] == block.id:
            b[0] = new_id
    return Plan(fm._merge(doc.text, changes), _verifier(doc, expected), notes=notes)


# ---------------------------------------------------------------- a Block's description
def edit_block(doc: FlowDoc, block: Block, description: str | None) -> Plan | None:
    """``block``'s description set (replacing only its characters), added (one line, before
    ``steps:``) or removed (its own lines, when they carry no comment)."""
    _editable(doc)
    description = (description or "").strip() or None
    attr = block.attrs.get("description")
    text = doc.text
    if attr is None and description is None:
        return None
    if attr is not None and description is not None and attr.kind == "scalar" and str(attr.value) == description:
        return None
    if attr is not None and attr.why is not None:
        raise EditError(attr.why)
    if attr is not None and attr.kind not in ("scalar", "empty"):
        raise EditError(_("{block}'s description is written in a way divide does not edit: edit it in the code (Ctrl+T)").format(block=block.id))
    if description is None:
        start, end = fm._whole_lines(text, attr.start, attr.end)
        if fm.comments_in(doc, start, end):
            raise EditError(_('This change would remove a comment written there: make it in the code (Ctrl+T)'))
        change, raw = Change(start, end, ""), None
    elif attr is None:
        if block.steps_key is not None:
            at = fm._line_start(text, block.steps_key[0])
            if text[at:block.steps_key[0]].strip():
                raise EditError(_("Block '{block}' has its steps written another way: add it in the code (Ctrl+T)").format(block=block.id))
            column = block.steps_key[0] - at
        else:
            at = fm._line_after(text, block.key_end)
            column = block.key_column + 2
        raw = fm.render_scalar(description)
        prefix = "" if at == 0 or text[at - 1] == "\n" else "\n"
        change = Change(at, at, prefix + " " * column + f"description: {raw}\n")
    elif attr.kind == "empty":
        raw = fm.render_scalar(description)
        change = Change(attr.key_end + 1, attr.key_end + 1, " " + raw)
    else:
        raw = _quoted_like(attr.raw, description)
        change = Change(attr.value_start, attr.value_end, raw)
    return Plan(change, _verifier(doc, _expected(doc), described=(block.id, description)))


# ---------------------------------------------------------------- deleting
def delete_step(doc: FlowDoc, step: Step, *, unlink: bool = False) -> Plan:
    """``step``'s unit removed. The references that name it are removed too when ``unlink``
    (else the deletion is refused while there are any)."""
    _editable(doc)
    block = doc.block(step.block)
    start, end = unit(doc, step)
    refs = [r for r in incoming(doc, step) if r.step_part and r.step is not step]
    if refs and not unlink:
        raise EditError(_('{refs} lead(s) to {step}').format(refs=", ".join(r.describe() for r in refs), step=step.name))
    changes = [Change(start, end, "")]
    expected = _expected(doc)
    notes = []
    for ref in refs:
        changes.append(_unlink(doc, ref))
        _set_raw(expected, ref.step.block, ref.step.id, ref.key, None)
        notes.append(f"{ref.step.name}: {ref.key} {ref.attr.value}")
    for b in expected:
        if block is not None and b[0] == block.id:
            b[2] = [s for s in b[2] if s[0] != step.id]
    if block is not None and block.steps and block.steps[0] is step:
        following = block.steps[1].id if len(block.steps) > 1 else None
        for ref in first_step_refs(doc, block):
            if ref.step is not step:
                notes.append(_('{ref} now leads to {step}').format(ref=ref.describe(), step=f"{block.id}.{following}")
                             if following else _('{ref} leads to a Block without Steps').format(ref=ref.describe()))
    lost = fm.comments_in(doc, start, end)
    return Plan(fm._merge(doc.text, changes), _verifier(doc, expected, lost), lost, notes)


def delete_block(doc: FlowDoc, block: Block, *, unlink: bool = False) -> Plan:
    """``block``'s unit removed (never the only Block); the references from other Blocks that lead
    into it removed too when ``unlink`` (else refused while there are any)."""
    _editable(doc)
    if len(doc.blocks) == 1:
        raise EditError(_('A Flow needs a Block: {block} is the only one').format(block=block.id))
    start, end = unit(doc, block)
    refs = [r for r in incoming(doc, block) if r.step.block != block.id]
    if refs and not unlink:
        raise EditError(_('{refs} lead(s) into {block}').format(refs=", ".join(r.describe() for r in refs), block=block.id))
    changes = [Change(start, end, "")]
    expected = [b for b in _expected(doc) if b[0] != block.id]
    notes = []
    for ref in refs:
        changes.append(_unlink(doc, ref))
        _set_raw(expected, ref.step.block, ref.step.id, ref.key, None)
        notes.append(f"{ref.step.name}: {ref.key} {ref.attr.value}")
    lost = fm.comments_in(doc, start, end)
    return Plan(fm._merge(doc.text, changes), _verifier(doc, expected, lost), lost, notes)


# ---------------------------------------------------------------- adding
def add_block(doc: FlowDoc, after: Block | None, block_id: str, step_id: str, values: dict,
              description: str = "") -> Plan:
    """A new Block ``block_id`` with its first Step, written after ``after`` (else after the last
    Block, else under an empty ``blocks:``), indented as the other Blocks."""
    _editable(doc)
    block_id = _check_id(block_id, _('Block'))
    step_id = _check_id(step_id, _('Step'))
    if doc.block(block_id) is not None:
        raise EditError(_("The Flow already has a Block '{block}'").format(block=block_id))
    text = doc.text
    model = after or (doc.blocks[-1] if doc.blocks else None)
    if model is not None:
        column = model.key_column
        steps_off, step_off, attr_off = 2, 2, 2  # as the Blocks already written, else two spaces a level
        sample = next((b for b in [model] + doc.blocks if b.steps_key is not None and b.steps), None)
        if sample is not None:
            steps_col = _column_of(text, sample.steps_key[0])
            steps_off = max(1, steps_col - sample.key_column)
            step_off = max(1, sample.steps[0].key_column - steps_col)
            if sample.steps[0].attr_column is not None:
                attr_off = max(1, sample.steps[0].attr_column - sample.steps[0].key_column)
        steps_column = column + steps_off
        step_column = steps_column + step_off
        attr_column = step_column + attr_off
        at = unit(doc, model)[1]
    elif doc.blocks_key is not None:
        at = fm._line_after(text, doc.blocks_key[1])
        rest = text[doc.blocks_key[1]:at].strip(" \t\r\n:")
        if rest and not rest.startswith("#"):
            raise EditError(_('The blocks are written another way: add the Block in the code (Ctrl+T)'))
        column = _column_of(text, doc.blocks_key[0]) + 2
        steps_column, step_column, attr_column = column + 2, column + 4, column + 6
    else:
        raise EditError(_('The Flow has no blocks: write blocks: in the code first (Ctrl+T)'))
    values = {k: v for k, v in fm.normalize(values).items() if v is not None}
    if values.get("context") is not None and (problem := fm.check_context(values["context"])):
        raise EditError(problem)
    body = "".join(" " * attr_column + f"{key}: {fm._value_text(key, values[key])}\n" for key in fm.ATTRS if key in values)
    if not body:
        raise EditError(_('A Step needs something to do: an activity, a call, a jump, a pause...'))
    description = description.strip()
    lines = " " * column + block_id + ":\n"
    if description:
        lines += " " * steps_column + f"description: {fm.render_scalar(description)}\n"
    lines += " " * steps_column + "steps:\n" + " " * step_column + step_id + ":\n" + body
    prefix = "" if at == 0 or text[at - 1] == "\n" else "\n"
    change = Change(at, at, prefix + lines)
    after_doc = fm.parse(fm.apply(text, change))
    expected = _expected(doc)
    new = next((b for b in outline(after_doc) if b[0] == block_id), None)
    expected.insert(doc.blocks.index(model) + 1 if model is not None else 0, new)
    check = _verifier(doc, expected)

    def written(after: str) -> str | None:
        problem = check(after)
        if problem is not None:
            return problem
        mine = fm.parse(after).step(block_id, step_id)
        if mine is None:
            return _('{name} is not found after the edit').format(name=f"{block_id}.{step_id}")
        return _new_values(mine, values)
    return Plan(change, written)


def _column_of(text: str, offset: int) -> int:
    return offset - fm._line_start(text, offset)


def _new_values(step: Step, values: dict) -> str | None:
    for key in fm.ATTRS:
        if (key in values) != (key in step.attrs) or (key in values and not fm._unchanged(step.attrs[key], key, values[key])):
            return _('{key} reads back differently').format(key=key)
    return None


# ---------------------------------------------------------------- the step dialog's edit, as a plan
def edit_step(doc: FlowDoc, step: Step, values: dict) -> Plan | None:
    """:func:`divide.run.flowmodel.edit_step` as a plan."""
    change = fm.edit_step(doc, step, values)
    if change is None:
        return None
    block_id, step_id = step.block, step.id
    return Plan(change, lambda after: fm.verify(doc, after, block_id, step_id, values))


def set_target(doc: FlowDoc, step: Step, key: str, target: str | None) -> Plan | None:
    """``step``'s ``call`` or ``jump`` led to ``target`` (``block.step``, ``block.``), or removed (None)."""
    if key not in fm.TARGET_ATTRS:
        raise ValueError(key)
    return edit_step(doc, step, {key: target or ""})
