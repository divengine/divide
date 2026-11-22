"""A Step's context edited as data: a tree (the JSON editor's) or JSON text (the code editor), in one dialog.

The context is read from its YAML (``flowmodel.context_data``), edited on a copy,
and given back as a YAML flow mapping (``flowmodel.render_context``) only on OK;
writing it into the Flow is the Step edit's (which changes a block-style context
key by key, keeping its comments). Tree and JSON are two views of the same
value: switching parses the JSON (an error keeps you in the text).
"""

from __future__ import annotations

from divide.i18n import _

import json
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.constants import Command

from divide.lang import divjson
from divide.ui.dialogs import _Dialog, confirm
from divide.ui.jsontree import EditItemDialog, JsonTree, node_label
from divide.ui.windows import EditorView

CM_CONTEXT_TREE = Command.USER + 208
CM_CONTEXT_TEXT = Command.USER + 209


def plain(value: Any) -> Any:
    """Data the JSON editor may hold ($references) as plain data for a Flow's context."""
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class ContextTree(JsonTree):
    """The JSON editor's tree, over the dialog's copy of the context."""

    def _window(self):  # type: ignore[override]
        return next(a for a in self.ancestors if isinstance(a, ContextDialog))

    def action_undo(self) -> None:
        pass

    def action_redo(self) -> None:
        pass


class ContextDialog(_Dialog):
    """The context as a tree (Enter edits, Ins adds, Del deletes, Ctrl+Up/Down moves) or as JSON text."""

    DEFAULT_CSS = """
    ContextDialog { width: 76; height: 24; }
    ContextDialog .context-view { height: 1fr; }
    ContextDialog ContextTree { height: 1fr; background: $window-content-background; }
    ContextDialog EditorView { height: 1fr; }
    ContextDialog .context-hint { height: 1; color: $text; }
    """

    def __init__(self, title: str, value: dict) -> None:
        super().__init__(title=title)
        self.value: dict = plain(value)
        self.items = ContextTree()
        self.json_text = EditorView(json.dumps(self.value, indent=2, ensure_ascii=False), path=Path("context.json"))
        self.hint = Static("", classes="context-hint", markup=False)
        self.mode = "tree"
        self.result: dict | None = None

    def compose_content(self) -> ComposeResult:
        yield self.hint
        with Vertical(classes="context-view"):
            yield self.items
            yield self.json_text
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('O~K~'), Command.OK, is_default=True, id="ok")
            yield Button(_('T~r~ee'), CM_CONTEXT_TREE, id="tree")
            yield Button(_('~J~SON'), CM_CONTEXT_TEXT, id="json")
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.show("tree")

    # ------------------------------------------------------------ the two views
    def show(self, mode: str) -> None:
        self.mode = mode
        self.items.display = mode == "tree"
        self.json_text.display = mode == "text"
        if mode == "tree":
            self.hint.update(_('Enter edit · Ins add · Del delete · Ctrl+Up/Down move · Alt+J the JSON'))
            self.rebuild()
            self.call_after_refresh(self.items.tv_select_self)
        else:
            self.hint.update(_('The context as JSON: an object. Alt+R the tree'))
            self.json_text.load_text(json.dumps(self.value, indent=2, ensure_ascii=False))
            self.call_after_refresh(self.json_text.tv_select_self)

    def from_text(self) -> bool:
        """The JSON typed, as the value (an error is said, and the text stays)."""
        try:
            value = json.loads(self.json_text.text or "{}")
        except ValueError as exc:
            self.app.notify(_('Not JSON: {error}').format(error=exc), severity="error")
            return False
        if not isinstance(value, dict):
            self.app.notify(_('The context must be an object: {"key": "value"}'), severity="error")
            return False
        self.value = value
        return True

    def on_command_message(self, message) -> None:
        if message.command in (CM_CONTEXT_TREE, CM_CONTEXT_TEXT):
            message.stop()
            message.prevent_default()
            if message.command == CM_CONTEXT_TREE and self.mode == "text" and not self.from_text():
                return
            self.show("tree" if message.command == CM_CONTEXT_TREE else "text")

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        if self.mode == "text" and not self.from_text():
            return False
        self.result = self.value
        return True

    # ------------------------------------------------------------ the tree (what JsonTreeWindow does, on the copy)
    def rebuild(self, cursor: tuple | None = None) -> None:
        tree = self.items
        if cursor is None and tree.cursor_node is not None:
            cursor = tree.cursor_node.data
        tree.clear()
        tree.root.data = ()
        tree.root.set_label(node_label(None, self.value))
        target = []

        def fill(node, value, path) -> None:
            for key, child in (value.items() if isinstance(value, dict) else enumerate(value)):
                child_path = path + (key,)
                label = node_label(key, child)
                sub = node.add(label, data=child_path, expand=True) if isinstance(child, (dict, list)) else node.add_leaf(label, data=child_path)
                if isinstance(child, (dict, list)):
                    fill(sub, child, child_path)
                if child_path == cursor:
                    target.append(sub)

        fill(tree.root, self.value, ())
        tree.root.expand()
        if target:
            self.call_after_refresh(lambda: tree.move_cursor(target[0]))

    def _path(self) -> tuple:
        node = self.items.cursor_node
        return node.data if node is not None and node.data is not None else ()

    def _run(self, coro) -> None:
        self.run_worker(coro, exclusive=True)

    def edit_item(self) -> None:
        self._run(self._edit_item())

    async def _edit_item(self) -> None:
        path = self._path()
        if not path:
            await self._add_item()
            return
        current = divjson.get_at(self.value, path)
        is_member = isinstance(path[-1], str)
        dialog = EditItemDialog(_('Edit item'), key=path[-1] if is_member else None, value=current)
        if await self.app.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        try:
            if is_member and dialog.result_key != path[-1]:
                path = divjson.rename_key(self.value, path, dialog.result_key or "")
            self.value = divjson.set_at(self.value, path, plain(dialog.result_value))
        except ValueError as exc:
            self.app.notify(str(exc), severity="error")
            return
        self.rebuild(path)

    def add_item(self) -> None:
        self._run(self._add_item())

    async def _add_item(self) -> None:
        path = self._path()
        target = divjson.get_at(self.value, path)
        container, after = (path, None) if isinstance(target, (dict, list)) else (path[:-1], path[-1])
        parent = divjson.get_at(self.value, container)
        dialog = EditItemDialog(_('Add item'), key="" if isinstance(parent, dict) else None, value="", type_="String")
        if await self.app.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        try:
            new_path = divjson.insert_after(self.value, container, after, dialog.result_key, plain(dialog.result_value))
        except ValueError as exc:
            self.app.notify(str(exc), severity="error")
            return
        self.rebuild(new_path)

    def delete_item(self) -> None:
        self._run(self._delete_item())

    async def _delete_item(self) -> None:
        path = self._path()
        if not path:
            return
        current = divjson.get_at(self.value, path)
        if isinstance(current, (dict, list)) and current and await self.app.run_dialog(  # type: ignore[attr-defined]
                confirm(_('Delete'), _('Delete {path!s} and its {count} item(s)?').format(path=path[-1], count=len(current)))) != Command.YES:
            return
        divjson.delete_at(self.value, path)
        parent = divjson.get_at(self.value, path[:-1])
        self.rebuild(path[:-1] + (min(path[-1], len(parent) - 1),) if isinstance(parent, list) and parent else path[:-1])

    def move_item(self, delta: int) -> None:
        path = self._path()
        if path:
            self.rebuild(divjson.move(self.value, path, delta))
