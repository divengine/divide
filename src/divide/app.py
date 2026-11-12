"""divide — terminal IDE for the Divengine projects.

A Turbo Vision desktop (menu bar, windows, status line) built on
textual-vision, with first-class support for Div templates
(dialect-aware highlighting).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from textual import events, on, work
from textual.binding import Binding
from textual_vision.app import Application
from textual_vision.constants import Command
from textual_vision.events import CommandMessage
from textual_vision.menus import Menu, MenuBar, MenuItem, Separator, SubMenu
from textual_vision.status_line import StatusDef, StatusItem, StatusLine
from textual.widgets.text_area import Selection
from textual_vision.window import Window

from divide import __version__
from divide.editor.div_editor import DivEditor, is_div_file
from divide.editor.search import SearchError, SearchOptions, compile_pattern, expand, find, replace_all
from divide.ui.dialogs import (
    CM_CHANGE_ALL,
    DialogScreen,
    FileDialog,
    GotoLineDialog,
    SearchDialog,
    about_box,
    confirm_save,
    information,
    replace_prompt,
)
from divide.ui.shadow import ShadowScreen
from divide.ui.windows import EditorWindow, ProjectTree, ProjectWindow

PALETTES = {"turbo-pascal": "Turbo ~P~ascal colors", "turbo-c": "Turbo ~C~ colors"}
DEFAULT_PALETTE = "turbo-pascal"

# Commands of our own, beyond the Turbo Vision standard set.
CM_PROJECT = Command.USER + 1
CM_ABOUT = Command.USER + 2
CM_SELECT_ALL = Command.USER + 3
CM_PALETTE = Command.USER + 4  # info: palette name
CM_FIND = Command.USER + 5
CM_REPLACE = Command.USER + 6
CM_SEARCH_AGAIN = Command.USER + 7
CM_GOTO_LINE = Command.USER + 8

# Names usable in bindings: action_command('SAVE'), action_command('FIND'), ...
COMMANDS: dict[str, int] = {
    **Command.__members__,
    "FIND": CM_FIND,
    "REPLACE": CM_REPLACE,
    "SEARCH_AGAIN": CM_SEARCH_AGAIN,
    "GOTO_LINE": CM_GOTO_LINE,
}


class DropMenuBar(MenuBar):
    """F10 opens the first menu right away.

    textual-vision only highlights the bar, leaving keyboard focus in the editor,
    which then eats Enter and the arrows. With the drop-down open, focus is in
    the menu and Left/Right still walk the bar.
    """

    def activate(self) -> None:
        super().activate()
        if self._menu_box is None:
            self._open_menu_box()


class HintStatusLine(StatusLine):
    """Status line with a free-form hint on the right (language / dialect)."""

    def set_hint(self, text: str) -> None:
        if text != self._hint_text:
            self._hint_text = text
            self.refresh()


class Divide(Application):
    TITLE = "divide"
    CSS = """
    MenuBox .menubox--hotkey { color: $menu-hotkey; }
    """
    # Key handling lives in bindings; menu and status line entries only show the keys.
    BINDINGS = [
        Binding("f2,ctrl+s", "command('SAVE')", "Save", show=False),
        Binding("f3", "command('OPEN')", "Open", show=False),
        # priority: TextArea binds ctrl+w to delete-word-left (ctrl+backspace still does it)
        Binding("alt+f3,ctrl+w", "command('CLOSE')", "Close", show=False, priority=True),
        Binding("f5", "command('ZOOM')", "Zoom", show=False),
        # priority: TextArea binds f6 to select-line
        Binding("f6,ctrl+pagedown", "command('NEXT')", "Next", show=False, priority=True),
        Binding("shift+f6,ctrl+pageup", "command('PREV')", "Prev", show=False, priority=True),
        Binding("ctrl+b", "project", "Project", show=False),
        Binding("ctrl+f", "command('FIND')", "Find", show=False),
        Binding("ctrl+r", "command('REPLACE')", "Replace", show=False),
        Binding("ctrl+l", "command('SEARCH_AGAIN')", "Search again", show=False),
        Binding("ctrl+g", "command('GOTO_LINE')", "Go to line", show=False),
        Binding("alt+x,ctrl+q", "command('QUIT')", "Exit", show=False, priority=True),
    ] + [Binding(f"alt+{n}", f"window({n})", show=False) for n in range(1, 10)]

    def __init__(self, root: Path, files: list[Path], *, palette: str = DEFAULT_PALETTE) -> None:
        super().__init__(theme=palette)
        self.root = root
        self.initial_files = files
        self._untitled = 0
        self.search_query = ""
        self.search_replacement = ""
        self.search_options = SearchOptions()
        self.last_search: str | None = None  # "find" | "replace"

    # --------------------------------------------------------------- shell
    def get_default_screen(self) -> ShadowScreen:
        return ShadowScreen(id="_default")

    def init_menu_bar(self) -> Menu:
        palette_items = [MenuItem(label, CM_PALETTE, param=name) for name, label in PALETTES.items()]
        return Menu(
            items=[
                SubMenu(
                    "~F~ile",
                    MenuItem("~N~ew", Command.NEW),
                    MenuItem("~O~pen...", Command.OPEN, "F3"),
                    MenuItem("~S~ave", Command.SAVE, "F2"),
                    MenuItem("Save ~a~s...", Command.SAVE_AS),
                    MenuItem("Save a~l~l", Command.SAVE_ALL),
                    Separator(),
                    MenuItem("E~x~it", Command.QUIT, "Alt+X"),
                ),
                SubMenu(
                    "~E~dit",
                    MenuItem("~U~ndo", Command.UNDO, "Ctrl+Z"),
                    MenuItem("~R~edo", Command.REDO, "Ctrl+Y"),
                    Separator(),
                    MenuItem("Cu~t~", Command.CUT, "Ctrl+X"),
                    MenuItem("~C~opy", Command.COPY, "Ctrl+C"),
                    MenuItem("~P~aste", Command.PASTE, "Ctrl+V"),
                    Separator(),
                    MenuItem("Select ~a~ll", CM_SELECT_ALL, "F7"),
                ),
                SubMenu(
                    "~S~earch",
                    MenuItem("~F~ind...", CM_FIND, "Ctrl+F"),
                    MenuItem("~R~eplace...", CM_REPLACE, "Ctrl+R"),
                    MenuItem("~S~earch again", CM_SEARCH_AGAIN, "Ctrl+L"),
                    Separator(),
                    MenuItem("~G~o to line number...", CM_GOTO_LINE, "Ctrl+G"),
                ),
                SubMenu(
                    "~W~indow",
                    MenuItem("~P~roject", CM_PROJECT, "Ctrl+B"),
                    Separator(),
                    MenuItem("~T~ile", Command.TILE),
                    MenuItem("C~a~scade", Command.CASCADE),
                    Separator(),
                    MenuItem("~Z~oom", Command.ZOOM, "F5"),
                    MenuItem("~N~ext", Command.NEXT, "F6"),
                    MenuItem("Pre~v~ious", Command.PREV, "Shift+F6"),
                    MenuItem("~C~lose", Command.CLOSE, "Alt+F3"),
                    MenuItem("Close a~l~l", Command.CLOSE_ALL),
                ),
                # Flat: textual-vision 0.0.1 does not move keyboard focus into nested sub-menus.
                SubMenu("~O~ptions", *palette_items),
                SubMenu("~H~elp", MenuItem("~A~bout...", CM_ABOUT)),
            ]
        )

    def init_status_line(self) -> list[StatusDef]:
        # Empty key codes: the keys are bindings, the status line only shows them.
        items = [
            StatusItem("~F2~ Save", "", Command.SAVE),
            StatusItem("~F3~ Open", "", Command.OPEN),
            StatusItem("~Alt+F3~ Close", "", Command.CLOSE),
            StatusItem("~F5~ Zoom", "", Command.ZOOM),
            StatusItem("~F6~ Next", "", Command.NEXT),
            StatusItem("~F10~ Menu", "", Command.MENU),
            StatusItem("~Alt+X~ Exit", "", Command.QUIT),
        ]
        return [StatusDef(0, 0xFFFF, items)]

    def compose(self):
        for widget in super().compose():
            if isinstance(widget, StatusLine) and not isinstance(widget, HintStatusLine):
                widget = HintStatusLine(defs=self.init_status_line())
                self._status_line = widget
            elif isinstance(widget, MenuBar) and not isinstance(widget, DropMenuBar):
                widget = DropMenuBar(menu=widget.menu)
                self._menu_bar = widget
            yield widget

    def on_mount(self) -> None:
        if self.initial_files:
            for f in self.initial_files:
                self.open_file(f)
        else:
            self.call_after_refresh(self.toggle_project)
        self.call_after_refresh(self.update_status)

    # ----------------------------------------------------------- windows
    def windows(self) -> list[Window]:
        desktop = self.desktop
        return list(desktop._z_order) if desktop else []

    def editor_windows(self) -> list[EditorWindow]:
        return [w for w in self.windows() if isinstance(w, EditorWindow)]

    def active_window(self) -> Window | None:
        current = self.desktop.current if self.desktop else None
        return current if isinstance(current, Window) else None

    def active_editor(self) -> EditorWindow | None:
        win = self.active_window()
        return win if isinstance(win, EditorWindow) else None

    def project_window(self) -> ProjectWindow | None:
        return next((w for w in self.windows() if isinstance(w, ProjectWindow)), None)

    def _free_number(self) -> int:
        used = {w.number for w in self.windows()}
        return next((n for n in range(1, 10) if n not in used), 0)

    def _place(self, window: Window) -> None:
        """New windows fill the desktop, beside the project window if it is open."""
        project = self.project_window()
        if project is not None and project is not window and not project.zoomed:
            window.styles.offset = (ProjectWindow.WIDTH, 0)
            window.styles.width = max(20, (self.desktop.size.width or 80) - ProjectWindow.WIDTH)
        else:
            window.styles.offset = (0, 0)
            window.styles.width = "100%"
        window.styles.height = "100%"

    def _insert(self, window: Window) -> None:
        self._place(window)
        self.insert_window(window)

    def raise_window(self, window: Window) -> None:
        if self.desktop is not None:
            self.desktop.raise_window(window)

    def _relabel(self, win: EditorWindow) -> None:
        if win.path is None:
            win.title = win.display_name
            return
        try:
            win.title = str(win.path.relative_to(self.root))
        except ValueError:
            win.title = str(win.path)

    def open_file(self, path: Path) -> EditorWindow | None:
        path = path.expanduser().resolve()
        for win in self.editor_windows():
            if win.path == path:
                self.raise_window(win)
                return win
        try:
            text = path.read_text(encoding="utf-8") if path.exists() else ""
        except (OSError, UnicodeDecodeError) as exc:
            self.notify(f"Cannot open {path.name}: {exc}", severity="error")
            return None
        win = EditorWindow(path, text, roots=[self.root], number=self._free_number())
        self._relabel(win)
        self._insert(win)
        return win

    def new_file(self) -> EditorWindow:
        win = EditorWindow(None, "", roots=[self.root], untitled=self._untitled, number=self._free_number())
        self._untitled += 1
        self._insert(win)
        return win

    def toggle_project(self) -> None:
        """Open the project window, raise it, or close it when it is on top."""
        project = self.project_window()
        if project is None:
            project = ProjectWindow(self.root)
            project.styles.offset = (0, 0)
            project.styles.width = ProjectWindow.WIDTH
            project.styles.height = "100%"
            self.insert_window(project)
        elif self.active_window() is project:
            self._remove_window(project)
        else:
            self.raise_window(project)

    def _remove_window(self, window: Window) -> None:
        if self.desktop is not None:
            self.desktop.remove_window(window)
        self.call_after_refresh(self.update_status)

    # ------------------------------------------------------------- files
    def _write(self, win: EditorWindow) -> bool:
        assert win.path is not None
        try:
            win.path.write_text(win.editor.text, encoding="utf-8")
        except OSError as exc:
            self.notify(f"Save failed: {exc}", severity="error")
            return False
        win.saved_text = win.editor.text
        win.refresh_indicator()
        self.update_status()
        self.notify(f"Saved {win.path.name}", timeout=1.5)
        return True

    async def save(self, win: EditorWindow, *, ask_name: bool = False) -> bool:
        if win.path is None or ask_name:
            start = win.path.parent if win.path else self.root
            dialog = FileDialog("Save file as", start, name=win.path.name if win.path else "", ok_label="~O~K")
            if await self.run_dialog(dialog) != Command.OK or dialog.chosen is None:
                return False
            win.path = dialog.chosen
            win.editor.path = dialog.chosen
            win.editor.div_enabled = is_div_file(dialog.chosen)
            self._relabel(win)
        ok = self._write(win)
        if ok and ask_name:
            win.editor._build_highlight_map()
            win.editor.refresh()
        return ok

    async def confirm_close(self, win: EditorWindow) -> bool:
        """Ask about unsaved changes. True when the window may close."""
        if not win.dirty:
            return True
        self.raise_window(win)
        choice = await self.run_dialog(confirm_save(win.display_name))
        if choice == Command.YES:
            return await self.save(win)
        return choice == Command.NO

    async def run_dialog(self, dialog) -> Command:
        return await self.push_screen_wait(DialogScreen(dialog))

    @work(exclusive=True, group="close")
    async def close_window(self, window: Window) -> None:
        if isinstance(window, EditorWindow) and not await self.confirm_close(window):
            return
        self._remove_window(window)

    # ---------------------------------------------------------- commands
    def action_command(self, name: str) -> None:
        # Priority bindings fire even under a dialog; the dialog owns the keyboard then.
        if not isinstance(self.screen, DialogScreen):
            self.post_message(CommandMessage(COMMANDS[name]))  # type: ignore[arg-type]

    def action_project(self) -> None:
        self.toggle_project()

    def action_window(self, number: int) -> None:
        for win in self.windows():
            if win.number == number:
                self.raise_window(win)
                return

    def on_command_message(self, message: CommandMessage) -> None:
        message.stop()
        # Program.on_command_message would exit on QUIT without asking about unsaved changes.
        message.prevent_default()
        if message.command != Command.VALID:
            self.run_command(message.command, message.info)

    @work(group="command")
    async def run_command(self, command: int, info: object = None) -> None:
        win = self.active_window()
        editor = self.active_editor()
        match command:
            case Command.QUIT:
                for w in self.editor_windows():
                    if not await self.confirm_close(w):
                        return
                self.exit()
            case Command.NEW:
                self.new_file()
            case Command.OPEN:
                start = editor.path.parent if editor and editor.path else self.root
                dialog = FileDialog("Open a file", start)
                if await self.run_dialog(dialog) == Command.OK and dialog.chosen:
                    self.open_file(dialog.chosen)
            case Command.SAVE if editor:
                await self.save(editor)
            case Command.SAVE_AS if editor:
                await self.save(editor, ask_name=True)
            case Command.SAVE_ALL:
                for w in self.editor_windows():
                    if w.dirty and not await self.save(w):
                        return
            case Command.CLOSE if win:
                if not isinstance(win, EditorWindow) or await self.confirm_close(win):
                    self._remove_window(win)
            case Command.CLOSE_ALL:
                for w in list(self.windows()):
                    if isinstance(w, EditorWindow) and not await self.confirm_close(w):
                        return
                    self._remove_window(w)
            case Command.ZOOM if win:
                win.toggle_zoom()
            case Command.NEXT:
                self._cycle(forward=True)
            case Command.PREV:
                self._cycle(forward=False)
            case Command.TILE if self.desktop:
                self.desktop.tile()
            case Command.CASCADE if self.desktop:
                self.desktop.cascade()
            case Command.MENU if self.menu_bar:
                self.menu_bar.activate()
            case Command.UNDO if editor:
                editor.editor.action_undo()
            case Command.REDO if editor:
                editor.editor.action_redo()
            case Command.CUT if editor:
                editor.editor.action_cut()
            case Command.COPY if editor:
                editor.editor.action_copy()
            case Command.PASTE if editor:
                editor.editor.action_paste()
            case _ if command == CM_SELECT_ALL and editor:
                editor.editor.select_all()
            case _ if command == CM_PROJECT:
                self.toggle_project()
            case _ if command == CM_PALETTE and isinstance(info, str):
                self.theme = info
            case _ if command == CM_ABOUT:
                await self.run_dialog(about_box(f"v{__version__}"))
            case _ if command in (CM_FIND, CM_REPLACE) and editor:
                await self.search_dialog(editor, replace=command == CM_REPLACE)
            case _ if command == CM_SEARCH_AGAIN and editor:
                if self.last_search is None:
                    await self.search_dialog(editor, replace=False)
                else:
                    await self.search(editor, first=False)
            case _ if command == CM_GOTO_LINE and editor:
                ed = editor.editor
                dialog = GotoLineDialog(ed.cursor_location[0] + 1)
                if await self.run_dialog(dialog) == Command.OK and dialog.line:
                    row = min(dialog.line, ed.document.line_count) - 1
                    ed.move_cursor((row, 0), center=True)
        self.update_status()

    # ------------------------------------------------------------ search
    def _initial_query(self, ed: DivEditor) -> str:
        """Selected text (one line) or the word at the cursor, else the last query."""
        selected = ed.selected_text
        if selected and "\n" not in selected:
            return selected
        row, col = ed.cursor_location
        for m in re.finditer(r"\w+", ed.document.get_line(row)):
            if m.start() <= col <= m.end():
                return m.group()
        return self.search_query

    async def search_dialog(self, win: EditorWindow, *, replace: bool) -> None:
        dialog = SearchDialog(
            replace=replace,
            query=self._initial_query(win.editor),
            replacement=self.search_replacement,
            options=self.search_options,
        )
        result = await self.run_dialog(dialog)
        if result not in (Command.OK, CM_CHANGE_ALL):
            return
        self.search_query = dialog.search_text
        self.search_options = dialog.options
        if replace:
            self.search_replacement = dialog.replacement
        self.last_search = "replace" if replace else "find"
        await self.search(win, first=True, change_all=result == CM_CHANGE_ALL)

    @staticmethod
    def _select(ed: DivEditor, start: int, end: int) -> None:
        doc = ed.document
        ed.selection = Selection(doc.get_location_from_index(start), doc.get_location_from_index(end))
        ed.scroll_cursor_visible(center=True)

    async def search(self, win: EditorWindow, *, first: bool, change_all: bool = False) -> None:
        """Run the stored find / replace from the cursor (or the scope edge on the first run)."""
        ed, opts = win.editor, self.search_options
        try:
            pattern = compile_pattern(self.search_query, opts)
        except SearchError as exc:
            await self.run_dialog(information("Error", str(exc)))
            return
        doc, text = ed.document, ed.text
        if first and opts.entire_scope:
            pos = len(text) if opts.backward else 0
        else:
            sel_start, sel_end = sorted((ed.selection.start, ed.selection.end))
            pos = doc.get_index_from_location(sel_start if opts.backward else sel_end)
        try:
            if self.last_search == "replace":
                count, found = await self._replace(ed, pattern, pos, change_all)
            else:
                m = find(text, pattern, pos, backward=opts.backward)
                found, count = m is not None, 0
                if m:
                    self._select(ed, m.start(), m.end())
        except SearchError as exc:
            await self.run_dialog(information("Error", str(exc)))
            return
        if not found:
            await self.run_dialog(information("Information", "Search string not found."))
        elif count > 1:
            self.notify(f"{count} occurrences replaced", timeout=2)

    async def _replace(self, ed: DivEditor, pattern: re.Pattern[str], pos: int, change_all: bool) -> tuple[int, bool]:
        """Replace one occurrence, or all of them with ``change_all``. Returns (replaced, found)."""
        opts, repl, doc = self.search_options, self.search_replacement, ed.document
        loc = doc.get_location_from_index
        if change_all and not opts.prompt:
            # One edit, so a single undo restores everything.
            text = ed.text
            if opts.backward:
                new, count = replace_all(text[:pos], pattern, repl, opts)
                if count:
                    ed.replace(new, (0, 0), loc(pos), maintain_selection_offset=False)
            else:
                new, count = replace_all(text, pattern, repl, opts, start=pos)
                if count:
                    ed.replace(new[pos:], loc(pos), doc.end, maintain_selection_offset=False)
            return count, count > 0
        count, found, ask = 0, False, opts.prompt
        while (m := find(ed.text, pattern, pos, backward=opts.backward)) is not None:
            found = True
            self._select(ed, m.start(), m.end())
            if ask:
                answer = await self.run_dialog(replace_prompt())
                if answer == Command.CANCEL:
                    break
                if answer == CM_CHANGE_ALL:
                    ask, change_all = False, True
                elif answer == Command.NO:
                    pos = m.start() if opts.backward else m.end()
                    if change_all:
                        continue
                    break
            new = expand(m, repl, opts)
            result = ed.replace(new, loc(m.start()), loc(m.end()), maintain_selection_offset=False)
            ed.selection = Selection(loc(m.start()), result.end_location)
            count += 1
            pos = m.start() if opts.backward else m.start() + len(new)
            if not change_all:
                break
        return count, found

    def _cycle(self, *, forward: bool) -> None:
        """F6 brings the bottom window up; Shift+F6 sends the top one down."""
        desktop = self.desktop
        if desktop is None or len(desktop._z_order) < 2:
            return
        if forward:
            desktop.raise_window(desktop._z_order[0])
        else:
            top = desktop._z_order.pop()
            desktop._z_order.insert(0, top)
            desktop._rebuild_layers()
            desktop.raise_window(desktop._z_order[-1])

    # ------------------------------------------------------------ events
    @on(ProjectTree.FileSelected)
    def _file_selected(self, event: ProjectTree.FileSelected) -> None:
        event.stop()
        self.open_file(event.path)

    @on(DivEditor.Changed)
    @on(DivEditor.SelectionChanged)
    def _editor_changed(self, event: DivEditor.Changed | DivEditor.SelectionChanged) -> None:
        for win in self.editor_windows():
            if win.editor is event.text_area:
                win.refresh_indicator()
        self.update_status()

    @on(DivEditor.DialectChanged)
    def _dialect_changed(self) -> None:
        self.update_status()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        self.update_status()

    def update_status(self) -> None:
        status = self.status_line
        if not isinstance(status, HintStatusLine):
            return
        win = self.active_editor()
        if win is None:
            status.set_hint(str(self.root))
            return
        ed = win.editor
        if ed.div_enabled:
            d = ed.dialect
            hint = "Div" + ("" if d.name == "default" else f" · {d.name}")
            if d.error:
                hint += f" [!] {d.error}"
        else:
            hint = "plain text"
        status.set_hint(hint)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="divide", description="Terminal IDE for the Divengine projects.")
    parser.add_argument("paths", nargs="*", help="project folder and/or files to open")
    parser.add_argument("--palette", choices=sorted(PALETTES), default=DEFAULT_PALETTE, help="colour palette")
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
    Divide(root, files, palette=args.palette).run()


__all__ = ["Divide", "main", "is_div_file"]
