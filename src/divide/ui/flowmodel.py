"""The Flow window: a Runner Flow's Blocks and Steps over the same buffer as its YAML code.

Ctrl+T on a YAML Flow opens it in the code window's place (as on JSON, the
Data tree) and flips between the two, keeping the place: the Step under the
code's cursor, the line of the selected Step. The window never owns the Flow:
it reads the code editor's text (:mod:`divide.run.flowmodel`), and each
change made here is one edit of that text, which changes only what it must
(undo, redo, the modified mark and F2 work as in the code). Typing in the code
rebuilds the tree, keeping the selection.

Keys: arrows to move, Enter edits a Step (or opens a Block), Ins adds a Step,
Del deletes one, Ctrl+Enter goes to the ``call`` or ``jump`` target (or opens
the activity's file), Ctrl+T to the code, Alt+F9 checks, Ctrl+F9 runs the
Flow (the Run Flow dialog), F2 saves.

Validation is Runner's (its compiler, run without evaluating the Flow) plus the
targets and function files the lookups find missing: the same diagnostics as
the code editor's squiggles and the Messages window (:class:`FlowModelMixin`).
"""

from __future__ import annotations

from divide.i18n import _

import json
import textwrap
from pathlib import Path

from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, Tree
from textual.widgets.tree import TreeNode
from textual_vision.button import Button
from textual_vision.cluster import CheckBoxes
from textual_vision.constants import Command, OptionFlag
from textual_vision.group import TVViewMixin
from textual_vision.input_line import InputLine
from textual_vision.label import Label

from divide import themes
from divide.lang.div.diagnostics import Diagnostic
from divide.run import flowmodel as fm
from divide.run.flow import find_runner, is_flow
from divide.ui.dialogs import _Dialog, confirm, information
from divide.ui.filter import Filtered, FilteredTree
from divide.ui.history import HistoryInput
from divide.ui.windows import EditorWindow, HRule, VRule, _TVWindow

Key = tuple  # ("flow",) | ("block", id) | ("step", block, id)


def _style(kind: str):
    return themes.current().token_styles()[kind]


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _summary(step: fm.Step) -> str:
    """What a Step does, in a few words: ``activity compute_total``, ``call -> review.check``."""
    parts = []
    module = step.get("module")
    for key in ("condition", "activity"):
        value = step.get(key)
        if value:
            parts.append(f"{key} {module + ':' if module else ''}{value}")
    for key in ("call", "jump"):
        value = step.get(key)
        if value:
            parts.append(f"{key} -> {value}")
    if "context" in step.attrs:
        parts.append("context")
    if step.get("pause").lower() == "true":
        parts.append("pause")
    if step.why is not None:
        parts.append(_('(read-only)'))
    return ", ".join(parts)


# ---------------------------------------------------------------- the Step dialog
class StepDialog(_Dialog):
    """A Step's attributes: what the project declares is offered (Down) in each line."""

    DEFAULT_CSS = """
    StepDialog { width: 72; height: 24; }
    StepDialog InputLine { width: 1fr; }
    StepDialog CheckBoxes { width: 1fr; height: 1; }
    StepDialog .flow-note { height: 2; margin-top: 1; color: $text; background: $surface; }
    """

    def __init__(self, title: str, step: fm.Step | None, *, new_id: bool, offers: dict, note: str = "") -> None:
        super().__init__(title=title)
        self.new_id = new_id
        self.id_input = InputLine(max_len=128)
        self.inputs: dict[str, InputLine] = {}
        for key in fm.ATTRS:
            if key == "pause":
                continue
            line = InputLine(max_len=1024)
            line.data = step.get(key) if step is not None else ""
            self.inputs[key] = line
        self.pause = CheckBoxes([_('~P~ause the Flow after this Step')])
        self.pause.value = 1 if step is not None and step.get("pause").lower() == "true" else 0
        self.offers = offers
        self.note = note
        self.values: dict = {}
        self.step_id = ""
        if not new_id:
            self.styles.height = 22

    def compose_content(self) -> ComposeResult:
        if self.new_id:
            yield Label(_('Step ~i~d (letters, digits, _ and -)'), link=self.id_input)
            yield self.id_input
        labels = {"module": _('~M~odule (folder of the activity and condition; optional)'),
                  "condition": _('C~o~ndition (a function: the Step runs only when it returns true)'),
                  "activity": _('~A~ctivity (a function that does the work)'),
                  "call": _('~C~all block.step (and come back)'),
                  "jump": _('~J~ump block.step (and go on from there)'),
                  "context": _('Con~t~ext: set these values, a mapping {key: value, ...}')}
        for key, line in self.inputs.items():
            yield Label(labels[key], link=line)
            offer = self.offers.get(key)
            yield HistoryInput(line, f"flow-{key}", offer=offer) if offer is not None else line
        yield self.pause
        if self.note:
            yield Static(self.note, classes="flow-note", markup=False)
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('O~K~'), Command.OK, is_default=True, id="ok")
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        first = self.id_input if self.new_id else self.inputs["activity"] if not self.inputs["call"].data else self.inputs["call"]
        self.call_after_refresh(lambda: (first.tv_select_self(), first.select_all()))

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        if self.new_id:
            self.step_id = self.id_input.data.strip()
            if not fm.STEP_ID.match(self.step_id):
                self.app.notify(_('A Step id here is letters, digits, _ and -, starting with a letter or digit'), severity="error")
                return False
        context = self.inputs["context"].data.strip()
        if context and (problem := fm.check_context(context)):
            self.app.notify(problem, severity="error")
            return False
        module = self.inputs["module"].data.strip()
        if module and not (self.inputs["activity"].data.strip() or self.inputs["condition"].data.strip()):
            self.app.notify(_('A Module needs an activity or a condition'), severity="error")
            return False
        self.values = {key: line.data.strip() for key, line in self.inputs.items()}
        self.values["pause"] = bool(self.pause.value & 1)
        return True


# ---------------------------------------------------------------- the tree
class FlowTree(FilteredTree, Tree[Key], TVViewMixin):
    ICON_NODE = "► "  # Turbo Vision's own (CP437)
    ICON_NODE_EXPANDED = "▼ "
    DEFAULT_CSS = """
    FlowTree {
        background: $window-content-background;
        color: $foreground;
        scrollbar-size: 1 1;
        scrollbar-background: $secondary;
        scrollbar-color: $background;
        scrollbar-corner-color: $secondary;
        padding: 0;
        width: 1fr;
    }
    FlowTree > .tree--guides, FlowTree > .tree--guides-hover, FlowTree > .tree--guides-selected { color: $secondary; }
    FlowTree > .tree--cursor, FlowTree:focus > .tree--cursor { background: $secondary; text-style: none; }
    FlowTree > .tree--highlight, FlowTree > .tree--highlight-line { background: $window-content-background; }
    """
    BINDINGS = [
        Binding("enter", "edit", "Edit", show=False),
        Binding("left", "close_node", "Close", show=False),
        Binding("right", "open_node", "Open", show=False),
        Binding("insert", "add", "Add", show=False),
        Binding("delete", "delete", "Delete", show=False),
        Binding("ctrl+z", "undo", "Undo", show=False),
        Binding("ctrl+y", "redo", "Redo", show=False),
    ]

    def __init__(self) -> None:
        super().__init__("", data=("flow",))
        self.tv_options = OptionFlag.SELECTABLE
        self.guide_depth = 3
        self.auto_expand = False

    def _window(self) -> "FlowWindow":
        return next(a for a in self.ancestors if isinstance(a, FlowWindow))

    def action_edit(self) -> None:
        node = self.cursor_node
        if node is not None and node.data and node.data[0] != "step":
            node.toggle()
            return
        self._window().edit_step()

    def action_close_node(self) -> None:
        """Left: close the Block, or go up to it from one of its Steps."""
        node = self.cursor_node
        if node is None:
            return
        if node.allow_expand and node.is_expanded:
            node.collapse()
        elif node.parent is not None:
            self.move_cursor(node.parent)

    def action_open_node(self) -> None:
        """Right: open the Block, or go into its first Step."""
        node = self.cursor_node
        if node is None or not node.allow_expand:
            return
        if not node.is_expanded:
            node.expand()
        elif node.children:
            self.move_cursor(node.children[0])

    def action_add(self) -> None:
        self._window().add_step()

    def action_delete(self) -> None:
        self._window().delete_step()

    def action_undo(self) -> None:
        self._window().source.editor.undo()

    def action_redo(self) -> None:
        self._window().source.editor.redo()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self.tv_select_self()


class FlowWindow(_TVWindow):
    """Tree of a Flow's Blocks and Steps | what the selected one is, with Runner's verdict below."""

    HINT = _('Enter edit · Ins add · Del del · ^Enter go to · ^T code')
    DEFAULT_CSS = """
    FlowWindow .flow-left { width: 1fr; height: 1fr; }
    FlowWindow .flow-right { width: 48; height: 1fr; }
    FlowWindow .flow-inspector { width: 1fr; height: auto; padding: 0 1; background: $window-content-background; color: $foreground; }
    FlowWindow VerticalScroll { background: $window-content-background; scrollbar-size: 1 1; }
    FlowWindow .flow-verdict { height: 3; padding: 0 1; background: $window-content-background; color: $foreground; }
    """

    def __init__(self, source: EditorWindow, number: int = 0) -> None:
        self.source = source
        super().__init__(self._make_title(), number=number)
        self.flow_tree = FlowTree()
        self.inspector = Static("", classes="flow-inspector")
        self.verdict = Static(_('Asking Runner...'), classes="flow-verdict")
        self.doc = fm.parse(source.editor.text)
        self._built: str | None = None

    def _make_title(self) -> str:
        return f"Flow: {self.source.display_name}"

    def compose_content(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes="flow-left"):
                yield Filtered(self.flow_tree)
            yield VRule()
            with Vertical(classes="flow-right"):
                with VerticalScroll():
                    yield self.inspector
                yield HRule()
                yield self.verdict

    def on_mount(self) -> None:
        self.call_after_refresh(self.reload)
        self.call_after_refresh(self.flow_tree.focus)
        self.app.theme_changed_signal.subscribe(self, lambda _theme: self.rebuild())

    # ------------------------------------------------------------- sync
    @property
    def diagnostics(self) -> list[Diagnostic]:
        return list(self.source.editor.diagnostics)

    def reload(self) -> None:
        """Parse the source buffer again and rebuild the tree, keeping the cursor and what is open."""
        text = self.source.editor.text
        if text == self._built:
            self.show_selected()
            return
        self.doc = fm.parse(text)
        self.rebuild()

    def problems_in(self, start: int, end: int) -> list[Diagnostic]:
        return [d for d in self.diagnostics if start <= d.start < end]

    def _step_problems(self, step: fm.Step) -> list[Diagnostic]:
        return self.problems_in(step.key_start, max(step.end, step.key_end + 1))

    def _expanded(self) -> set[Key]:
        out: set[Key] = set()
        for node in self.flow_tree.root.children:
            if node.is_expanded and node.data is not None:
                out.add(node.data)
        return out

    def rebuild(self, cursor: Key | None = None) -> None:
        tree = self.flow_tree
        first = not tree.root.children
        expanded = self._expanded()
        if cursor is None and tree.cursor_node is not None:
            cursor = tree.cursor_node.data
        doc = self.doc
        self._built = doc.text
        tree.clear()
        tree.root.data = ("flow",)
        root_label = Text(_('Flow '), style=_style("div.comment"))
        root_label.append(doc.id or self.source.display_name, style=_style("json.key"))
        if doc.problems:
            root_label.append(_('  [YAML errors]'), style=_style("diag.error"))
        tree.root.set_label(root_label)
        target: list[TreeNode[Key]] = []
        for block in doc.blocks:
            key: Key = ("block", block.id)
            label = Text()
            bad = any(self._step_problems(s) for s in block.steps) or self.problems_in(block.key_start, block.key_end + 1)
            if bad:
                label.append("! ", style=_style("diag.error"))
            label.append(block.id, style=_style("json.key"))
            label.append(f"  ({len(block.steps)})", style=_style("div.comment"))
            node = tree.root.add(label, data=key, expand=first or key in expanded)
            if key == cursor:
                target.append(node)
            for step in block.steps:
                step_key: Key = ("step", block.id, step.id)
                label = Text()
                problems = self._step_problems(step)
                if problems:
                    worst = "diag.error" if any(p.severity == "error" for p in problems) else "diag.warning"
                    label.append("! ", style=_style(worst))
                label.append(step.id, style=_style("ts.yaml.field") if "ts.yaml.field" in themes.current().token_styles() else None)
                summary = _summary(step)
                if summary:
                    label.append("  " + summary, style=_style("div.comment"))
                leaf = node.add_leaf(label, data=step_key)
                if step_key == cursor:
                    target.append(leaf)
        tree.root.expand()
        if target:
            node = target[0]
            parent = node.parent
            while parent is not None:
                parent.expand()
                parent = parent.parent
            self.call_after_refresh(lambda: (tree.move_cursor(node), self.show_selected()))
        else:
            self.call_after_refresh(self.show_selected)

    def select(self, key: Key) -> None:
        self.rebuild(cursor=key)

    # ------------------------------------------------------------- the selection
    def selected(self) -> fm.Block | fm.Step | None:
        node = self.flow_tree.cursor_node
        data = node.data if node is not None else None
        if not data or data[0] == "flow":
            return None
        if data[0] == "block":
            return self.doc.block(data[1])
        return self.doc.step(data[1], data[2])

    def on_tree_node_highlighted(self, event) -> None:
        self.show_selected()

    def show_selected(self) -> None:
        if not self.is_mounted:
            return
        item = self.selected()
        doc = self.doc
        text = Text()
        key_style, dim = _style("json.key"), _style("div.comment")

        width = max(20, (self.inspector.size.width or 42) - 2)  # its padding

        def wrapped(value: str, first: int, indent: int) -> str:
            """``value`` broken to the panel's width, its later lines under its first word."""
            return textwrap.fill(value, width=width, initial_indent=" " * first, subsequent_indent=" " * indent,
                                 break_on_hyphens=False, break_long_words=False)

        def row(name: str, value: str, style=None) -> None:
            text.append(f"{name:<10} ", style=dim)
            text.append(wrapped(value, 11, 11)[11:] + "\n", style=style)

        def styled(lines: str, style) -> None:
            """Each line's indentation plain, its words in ``style`` (a red mark only under the words)."""
            for line in lines.split("\n"):
                words = line.lstrip(" ")
                text.append(line[:len(line) - len(words)])
                text.append(words, style=style)
                text.append("\n")

        def note(value: str, style=None) -> None:
            styled(wrapped(value, 11, 13), style if style is not None else dim)

        if isinstance(item, fm.Step):
            text.append(_('Step '), style=dim)
            text.append(item.name, style=key_style)
            text.append(_('  line {n}').format(n=_line_of(doc.text, item.key_start)) + "\n\n", style=dim)
            functions = self.app.flow_functions(self.source) if hasattr(self.app, "flow_functions") else None  # type: ignore[attr-defined]
            cwd = self.app.root  # type: ignore[attr-defined]
            module = item.get("module") or None
            for key in fm.STEP_KEYS:
                attr = item.attrs.get(key)
                if attr is None:
                    continue
                row(key, attr.text() or "''")
                if key in fm.TARGET_ATTRS and attr.kind == "scalar":
                    block, step, problem = fm.resolve_target(doc, item.block, str(attr.value))
                    if problem:
                        note("! " + problem, _style("diag.error"))
                    elif step is not None:
                        note(_('-> Block {block}, Step {step} (line {n})').format(block=block.id, step=step.id, n=_line_of(doc.text, step.key_start)))
                    elif block is not None:
                        note(_('-> Block {block} (no Steps)').format(block=block.id))
                elif key in fm.FUNCTION_ATTRS and attr.kind == "scalar" and functions is not None:
                    found = functions.find(str(attr.value), module, cwd)
                    if found is not None:
                        note("-> " + fm._shown(found, cwd))
            if item.why:
                text.append("\n" + _('Read-only: {why}').format(why=item.why) + "\n", style=_style("diag.warning"))
            problems = self._step_problems(item)
        elif isinstance(item, fm.Block):
            text.append(_('Block '), style=dim)
            text.append(item.id, style=key_style)
            text.append(_('  line {n}').format(n=_line_of(doc.text, item.key_start)) + "\n\n", style=dim)
            if item.description:
                text.append(item.description + "\n\n")
            row(_('steps'), ", ".join(s.id for s in item.steps) or _('(none)'))
            callers = [f"{s.name} ({k})" for s in doc.steps() for k in fm.TARGET_ATTRS
                       if s.attrs.get(k) is not None and s.attrs[k].kind == "scalar"
                       and fm.resolve_target(doc, s.block, str(s.attrs[k].value))[0] is item]
            row(_('entered'), ", ".join(callers) if callers else (_('first Block: the Flow starts here') if doc.blocks and doc.blocks[0] is item else _('from no Step')))
            problems = self.problems_in(item.key_start, item.key_end + 1)
        else:
            text.append(_('Flow '), style=dim)
            text.append((doc.id or self.source.display_name) + "\n\n", style=key_style)
            if doc.description:
                text.append(doc.description + "\n\n")
            row(_('blocks'), str(len(doc.blocks)))
            row(_('steps'), str(len(doc.steps())))
            if doc.blocks:
                row(_('starts at'), doc.blocks[0].id)
            problems = self.diagnostics
        if problems:
            text.append("\n")
            for p in problems[:30]:
                style = _style("diag.error") if p.severity == "error" else _style("diag.warning")
                styled(wrapped(f"! {_line_of(doc.text, p.start)}: {p.message}", 0, 2), style)
        self.inspector.update(text)

    def show_verdict(self, verdict: str, bad: bool) -> None:
        self.verdict.update(Text(verdict, style=_style("diag.error") if bad else None))

    # ------------------------------------------------------------- edits
    def _run(self, coro) -> None:
        self.app.run_worker(coro, group="flowmodel", exclusive=True)

    def _change(self, change: fm.Change, cursor: Key, check) -> None:
        """Write ``change`` into the code as one edit, then make sure it reads back as meant (else undo it)."""
        editor = self.source.editor
        doc = editor.document
        before = self.doc
        editor.replace(change.text, doc.get_location_from_index(change.start), doc.get_location_from_index(change.end),
                       maintain_selection_offset=False)
        problem = check(before, editor.text)
        if problem is not None:
            editor.undo()
            self.app.notify(_('The edit was undone: {problem}').format(problem=problem), severity="error", timeout=6)
        self.doc = fm.parse(editor.text)
        self.rebuild(cursor)

    async def _can_edit(self) -> bool:
        if self.doc.problems:
            await self.app.run_dialog(information(  # type: ignore[attr-defined]
                _('Flow'), _('Fix the YAML in the code first (Ctrl+T):\n{error}').format(error=self.doc.problems[0].message)))
            return False
        return True

    def _offers(self, module_hint: str = "") -> dict:
        app = self.app
        functions = app.flow_functions(self.source) if hasattr(app, "flow_functions") else None  # type: ignore[attr-defined]
        targets = [f"{s.block}.{s.id}" for s in self.doc.steps()] + [f"{b.id}." for b in self.doc.blocks]
        offers: dict = {"call": lambda: targets, "jump": lambda: targets}
        if functions is not None:
            def names(dialog_module=None):
                return functions.names(dialog_module or None)
            offers["module"] = functions.module_names
            offers["condition"] = offers["activity"] = lambda: names(self._dialog_module())
        return offers

    def _dialog_module(self) -> str:
        dialog = getattr(self.app.screen, "dialog", None)
        if isinstance(dialog, StepDialog):
            return dialog.inputs["module"].data.strip()
        return ""

    def edit_step(self) -> None:
        self._run(self._edit_step())

    async def _edit_step(self) -> None:
        step = self.selected()
        if not isinstance(step, fm.Step) or not await self._can_edit():
            return
        if step.why is not None:
            await self.app.run_dialog(information(_('Flow'), _('{step} cannot be edited here: {why}').format(step=step.name, why=step.why)))  # type: ignore[attr-defined]
            return
        odd = next((a.why for a in step.attrs.values() if a.why and a.key in fm.ATTRS), None)
        dialog = StepDialog(_('Step {name}').format(name=step.name), step, new_id=False, offers=self._offers(),
                            note=odd or _('An empty line removes the attribute. Only what you change is written.'))
        if await self.app.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        try:
            change = fm.edit_step(self.doc, step, dialog.values)
        except fm.EditError as exc:
            await self.app.run_dialog(information(_('Flow'), str(exc)))  # type: ignore[attr-defined]
            return
        if change is None:
            return
        block_id, step_id, values = step.block, step.id, dialog.values
        self._change(change, ("step", block_id, step_id), lambda before, text: fm.verify(before, text, block_id, step_id, values))

    def add_step(self) -> None:
        self._run(self._add_step())

    async def _add_step(self) -> None:
        item = self.selected()
        if not await self._can_edit():
            return
        if isinstance(item, fm.Step):
            block, after = self.doc.block(item.block), item
        elif isinstance(item, fm.Block):
            block, after = item, None
        else:
            await self.app.run_dialog(information(_('Flow'), _('Choose the Block (or the Step) to add the Step to.')))  # type: ignore[attr-defined]
            return
        if block is None:
            return
        where = _('after {step}').format(step=after.id) if after is not None else _('at the end of {block}').format(block=block.id)
        dialog = StepDialog(_('New Step in {block}').format(block=block.id), None, new_id=True, offers=self._offers(),
                            note=_('Written {where}, indented as its siblings.').format(where=where))
        if await self.app.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        try:
            change = fm.add_step(self.doc, block, after, dialog.step_id, dialog.values)
        except fm.EditError as exc:
            await self.app.run_dialog(information(_('Flow'), str(exc)))  # type: ignore[attr-defined]
            return
        block_id, step_id, values = block.id, dialog.step_id, dialog.values
        self._change(change, ("step", block_id, step_id), lambda before, text: fm.verify(before, text, block_id, step_id, values))

    def delete_step(self) -> None:
        self._run(self._delete_step())

    async def _delete_step(self) -> None:
        step = self.selected()
        if not isinstance(step, fm.Step) or not await self._can_edit():
            return
        callers = [s.name for s in self.doc.steps() for k in fm.TARGET_ATTRS
                   if s.attrs.get(k) is not None and s.attrs[k].kind == "scalar"
                   and fm.resolve_target(self.doc, s.block, str(s.attrs[k].value))[1] is step]
        warn = (" " + _('{callers} lead(s) to it.').format(callers=", ".join(callers))) if callers else ""
        try:
            notes = fm.comments_in(self.doc, *fm.step_lines(self.doc, step))
        except fm.EditError:
            notes = 0
        if notes:  # said before, never lost silently
            warn += " " + _('The {count} comment(s) written in it go with it.').format(count=notes)
        if await self.app.run_dialog(confirm(_('Delete Step'), _('Delete {name}?').format(name=step.name) + warn)) != Command.YES:  # type: ignore[attr-defined]
            return
        try:
            change = fm.delete_step(self.doc, step)
        except fm.EditError as exc:
            await self.app.run_dialog(information(_('Flow'), str(exc)))  # type: ignore[attr-defined]
            return
        block = self.doc.block(step.block)
        siblings = [s.id for s in block.steps] if block is not None else []
        index = siblings.index(step.id) if step.id in siblings else 0
        rest = [s for s in siblings if s != step.id]
        cursor: Key = ("step", step.block, rest[min(index, len(rest) - 1)]) if rest else ("block", step.block)
        block_id, step_id = step.block, step.id
        self._change(change, cursor, lambda before, text: fm.verify(before, text, block_id, step_id, None))

    # ------------------------------------------------------------- going places
    def source_range(self) -> tuple[int, int] | None:
        item = self.selected()
        if isinstance(item, (fm.Step, fm.Block)):
            return item.key_start, item.key_end
        return None

    def goto_target(self) -> bool:
        """Ctrl+Enter: the Step a call or jump leads to (in the tree), else the activity's or condition's file."""
        item = self.selected()
        if not isinstance(item, fm.Step):
            return False
        for key in fm.TARGET_ATTRS:
            attr = item.attrs.get(key)
            if attr is None or attr.kind != "scalar":
                continue
            block, step, problem = fm.resolve_target(self.doc, item.block, str(attr.value))
            if problem:
                self.app.notify(f"{key} {attr.value}: {problem}", severity="error", timeout=4)
                return True
            self.select(("step", block.id, step.id) if step is not None else ("block", block.id))
            return True
        return self.app.flow_open_function(self.source, item)  # type: ignore[attr-defined]


# ---------------------------------------------------------------- app side
class FlowModelMixin:
    """The Flow window, the checks of YAML Flows, and going to targets (mixed into the Divide app)."""

    def _flowmodel_init(self) -> None:
        self._flow_checks: dict[int, tuple[str, fm.CheckResult | None]] = {}  # editor id -> (text checked, verdict)

    def flow_windows(self) -> list[FlowWindow]:
        return [w for w in self.windows() if isinstance(w, FlowWindow)]  # type: ignore[attr-defined]

    @staticmethod
    def is_flow_editor(win) -> bool:
        return isinstance(win, EditorWindow) and win.editor.lang == "yaml" and is_flow(win.path or Path("untitled.yml"), win.editor.text)

    def flow_source(self) -> EditorWindow | None:
        """The YAML Flow the active window shows: its code window, or the code under a Flow window."""
        active = self.active_window()  # type: ignore[attr-defined]
        if isinstance(active, FlowWindow):
            return active.source
        return active if self.is_flow_editor(active) else None

    def open_flow_window(self, source: EditorWindow) -> FlowWindow:
        """Ctrl+T on a YAML Flow: its Flow window, in the code's place, at the Step under the cursor."""
        win = next((w for w in self.flow_windows() if w.source is source), None)
        ed = source.editor
        here = fm.parse(ed.text).at(ed.document.get_index_from_location(ed.selection.start))
        key: Key | None = (("step", here.block, here.id) if isinstance(here, fm.Step)
                           else ("block", here.id) if isinstance(here, fm.Block) else None)
        if win is None:
            win = FlowWindow(source, number=self._free_number())  # type: ignore[attr-defined]
            for attr in ("offset", "width", "height"):
                setattr(win.styles, attr, getattr(source.styles, attr))
            self.insert_window(win)  # type: ignore[attr-defined]
            if key is not None:
                self.call_after_refresh(lambda: win.select(key))  # type: ignore[attr-defined]
        else:
            self.raise_window(win)  # type: ignore[attr-defined]
            if key is not None:
                win.select(key)
        self.check_flow(ed)
        return win

    def flow_to_code(self, win: FlowWindow) -> None:
        """Ctrl+T in a Flow window: its code, with the selected Block or Step selected."""
        where = win.source_range()
        if where is None:
            self.raise_window(win.source)  # type: ignore[attr-defined]
            return
        self._select_in(win.source, *where)  # type: ignore[attr-defined]

    # ------------------------------------------------------------- functions
    def flow_functions(self, source: EditorWindow) -> fm.Functions | None:
        """The function root and Modules of the Flow's Run Flow settings (issue #1's dialog)."""
        from divide.ui.flow import flow_settings

        project = self.root  # type: ignore[attr-defined]
        if source.path is None:
            return fm.functions_for(project)
        settings = flow_settings(source.path.resolve())
        context: dict = {}
        given = settings["context"].strip()
        try:
            if given.startswith("{"):
                context = json.loads(given)
            elif given:
                path = Path(given).expanduser()
                path = path if path.is_absolute() else project / path
                if path.is_file():
                    context = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            context = {}
        return fm.functions_for(project, settings["root"], context if isinstance(context, dict) else {})

    def flow_open_function(self, source: EditorWindow, step: fm.Step) -> bool:
        functions = self.flow_functions(source)
        module = step.get("module") or None
        for key in fm.FUNCTION_ATTRS:
            name = step.get(key)
            if not name or functions is None:
                continue
            found = functions.find(name, module, self.root)  # type: ignore[attr-defined]
            if found is not None:
                self.open_file(found)  # type: ignore[attr-defined]
                return True
            tried = ", ".join(fm._shown(p, self.root) for p in functions.candidates(name, module, self.root))  # type: ignore[attr-defined]
            self.notify(_('{key} {name}: no file {tried}').format(key=key, name=name, tried=tried), severity="warning", timeout=4)  # type: ignore[attr-defined]
            return True
        self.notify(_('This Step has no call, jump, activity or condition to go to'), timeout=2)  # type: ignore[attr-defined]
        return True

    def flow_goto_in_code(self, win: EditorWindow) -> bool:
        """Ctrl+Enter in a Flow's code: on a call or jump, its target; on an activity or condition, its file."""
        ed = win.editor
        offset = ed.document.get_index_from_location(ed.selection.end)
        doc = fm.parse(ed.text)
        here = doc.at(offset)
        if not isinstance(here, fm.Step):
            return False
        line = ed.text.count("\n", 0, offset)
        for key in fm.TARGET_ATTRS + fm.FUNCTION_ATTRS:
            attr = here.attrs.get(key)
            if attr is None or attr.kind != "scalar" or ed.text.count("\n", 0, attr.key_start) != line:
                continue
            if key in fm.TARGET_ATTRS:
                block, step, problem = fm.resolve_target(doc, here.block, str(attr.value))
                if problem:
                    self.notify(f"{key} {attr.value}: {problem}", severity="error", timeout=4)  # type: ignore[attr-defined]
                else:
                    target = step or block
                    self._select_in(win, target.key_start, target.key_end)  # type: ignore[attr-defined]
                return True
            single = fm.Step(here.block, here.id, 0, 0, 0, 0, {k: v for k, v in here.attrs.items() if k in ("module", key)})
            return self.flow_open_function(win, single)
        return False

    # ------------------------------------------------------------- checks
    def check_flow(self, ed) -> None:
        """Runner's verdict and the lookups, as the editor's diagnostics (squiggles, Messages, the Flow window)."""
        self.run_worker(self._check_flow(ed), group=f"flowcheck-{id(ed)}", exclusive=True)

    async def _check_flow(self, ed) -> list[Diagnostic] | None:
        win = next((w for w in self.editor_windows() if w.editor is ed), None)  # type: ignore[attr-defined]
        if win is None or not self.is_flow_editor(win):
            if ed.lang == "yaml" and ed.diagnostics:
                ed.set_lint([])  # no longer a Flow: no Flow marks
            return None
        text = ed.text
        doc = fm.parse(text)
        runner = find_runner(self.root)  # type: ignore[attr-defined]
        result = await fm.check(runner.bootstrap if runner.usable else None, text,
                                win.path.name if win.path is not None else "flow.yml", fm.function_names(doc))
        if ed.text != text:
            return None
        found = fm.diagnose(doc, self.flow_functions(win), self.root, result)  # type: ignore[attr-defined]
        self._flow_checks[id(ed)] = (text, result)
        ed.set_lint(found)
        verdict, bad = self.flow_verdict(runner, result, found)
        for view in self.flow_windows():
            if view.source is win:
                view.rebuild()
                view.show_verdict(verdict, bad)
        self.refresh_messages()  # type: ignore[attr-defined]
        self.update_status()  # type: ignore[attr-defined]
        return found

    @staticmethod
    def flow_verdict(runner, result: fm.CheckResult | None, found: list[Diagnostic]) -> tuple[str, bool]:
        errors = sum(d.severity == "error" for d in found)
        warnings = len(found) - errors
        if not runner.usable:
            head = (runner.problem or _('Runner is not installed')) + "\n" + _('Only the lookups: no Runner to compile the Flow.')
        elif result is None or result.ok is None:
            head = _('Runner could not be asked: {why}').format(why=(result.error if result else None) or "php")
        elif result.ok:
            head = _('Runner {version}: the Flow compiles.').format(version=runner.version or "")
        else:
            head = _('Runner {version}: {error}').format(version=runner.version or "", error=result.error)
        counts = _('{errors} error(s), {warnings} warning(s)').format(errors=errors, warnings=warnings) if found else _('No problems found.')
        return head + "\n" + counts, bool(errors) or bool(result is not None and result.ok is False)
