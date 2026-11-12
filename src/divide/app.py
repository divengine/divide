"""divide — terminal IDE for the Divengine projects.

First milestone: a file explorer plus tabbed editors with first-class
support for Div templates (dialect-aware highlighting).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Footer, Label, Static, TabbedContent, TabPane

from divide import __version__
from divide.editor.div_editor import DivEditor, is_div_file


class ConfirmClose(ModalScreen[str]):
    """Ask what to do with unsaved changes: save / discard / cancel."""

    DEFAULT_CSS = """
    ConfirmClose { align: center middle; }
    ConfirmClose > Vertical {
        width: 64; height: auto; padding: 1 2;
        border: thick $warning; background: $surface;
    }
    ConfirmClose Horizontal { height: auto; align-horizontal: right; margin-top: 1; }
    ConfirmClose Button { margin-left: 1; }
    """
    BINDINGS = [Binding("escape", "dismiss('cancel')", "Cancel")]

    def __init__(self, what: str) -> None:
        super().__init__()
        self.what = what

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Unsaved changes in {self.what}.")
            with Horizontal():
                yield Button("Save", id="save", variant="primary")
                yield Button("Discard", id="discard", variant="error")
                yield Button("Cancel", id="cancel")

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id or "cancel")


class EditorPane(TabPane):
    def __init__(self, path: Path, editor: DivEditor, pane_id: str) -> None:
        super().__init__(path.name, editor, id=pane_id)
        self.path = path
        self.editor = editor
        self.saved_text = editor.text

    @property
    def dirty(self) -> bool:
        return self.editor.text != self.saved_text

    def refresh_title(self) -> None:
        tab = self.app.query_one(TabbedContent).get_tab(self)
        tab.label = ("● " if self.dirty else "") + self.path.name


class StatusBar(Static):
    DEFAULT_CSS = """
    StatusBar { height: 1; background: $panel; color: $text-muted; padding: 0 1; }
    """


class Divide(App):
    TITLE = "divide"
    SUB_TITLE = f"v{__version__}"
    CSS = """
    #main { height: 1fr; }
    #sidebar { width: 32; border-right: solid $panel-lighten-2; }
    #sidebar.hidden { display: none; }
    #welcome { padding: 2 4; color: $text-muted; }
    TabbedContent { height: 1fr; }
    TabPane { padding: 0; }
    DivEditor { border: none; padding: 0; }
    """
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        # priority: TextArea binds ctrl+w to delete-word-left (ctrl+backspace still does it)
        Binding("ctrl+w", "close_tab", "Close tab", priority=True),
        Binding("ctrl+b", "explorer", "Explorer"),
        Binding("ctrl+pageup", "prev_tab", "Prev tab", show=False),
        Binding("ctrl+pagedown", "next_tab", "Next tab", show=False),
        Binding("ctrl+q", "quit", "Quit", priority=True),
    ]

    def __init__(self, root: Path, files: list[Path]) -> None:
        super().__init__()
        self.root = root
        self.initial_files = files
        self._pane_seq = 0

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            yield DirectoryTree(self.root, id="sidebar")
            with Vertical():
                yield Static(
                    "divide — Div template editor\n\n"
                    "Open a file from the explorer.\n"
                    "ctrl+s save · ctrl+w close tab · ctrl+b explorer · ctrl+pgup/pgdn switch tab · ctrl+q quit",
                    id="welcome",
                )
                yield TabbedContent(id="tabs")
        yield StatusBar(id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#tabs").display = False
        for f in self.initial_files:
            self.open_file(f)
        self._update_status()

    # ---------------------------------------------------------------- files
    def _panes(self) -> list[EditorPane]:
        return list(self.query(EditorPane))

    def _active_pane(self) -> EditorPane | None:
        tabs = self.query_one(TabbedContent)
        pane = tabs.active_pane
        return pane if isinstance(pane, EditorPane) else None

    def open_file(self, path: Path) -> None:
        path = path.resolve()
        for pane in self._panes():
            if pane.path == path:
                self.query_one(TabbedContent).active = pane.id or ""
                pane.editor.focus()
                return
        try:
            text = path.read_text(encoding="utf-8") if path.exists() else ""
        except (OSError, UnicodeDecodeError) as exc:
            self.notify(f"Cannot open {path.name}: {exc}", severity="error")
            return
        self._pane_seq += 1
        editor = DivEditor(text, path=path, roots=[self.root])
        pane = EditorPane(path, editor, f"pane-{self._pane_seq}")
        tabs = self.query_one(TabbedContent)
        tabs.display = True
        self.query_one("#welcome").display = False
        tabs.add_pane(pane)
        tabs.active = pane.id or ""
        self.call_after_refresh(editor.focus)

    @on(DirectoryTree.FileSelected)
    def _file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.open_file(event.path)

    def _save(self, pane: EditorPane) -> bool:
        try:
            pane.path.write_text(pane.editor.text, encoding="utf-8")
        except OSError as exc:
            self.notify(f"Save failed: {exc}", severity="error")
            return False
        pane.saved_text = pane.editor.text
        pane.refresh_title()
        self.notify(f"Saved {pane.path.name}", timeout=1.5)
        return True

    def _remove(self, pane: EditorPane) -> None:
        tabs = self.query_one(TabbedContent)
        tabs.remove_pane(pane.id or "")
        if len(self._panes()) <= 1:
            # remove_pane is async; the pane being removed may still be counted.
            remaining = [p for p in self._panes() if p is not pane]
            if not remaining:
                tabs.display = False
                self.query_one("#welcome").display = True
        self.call_after_refresh(self._update_status)

    # -------------------------------------------------------------- actions
    def action_save(self) -> None:
        pane = self._active_pane()
        if pane:
            self._save(pane)

    @work
    async def action_close_tab(self) -> None:
        pane = self._active_pane()
        if not pane:
            return
        if pane.dirty:
            choice = await self.push_screen_wait(ConfirmClose(pane.path.name))
            if choice == "cancel" or (choice == "save" and not self._save(pane)):
                return
        self._remove(pane)

    @work
    async def action_quit(self) -> None:
        for pane in self._panes():
            if pane.dirty:
                self.query_one(TabbedContent).active = pane.id or ""
                choice = await self.push_screen_wait(ConfirmClose(pane.path.name))
                if choice == "cancel" or (choice == "save" and not self._save(pane)):
                    return
        self.exit()

    def action_explorer(self) -> None:
        """Show+focus the explorer; when it already has focus, hide it."""
        sidebar = self.query_one("#sidebar")
        if sidebar.has_class("hidden"):
            sidebar.remove_class("hidden")
            sidebar.focus()
        elif sidebar.has_focus:
            sidebar.add_class("hidden")
            pane = self._active_pane()
            if pane:
                pane.editor.focus()
        else:
            sidebar.focus()

    def _cycle(self, step: int) -> None:
        panes = self._panes()
        current = self._active_pane()
        if not panes or current is None:
            return
        nxt = panes[(panes.index(current) + step) % len(panes)]
        self.query_one(TabbedContent).active = nxt.id or ""
        nxt.editor.focus()

    def action_prev_tab(self) -> None:
        self._cycle(-1)

    def action_next_tab(self) -> None:
        self._cycle(1)

    # --------------------------------------------------------------- status
    @on(DivEditor.Changed)
    def _changed(self, event: DivEditor.Changed) -> None:
        for pane in self._panes():
            if pane.editor is event.text_area:
                pane.refresh_title()
        self._update_status()

    @on(DivEditor.SelectionChanged)
    @on(DivEditor.DialectChanged)
    @on(TabbedContent.TabActivated)
    def _status_events(self) -> None:
        self._update_status()

    def _update_status(self) -> None:
        status = self.query_one(StatusBar)
        pane = self._active_pane()
        if pane is None:
            status.update(f"{self.root}")
            return
        ed = pane.editor
        row, col = ed.cursor_location
        try:
            rel = pane.path.relative_to(self.root)
        except ValueError:
            rel = pane.path
        if ed.div_enabled:
            d = ed.dialect
            lang = "Div" + ("" if d.name == "default" else f" · dialect {d.name}")
            if d.error:
                lang += f" [!] {d.error}"
        else:
            lang = "plain text"
        status.update(f"{rel}{' ●' if pane.dirty else ''}   Ln {row + 1}, Col {col + 1}   {lang}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="divide", description="Terminal IDE for the Divengine projects.")
    parser.add_argument("paths", nargs="*", help="project folder and/or files to open")
    args = parser.parse_args(argv)
    root = Path.cwd()
    files: list[Path] = []
    for raw in args.paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            root = p.resolve()
        else:
            files.append(p)
    if files and not any(Path(a).is_dir() for a in args.paths):
        root = files[0].resolve().parent
    Divide(root, files).run()


__all__ = ["Divide", "main", "is_div_file"]
