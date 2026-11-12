"""Visual editor for Div JSON data: a tree over the same buffer as the code editor.

The tree never owns the data: it parses the code editor's text, and every
edit made in the tree is written back to that text as one edit (so the code
editor's undo / redo and dirty flag keep working). Typing in the code editor
rebuilds the tree, keeping the expanded nodes and the cursor.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Tree
from textual.widgets.tree import TreeNode
from textual_vision.button import Button
from textual_vision.cluster import RadioButtons
from textual_vision.constants import Command, OptionFlag
from textual_vision.group import TVViewMixin
from textual_vision.input_line import InputLine
from textual_vision.label import Label

from divide.editor.theme import TURBO_STYLES
from divide.lang import divjson
from divide.lang.divjson import Ref
from divide.ui.dialogs import _Dialog
from divide.ui.windows import EditorWindow, _TVWindow

Path_ = tuple
MAX_PREVIEW = 48


def _style(kind: str):
    return TURBO_STYLES[kind]


def scalar_text(value: Any) -> Text:
    """A value as it reads in the tree, in the editor's JSON colours."""
    if isinstance(value, Ref):
        return Text(str(value), style=_style("json.ref"))
    if isinstance(value, str):
        shown = value if len(value) <= MAX_PREVIEW else value[: MAX_PREVIEW - 1] + "…"
        return Text(divjson.dumps(shown), style=_style("json.string"))
    if isinstance(value, (dict, list)):
        return container_preview(value)
    return Text(divjson.dumps(value), style=_style("json.number" if isinstance(value, (int, float)) and not isinstance(value, bool) else "json.constant"))


def container_preview(value: dict | list) -> Text:
    """``{name: "Potato", price: 1.5, …}`` / ``[1, 2, …]`` cut to a readable width."""
    is_dict = isinstance(value, dict)
    punct = _style("json.punct")
    text = Text("{" if is_dict else "[", style=punct)
    items = list(value.items()) if is_dict else list(enumerate(value))
    for i, (key, child) in enumerate(items):
        if text.cell_len > MAX_PREVIEW:
            text.append("…", style=punct)
            break
        if i:
            text.append(", ", style=punct)
        if is_dict:
            text.append(str(key), style=_style("json.key"))
            text.append(": ", style=punct)
        if isinstance(child, dict):
            text.append(f"{{{len(child)}}}", style=punct)
        elif isinstance(child, list):
            text.append(f"[{len(child)}]", style=punct)
        else:
            text.append_text(scalar_text(child))
    text.append("}" if is_dict else "]", style=punct)
    return text


def node_label(key: Any, value: Any) -> Text:
    label = Text()
    if isinstance(key, str):
        label.append(key, style=_style("json.key"))
        label.append(": ", style=_style("json.punct"))
    elif isinstance(key, int):
        label.append(f"{key}: ", style=_style("div.comment"))
    label.append_text(scalar_text(value))
    return label


class EditItemDialog(_Dialog):
    """Key (object members), type and value of one item."""

    DEFAULT_CSS = """
    EditItemDialog { width: 60; height: 15; }
    EditItemDialog InputLine { width: 1fr; margin-bottom: 1; }
    EditItemDialog RadioButtons { width: 1fr; margin-bottom: 1; }
    """

    def __init__(self, title: str, *, key: str | None, value: Any, type_: str | None = None) -> None:
        super().__init__(title=title)
        self.has_key = key is not None
        self.key_input = InputLine(max_len=256)
        self.key_input.data = key or ""
        self.types = RadioButtons(["~S~tring", "~N~umber", "~T~rue", "~F~alse", "N~u~ll", "~R~eference", "~O~bject", "~A~rray"], columns=2)
        type_ = type_ or divjson.type_name(value)
        self.types.value = 1 << divjson.TYPES.index(type_)
        self.value_input = InputLine(max_len=4096)
        self.value_input.data = divjson.value_text(value)
        self.original = value  # not "current": Group.current is the focused child
        self.result_key: str | None = None
        self.result_value: Any = None
        if not self.has_key:
            self.styles.height = 12

    def compose_content(self) -> ComposeResult:
        if self.has_key:
            yield Label("~K~ey", link=self.key_input)
            yield self.key_input
        yield Label("T~y~pe", link=self.types)
        yield self.types
        yield Label("~V~alue (text, number or $reference)", link=self.value_input)
        yield self.value_input
        with Horizontal(classes="dlg-buttons"):
            yield Button("O~K~", Command.OK, is_default=True, id="ok")
            yield Button("Cancel", Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        first = self.key_input if self.has_key and not self.key_input.data else self.value_input
        self.call_after_refresh(lambda: (first.tv_select_self(), first.select_all()))

    def selected_type(self) -> str:
        bits = self.types.value
        return divjson.TYPES[bits.bit_length() - 1] if bits else "String"

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        key = self.key_input.data.strip()
        if self.has_key and not key:
            self.app.notify("The key is empty", severity="error")
            return False
        try:
            self.result_value = divjson.make_value(self.selected_type(), self.value_input.data, self.original)
        except ValueError as exc:
            self.app.notify(str(exc), severity="error")
            return False
        self.result_key = key if self.has_key else None
        return True


class JsonTree(Tree[Path_], TVViewMixin):
    DEFAULT_CSS = """
    JsonTree {
        background: $window-content-background;
        color: $foreground;
        scrollbar-size: 1 1;
        scrollbar-background: $secondary;
        scrollbar-color: $background;
        scrollbar-corner-color: $secondary;
        padding: 0;
    }
    JsonTree > .tree--guides, JsonTree > .tree--guides-hover, JsonTree > .tree--guides-selected { color: $secondary; }
    JsonTree > .tree--cursor, JsonTree:focus > .tree--cursor { background: $secondary; text-style: none; }
    JsonTree > .tree--highlight, JsonTree > .tree--highlight-line { background: $window-content-background; }
    """
    BINDINGS = [
        Binding("enter", "edit", "Edit", show=False),
        Binding("insert", "add", "Add", show=False),
        Binding("delete", "delete", "Delete", show=False),
        Binding("ctrl+up", "move(-1)", "Move up", show=False),
        Binding("ctrl+down", "move(1)", "Move down", show=False),
        Binding("ctrl+z", "undo", "Undo", show=False),
        Binding("ctrl+y", "redo", "Redo", show=False),
    ]

    def __init__(self) -> None:
        super().__init__("", data=())
        self.tv_options = OptionFlag.SELECTABLE
        self.guide_depth = 3

    def _window(self) -> "JsonTreeWindow":
        return self.parent.parent  # type: ignore[return-value]

    def action_edit(self) -> None:
        self._window().edit_item()

    def action_add(self) -> None:
        self._window().add_item()

    def action_delete(self) -> None:
        self._window().delete_item()

    def action_move(self, delta: int) -> None:
        self._window().move_item(delta)

    def action_undo(self) -> None:
        self._window().source.editor.undo()

    def action_redo(self) -> None:
        self._window().source.editor.redo()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self.tv_select_self()


class JsonTreeWindow(_TVWindow):
    """Tree view of a JSON editor window's buffer."""

    HINT = "Enter edit · Ins add · Del del · ^↑↓ move · ^T code"

    def __init__(self, source: EditorWindow, number: int = 0) -> None:
        self.source = source
        super().__init__(self._make_title(), number=number)
        self.json_tree = JsonTree()
        self.value: Any = None
        self.error: divjson.DivJsonError | None = None
        self._written: str | None = None  # text this window wrote last (its own echo is skipped)
        self._rewrite_ok = False

    def _make_title(self, invalid: bool = False) -> str:
        return f"Data: {self.source.display_name}" + (" [invalid JSON]" if invalid else "")

    def compose_content(self) -> ComposeResult:
        yield self.json_tree

    def on_mount(self) -> None:
        self.call_after_refresh(self.reload)

    # ------------------------------------------------------------- sync
    def reload(self) -> None:
        """Parse the source buffer and rebuild the tree, keeping expansion and cursor."""
        text = self.source.editor.text
        if text == self._written:
            return
        try:
            value = divjson.loads(text) if text.strip() else {}
        except divjson.DivJsonError as exc:
            self.error = exc
            self.title = self._make_title(invalid=True)
            return
        self.error = None
        self.title = self._make_title()
        self.value = value
        self.rebuild()

    def _expanded_paths(self) -> set[Path_]:
        out: set[Path_] = set()

        def walk(node: TreeNode[Path_]) -> None:
            if node.is_expanded:
                out.add(node.data or ())
                for child in node.children:
                    walk(child)

        walk(self.json_tree.root)
        return out

    def rebuild(self, cursor: Path_ | None = None) -> None:
        tree = self.json_tree
        expanded = self._expanded_paths() if tree.root.children else {()}
        if cursor is None and tree.cursor_node is not None:
            cursor = tree.cursor_node.data
        tree.clear()
        tree.root.data = ()
        tree.root.set_label(node_label(None, self.value))
        target: list[TreeNode[Path_]] = []

        def fill(node: TreeNode[Path_], value: Any, path: Path_) -> None:
            items = value.items() if isinstance(value, dict) else enumerate(value)
            for key, child in items:
                child_path = path + (key,)
                label = node_label(key, child)
                if isinstance(child, (dict, list)):
                    sub = node.add(label, data=child_path, expand=child_path in expanded)
                    fill(sub, child, child_path)
                else:
                    sub = node.add_leaf(label, data=child_path)
                if child_path == cursor:
                    target.append(sub)

        if isinstance(self.value, (dict, list)):
            fill(tree.root, self.value, ())
        tree.root.expand()
        if target:
            node = target[0]
            parent = node.parent
            while parent is not None:
                parent.expand()
                parent = parent.parent
            self.call_after_refresh(lambda: tree.move_cursor(node))

    async def _write(self, cursor: Path_) -> None:
        """Serialize the value into the source buffer as one edit."""
        editor = self.source.editor
        text = divjson.dumps(self.value) + "\n"
        self._written = text
        editor.replace(text, (0, 0), editor.document.end, maintain_selection_offset=False)
        self.rebuild(cursor)

    async def _can_edit(self) -> bool:
        app = self.app
        if self.error is not None:
            await app.run_dialog(  # type: ignore[attr-defined]
                _info("Data", f"Fix the JSON in the code editor first:\n{self.error}")
            )
            return False
        if not self._rewrite_ok and divjson.has_extensions(self.source.editor.text):
            from divide.ui.dialogs import MessageBox

            box = MessageBox(
                "Data",
                f"Visual editing rewrites {self.source.display_name} as standard JSON: comments, "
                "single quotes and unquoted keys are lost ($references are kept). Continue?",
                [("~Y~es", Command.YES, "yes"), ("~N~o", Command.NO, "no")],
                width=56,
            )
            if await app.run_dialog(box) != Command.YES:  # type: ignore[attr-defined]
                return False
        self._rewrite_ok = True
        return True

    def _cursor_path(self) -> Path_:
        node = self.json_tree.cursor_node
        return node.data if node is not None and node.data is not None else ()

    # ------------------------------------------------------------ edits
    def _run(self, coro) -> None:
        self.app.run_worker(coro, group="jsontree", exclusive=True)

    def edit_item(self) -> None:
        self._run(self._edit_item())

    async def _edit_item(self) -> None:
        if not await self._can_edit():
            return
        path = self._cursor_path()
        current = divjson.get_at(self.value, path)
        is_member = bool(path) and isinstance(path[-1], str)
        dialog = EditItemDialog("Edit item", key=path[-1] if is_member else None, value=current)
        if await self.app.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        try:
            if is_member and dialog.result_key != path[-1]:
                path = divjson.rename_key(self.value, path, dialog.result_key or "")
            self.value = divjson.set_at(self.value, path, dialog.result_value)
        except ValueError as exc:
            self.app.notify(str(exc), severity="error")
            return
        await self._write(path)

    def add_item(self) -> None:
        self._run(self._add_item())

    async def _add_item(self) -> None:
        if not await self._can_edit():
            return
        path = self._cursor_path()
        target = divjson.get_at(self.value, path)
        # On an object / array: append inside it. On a plain value: insert right after it.
        if isinstance(target, (dict, list)):
            container, after = path, None
        else:
            container, after = path[:-1], path[-1]
        parent = divjson.get_at(self.value, container)
        dialog = EditItemDialog("Add item", key="" if isinstance(parent, dict) else None, value="", type_="String")
        if await self.app.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        try:
            new_path = divjson.insert_after(self.value, container, after, dialog.result_key, dialog.result_value)
        except ValueError as exc:
            self.app.notify(str(exc), severity="error")
            return
        await self._write(new_path)

    def delete_item(self) -> None:
        self._run(self._delete_item())

    async def _delete_item(self) -> None:
        path = self._cursor_path()
        if not path or not await self._can_edit():
            return
        current = divjson.get_at(self.value, path)
        if isinstance(current, (dict, list)) and current:
            from divide.ui.dialogs import MessageBox

            box = MessageBox(
                "Delete",
                f"Delete {path[-1]!s} and its {len(current)} item(s)?",
                [("~Y~es", Command.YES, "yes"), ("~N~o", Command.NO, "no")],
                width=48,
            )
            if await self.app.run_dialog(box) != Command.YES:  # type: ignore[attr-defined]
                return
        divjson.delete_at(self.value, path)
        parent = divjson.get_at(self.value, path[:-1])
        if isinstance(parent, list) and parent:
            cursor = path[:-1] + (min(path[-1], len(parent) - 1),)
        else:
            cursor = path[:-1]
        await self._write(cursor)

    def move_item(self, delta: int) -> None:
        self._run(self._move_item(delta))

    async def _move_item(self, delta: int) -> None:
        path = self._cursor_path()
        if not path or not await self._can_edit():
            return
        new_path = divjson.move(self.value, path, delta)
        if new_path != path or isinstance(path[-1], str):
            await self._write(new_path)


def _info(title: str, text: str):
    from divide.ui.dialogs import information

    return information(title, text)
