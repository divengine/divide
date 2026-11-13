"""divide — terminal IDE for the Divengine projects.

A Turbo Vision desktop (menu bar, windows, status line) built on
textual-vision, with first-class support for Div templates
(dialect-aware highlighting).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
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
    InputDialog,
    confirm,
    confirm_save,
    information,
    replace_prompt,
)
from divide.ui.shadow import ShadowScreen
from divide import config
from divide.run.render import (
    DialectVerdict,
    IncludeTarget,
    RenderError,
    check_dialect,
    default_data_file,
    find_engine,
    render,
    resolve_includes,
    translate_template,
)
from divide.ui.explorer import TREE_HINT, ExplorerMixin
from divide.ui.jsontree import JsonTreeWindow
from divide.ui.dialector import (
    CM_OPEN_TRANSLATION,
    CM_SAVE_TRANSLATION,
    DialectorWindow,
    SectionDialog,
    TransformDialog,
    TranslateDialog,
)
from divide.lang.div.dialect import Dialect, template_properties
from divide.lang.div import dialector as dx
from divide.lang.div.dialect import DEFAULT_TAGS
from divide.lang import divjson
from divide.lang.div.diagnostics import include_at, line_col
from divide.run.render import RenderMessage
from divide.ui.windows import EditorWindow, MessageItem, MessagesWindow, OutputWindow, ProjectTree, ProjectWindow

SAVE_FIRST = (
    "Save the template first (F2). divide hands Div templates that live in a file: "
    "Div finds the includes and the data file from the template's folder."
)

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
CM_RENDER = Command.USER + 9
CM_OUTPUT = Command.USER + 10
CM_DATA_FILE = Command.USER + 11
CM_EDIT_DATA = Command.USER + 12
CM_DIV_ENGINE = Command.USER + 13
CM_DATA_TREE = Command.USER + 14
CM_CHECK = Command.USER + 15
CM_NEXT_ERROR = Command.USER + 16
CM_PREV_ERROR = Command.USER + 17
CM_MESSAGES = Command.USER + 18
CM_COMPLETE = Command.USER + 19
CM_GOTO_INCLUDE = Command.USER + 20
CM_DIALECTOR = Command.USER + 21
CM_TRANSLATE = Command.USER + 22
# The dialector's local menu
CM_DX_EDIT = Command.USER + 70
CM_DX_RESTORE = Command.USER + 71
CM_DX_TRANSFORM = Command.USER + 72
CM_DX_ALL_DEFAULTS = Command.USER + 73
CM_DX_PHP = Command.USER + 74
CM_DX_EXAMPLE = Command.USER + 75
CM_DX_CHECK = Command.USER + 76
CM_DX_IMPORT = Command.USER + 77
CM_DX_TRANSLATE = Command.USER + 78

# Names usable in bindings: action_command('SAVE'), action_command('FIND'), ...
COMMANDS: dict[str, int] = {
    **Command.__members__,
    "FIND": CM_FIND,
    "REPLACE": CM_REPLACE,
    "SEARCH_AGAIN": CM_SEARCH_AGAIN,
    "GOTO_LINE": CM_GOTO_LINE,
    "RENDER": CM_RENDER,
    "OUTPUT": CM_OUTPUT,
    "DATA_TREE": CM_DATA_TREE,
    "CHECK": CM_CHECK,
    "NEXT_ERROR": CM_NEXT_ERROR,
    "PREV_ERROR": CM_PREV_ERROR,
    "GOTO_INCLUDE": CM_GOTO_INCLUDE,
}


class DropMenuBar(MenuBar):
    """F10 opens the first menu right away.

    textual-vision only highlights the bar, leaving keyboard focus in the editor,
    which then eats Enter and the arrows. With the drop-down open, focus is in
    the menu and Left/Right still walk the bar.
    """

    # Only F10 (or the status line) opens the first menu: Alt+letter activates the
    # bar and opens its own menu right after, and a box opened by activate() would
    # not be mounted yet when that second open tries to close it, staying behind.
    def open_first(self) -> None:
        if not self.active:
            self.activate()
        if self._menu_box is None:
            self._open_menu_box()

    def tv_handle_key(self, event: events.Key) -> bool:
        opening = event.key == "f10" and not self.active
        handled = super().tv_handle_key(event)
        if opening and self.active and self._menu_box is None:
            self._open_menu_box()
        return handled


class HintStatusLine(StatusLine):
    """Status line with a free-form hint on the right (language / dialect)."""

    def set_hint(self, text: str) -> None:
        if text != self._hint_text:
            self._hint_text = text
            self.refresh()


class Divide(ExplorerMixin, Application):
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
        Binding("ctrl+f9", "command('RENDER')", "Render", show=False, priority=True),
        Binding("alt+f5", "command('OUTPUT')", "Output", show=False, priority=True),
        Binding("ctrl+t", "command('DATA_TREE')", "Data tree", show=False, priority=True),
        # Turbo Pascal: Alt+F9 compile, Alt+F8 / Alt+F7 next / previous message.
        Binding("alt+f9", "command('CHECK')", "Check", show=False, priority=True),
        Binding("alt+f8", "command('NEXT_ERROR')", "Next error", show=False, priority=True),
        Binding("alt+f7", "command('PREV_ERROR')", "Previous error", show=False, priority=True),
        # Borland's "open file at cursor"; terminals that send Ctrl+Enter as a newline give ctrl+j.
        Binding("ctrl+enter,ctrl+j", "command('GOTO_INCLUDE')", "Go to include", show=False, priority=True),
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
        self.data_files: dict[Path, Path] = {}  # template -> data file chosen in Run > Data file
        self.last_template: Path | None = None
        self.render_messages: list[RenderMessage] = []  # of last_template's last render
        self._focused_template: EditorWindow | None = None  # last template window that had focus
        self._completion_cache: dict[Path, tuple[str, object]] = {}  # data file -> (text, value)
        self._include_timers: dict[int, object] = {}  # editor id -> pending include resolution
        self._include_gen: dict[int, int] = {}  # editor id -> latest resolution asked

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
                    MenuItem("Co~m~plete", CM_COMPLETE, "Ctrl+Space"),
                ),
                SubMenu(
                    "~S~earch",
                    MenuItem("~F~ind...", CM_FIND, "Ctrl+F"),
                    MenuItem("~R~eplace...", CM_REPLACE, "Ctrl+R"),
                    MenuItem("~S~earch again", CM_SEARCH_AGAIN, "Ctrl+L"),
                    Separator(),
                    MenuItem("~G~o to line number...", CM_GOTO_LINE, "Ctrl+G"),
                    MenuItem("Go to ~i~ncluded template", CM_GOTO_INCLUDE, "Ctrl+Enter"),
                    Separator(),
                    MenuItem("~P~revious error", CM_PREV_ERROR, "Alt+F7"),
                    MenuItem("~N~ext error", CM_NEXT_ERROR, "Alt+F8"),
                ),
                SubMenu(
                    "~R~un",
                    MenuItem("~R~ender", CM_RENDER, "Ctrl+F9"),
                    MenuItem("~C~heck", CM_CHECK, "Alt+F9"),
                    MenuItem("~O~utput", CM_OUTPUT, "Alt+F5"),
                    Separator(),
                    MenuItem("~D~ata file...", CM_DATA_FILE),
                    MenuItem("~E~dit data", CM_EDIT_DATA),
                    MenuItem("Data ~t~ree", CM_DATA_TREE, "Ctrl+T"),
                ),
                SubMenu(
                    "~W~indow",
                    MenuItem("~P~roject", CM_PROJECT, "Ctrl+B"),
                    MenuItem("~M~essages", CM_MESSAGES),
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
                SubMenu(
                    "~T~ools",
                    MenuItem("~D~ialector...", CM_DIALECTOR),
                    MenuItem("~T~ranslate a template...", CM_TRANSLATE),
                ),
                SubMenu("~O~ptions", *palette_items, Separator(), MenuItem("~D~iv engine...", CM_DIV_ENGINE)),
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
        self.call_after_refresh(self.resolve_includes_of, win.editor)
        return win

    def new_file(self, text: str = "", *, plain: bool = False) -> EditorWindow:
        win = EditorWindow(None, text, roots=[self.root], untitled=self._untitled, number=self._free_number())
        win.saved_text = ""  # generated text counts as unsaved
        if plain:
            win.editor.lang = None
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
            # A data tree is a view of its code window: they close together.
            for view in self.tree_windows() + self.dialector_windows():
                if view.source is window:
                    self.desktop.remove_window(view)
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
        self.recheck_includes()  # a template may now exist
        self._rerender_after_save(win.path)
        return True

    async def save(self, win: EditorWindow, *, ask_name: bool = False) -> bool:
        if win.path is None or ask_name:
            start = win.path.parent if win.path else self.root
            dialog = FileDialog("Save file as", start, name=win.path.name if win.path else "", ok_label="~O~K")
            if await self.run_dialog(dialog) != Command.OK or dialog.chosen is None:
                return False
            win.path = dialog.chosen
            win.editor.set_path(dialog.chosen)
            self._relabel(win)
            if self._write(win):
                self.refresh_project()
                return True
            return False
        return self._write(win)

    def refresh_project(self) -> None:
        """Show files created outside the project window (Save as)."""
        project = self.project_window()
        if project is not None:
            project.project_tree.reload()

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
            case Command.SAVE if editor or isinstance(win, (JsonTreeWindow, DialectorWindow)):
                await self.save(editor or win.source)  # type: ignore[union-attr]
            case Command.SAVE_AS if editor or isinstance(win, (JsonTreeWindow, DialectorWindow)):
                await self.save(editor or win.source, ask_name=True)  # type: ignore[union-attr]
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
            case Command.MENU if isinstance(self.menu_bar, DropMenuBar):
                self.menu_bar.open_first()
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
            case _ if command == CM_DIALECTOR:
                await self.open_dialector()
            case _ if command == CM_TRANSLATE:
                await self.translate_wizard()
            case _ if command == CM_GOTO_INCLUDE and editor:
                await self.goto_include(editor)
            case _ if command == CM_COMPLETE and editor:
                editor.editor.focus()
                self.call_after_refresh(editor.editor.update_completion, True)
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
            case _ if command == CM_RENDER:
                await self.render_template()
            case _ if command == CM_OUTPUT:
                output = self.output_window()
                if output is not None:
                    self.raise_window(output)
                else:
                    await self.render_template()
            case _ if command == CM_DATA_FILE:
                await self.choose_data_file()
            case _ if command == CM_EDIT_DATA:
                self.edit_data()
            case _ if command == CM_CHECK:
                self.show_messages(announce=True)
            case _ if command == CM_MESSAGES:
                self.show_messages()
            case _ if command in (CM_NEXT_ERROR, CM_PREV_ERROR):
                self.jump_to_diagnostic(forward=command == CM_NEXT_ERROR)
            case _ if command == CM_DATA_TREE:
                self.toggle_data_tree()
            case _ if command == CM_DIV_ENGINE:
                await self.choose_engine()
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

    # ---------------------------------------------------------------- run
    def output_window(self) -> OutputWindow | None:
        return next((w for w in self.windows() if isinstance(w, OutputWindow)), None)

    def messages_window(self) -> MessagesWindow | None:
        return next((w for w in self.windows() if isinstance(w, MessagesWindow)), None)

    def window_for(self, path: Path) -> EditorWindow | None:
        return next((w for w in self.editor_windows() if w.path == path), None)

    def data_file_for(self, template: Path) -> Path:
        return self.data_files.get(template) or default_data_file(template)

    def template_for_data(self, data: Path) -> Path | None:
        for template, chosen in self.data_files.items():
            if chosen == data:
                return template
        sibling = data.with_suffix(".tpl")
        return sibling if sibling.exists() or self.window_for(sibling) else None

    def render_target(self) -> Path | None:
        """The template to render: the active one, the one whose data is active, or the last one."""
        win = self.active_editor()
        if win is not None and win.path is not None:
            if win.editor.div_enabled:
                return win.path
            if win.path.suffix == ".json" and (template := self.template_for_data(win.path)):
                return template
        return self.last_template

    def _text_of(self, path: Path) -> str | None:
        """Editor buffer when the file is open (unsaved changes count), else the file."""
        if (win := self.window_for(path)) is not None:
            return win.editor.text
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def completion_data_for(self, editor: DivEditor) -> object:
        """The data JSON of the template in ``editor`` (decoded; the last good one while it is broken)."""
        if editor.path is None:
            return None
        data_path = self.data_file_for(editor.path)
        text = self._text_of(data_path)
        if text is None:
            return None
        cached = self._completion_cache.get(data_path)
        if cached is not None and cached[0] == text:
            return cached[1]
        try:
            value = divjson.loads(text)
        except divjson.DivJsonError:
            return cached[1] if cached is not None else None
        self._completion_cache[data_path] = (text, value)
        return value

    # ---------------------------------------------------------- includes
    # divide never looks for included templates itself: Div's getTplPath does
    # (through the PHP bridge, with the template's path and the render cwd).
    @on(DivEditor.IncludesChanged)
    def _includes_changed(self, event: DivEditor.IncludesChanged) -> None:
        ed = event.editor
        timer = self._include_timers.pop(id(ed), None)
        if timer is not None:
            timer.stop()  # type: ignore[attr-defined]
        self._include_timers[id(ed)] = self.set_timer(0.4, lambda: self.resolve_includes_of(ed))

    def recheck_includes(self) -> None:
        for win in self.editor_windows():
            if win.editor.div_enabled and win.editor.include_set:
                self.resolve_includes_of(win.editor)

    def _include_engine(self, template: Path) -> Path | None:
        if not shutil.which("php"):
            return None
        return find_engine([template.parent, self.root], config.load().get("div_engine"))

    async def _resolve(self, ed: DivEditor, includes: list[str]) -> dict[str, IncludeTarget] | None:
        assert ed.path is not None
        engine = self._include_engine(ed.path)
        if engine is None:
            return None
        history = [self.last_template] if self.last_template and self.last_template != ed.path else []
        try:
            return await resolve_includes(
                engine, ed.path, includes, cwd=self.root, history=history,
                separator=ed.dialect["DIV_TAG_PREPROCESSED_SEPARATOR"],
            )
        except RenderError:
            return None

    @work(group="includes")
    async def resolve_includes_of(self, ed: DivEditor) -> None:
        self._include_timers.pop(id(ed), None)
        if not ed.div_enabled or ed.path is None or not ed.include_set:
            ed.set_include_targets({})
            return
        gen = self._include_gen[id(ed)] = self._include_gen.get(id(ed), 0) + 1
        targets = await self._resolve(ed, sorted(ed.include_set))
        if targets is not None and self._include_gen.get(id(ed)) == gen:
            ed.set_include_targets(targets)

    async def goto_include(self, win: EditorWindow) -> None:
        """Open the template that the include under the cursor leads to (Div decides which)."""
        ed = win.editor
        if not ed.div_enabled:
            return
        offset = ed.document.get_index_from_location(ed.selection.end)
        hit = include_at(ed.text, ed.tokens, ed.dialect, offset)
        if hit is None:
            self.notify("Put the cursor on a {% %} or {%% %%} include", timeout=2)
            return
        raw = hit[2]
        if win.path is None:
            await self.run_dialog(information("Go to include", SAVE_FIRST))
            return
        if self._include_engine(win.path) is None:
            await self.run_dialog(information("Go to include", "Div was not found (see Options > Div engine): only Div knows where an include leads."))
            return
        targets = await self._resolve(ed, [raw])
        target = (targets or {}).get(raw)
        if target is None:
            return
        if target.file is not None:
            self.open_file(target.file)
            return
        # Not found: offer to create it where Div looks first, next to the template.
        name = target.path if target.path.endswith(".tpl") else target.path + ".tpl"
        new = (win.path.parent / name).resolve()
        rel = self._project_relative(new)
        if await self.run_dialog(confirm("Go to include", f"Div cannot find {target.path}. Create {rel}?")) != Command.YES:
            return
        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            new.touch()
        except OSError as exc:
            await self.run_dialog(information("Go to include", f"Cannot create {rel}: {exc.strerror or exc}"))
            return
        self.refresh_project()
        self.recheck_includes()
        self.open_file(new)

    def _render_layout(self, template: Path, output: OutputWindow, messages: MessagesWindow | None) -> None:
        """First render: template on the left, output on the right, messages below."""
        desktop = self.desktop
        if desktop is None:
            return
        project = self.project_window()
        left = ProjectWindow.WIDTH if project is not None and not project.zoomed else 0
        width, height = (desktop.size.width or 80) - left, desktop.size.height or 24
        top_height = height - 8 if messages is not None else height
        half = width // 2
        source = self.window_for(template)
        if source is not None:
            source.styles.offset = (left, 0)
            source.styles.width, source.styles.height = half, top_height
        output.styles.offset = (left + half, 0)
        output.styles.width, output.styles.height = width - half, top_height
        if messages is not None:
            messages.styles.offset = (left, top_height)
            messages.styles.width, messages.styles.height = width, 8

    async def render_template(self, *, keep_focus: bool = False) -> None:
        """Render the target template. ``keep_focus`` (re-render after a save) leaves the active window on top."""
        previous = self.active_window()
        active = self.active_editor()
        if not keep_focus and active is not None and active.path is None and active.editor.div_enabled:
            # Convention: templates are saved before Div sees them. Div could take the
            # code alone, but its includes and data file are found from where it lives.
            await self.run_dialog(information("Render", SAVE_FIRST))
            return
        template = self.render_target()
        if template is None:
            await self.run_dialog(information("Render", "Open a Div template (.tpl) to render it."))
            return
        engine = find_engine([template.parent, self.root], config.load().get("div_engine"))
        if engine is None:
            await self.run_dialog(
                information(
                    "Render",
                    "Div was not found.\n\nInstall it in the project (composer require divengine/div) "
                    "or set its path in Options > Div engine.",
                )
            )
            return
        code = self._text_of(template)
        if code is None:
            await self.run_dialog(information("Render", f"Cannot read {template.name}."))
            return
        data_path = self.data_file_for(template)
        data = self._text_of(data_path) if data_path.exists() or self.window_for(data_path) else None
        try:
            result = await render(engine, template, code, data, cwd=self.root)
        except RenderError as exc:
            await self.run_dialog(information("Render", str(exc)))
            return
        self.last_template = template
        data_note = data_path.name if data is not None else "no data"
        summary = f"{template.name} + {data_note} · Div {result.version or '?'} · {result.seconds:.2f}s"
        output = self.output_window()
        first = output is None
        if output is None:
            output = OutputWindow(number=self._free_number())
            self.insert_window(output)
        output.show(template, result.output, summary)
        self.render_messages = result.messages
        messages = self.messages_window()
        serious = result.serious
        if serious and messages is None:
            messages = self._open_messages_window(layout=False)
        self.refresh_messages(template)
        if first:
            self._render_layout(template, output, messages if serious else None)
        if keep_focus and previous is not None and previous.is_attached:
            self.raise_window(previous)
        else:
            self.raise_window(output)
            if serious and messages is not None:
                self.raise_window(messages)
        self.notify(("Render failed: " if result.fatal else "Rendered ") + summary, timeout=3,
                    severity="error" if result.fatal else "information")
        self.update_status()

    # ---------------------------------------------------------- messages
    def _check_target(self) -> EditorWindow | None:
        """The template the Messages window talks about: the active one, else the last rendered."""
        win = self.active_editor()
        if win is not None and win.editor.div_enabled:
            return win
        if self._focused_template is not None and self._focused_template.is_attached:
            return self._focused_template
        if self.last_template is not None:
            return self.window_for(self.last_template)
        return None

    def message_items(self, template: Path | None = None) -> list[MessageItem]:
        win = self.window_for(template) if template is not None else self._check_target()
        items: list[MessageItem] = []
        if win is not None and win.editor.div_enabled:
            name = win.display_name
            text = win.editor.text
            for d in win.editor.diagnostics:
                line, col = line_col(text, d.start)
                label = "Error" if d.severity == "error" else "Warning"
                items.append(MessageItem(f"{name}({line},{col}): {label}: {d.message}", win.path, d.start, d.end))
            if not win.editor.diagnostics:
                items.append(MessageItem(f"{name}: no Div errors"))
        rendered = win.path if win is not None else template
        if self.render_messages and rendered is not None and rendered == self.last_template:
            order = {"FATAL": 0, "DATA": 1, "WARNING": 2, "PHP": 3, "NOTE": 4}
            items.append(MessageItem(f"── render of {rendered.name} ──"))
            for m in sorted(self.render_messages, key=lambda m: order.get(m.level, 9)):
                items.append(MessageItem(f"{m.level}: {m.text}"))
        return items

    def refresh_messages(self, template: Path | None = None) -> None:
        window = self.messages_window()
        if window is not None:
            window.show(self.message_items(template))

    def _open_messages_window(self, *, layout: bool = True) -> MessagesWindow:
        window = MessagesWindow(number=self._free_number())
        if layout and self.desktop is not None:
            project = self.project_window()
            left = ProjectWindow.WIDTH if project is not None and not project.zoomed else 0
            width, height = (self.desktop.size.width or 80) - left, self.desktop.size.height or 24
            top = max(0, height - 8)
            window.styles.offset = (left, top)
            window.styles.width, window.styles.height = width, min(8, height)
            # Like Turbo Pascal: the editors end where the message window starts.
            for other in self.windows():
                if other is window or other.zoomed:
                    continue
                y = int(other.styles.offset.y.value) if other.styles.offset.y else 0
                bottom = y + (other.size.height or height)
                if bottom > top and top - y >= 5:
                    other.styles.height = top - y
        self.insert_window(window)
        return window

    def show_messages(self, *, announce: bool = False) -> None:
        """Run > Check / Window > Messages: open (or raise) the Messages window."""
        target = self._check_target()
        window = self.messages_window() or self._open_messages_window()
        window.show(self.message_items())
        self.raise_window(window)
        self.call_after_refresh(window.list.tv_select_self)
        if announce and target is not None:
            errors = sum(d.severity == "error" for d in target.editor.diagnostics)
            warnings = len(target.editor.diagnostics) - errors
            self.notify(
                f"{target.display_name}: {errors} error(s), {warnings} warning(s)" if errors or warnings else f"{target.display_name}: no Div errors",
                timeout=2,
                severity="error" if errors else "information",
            )

    def goto_location(self, path: Path | None, start: int, end: int | None = None) -> None:
        win = self.window_for(path) if path is not None else None
        if win is None and path is not None:
            win = self.open_file(path)
        if win is not None:
            self._select_in(win, start, end)

    def _select_in(self, win: EditorWindow, start: int, end: int | None = None) -> None:
        """Raise ``win`` and select [start, end) in it."""
        self.raise_window(win)
        ed = win.editor
        doc = ed.document
        ed.selection = Selection(doc.get_location_from_index(start), doc.get_location_from_index(end if end is not None else start))
        ed.scroll_cursor_visible(center=True)
        ed.focus()
        messages = self.messages_window()
        if messages is not None:
            for index, item in enumerate(messages.items):
                if item.path == win.path and item.start == start:
                    messages.list.focus_item(index)
                    break
        self.update_status()

    def jump_to_diagnostic(self, *, forward: bool) -> None:
        win = self.active_editor()
        if win is None or not win.editor.div_enabled:
            win = self._check_target()
        if win is None or not win.editor.diagnostics:
            self.notify("No Div errors", timeout=1.5)
            return
        ed = win.editor
        here = ed.document.get_index_from_location(ed.selection.start)
        diags = win.editor.diagnostics
        if forward:
            target = next((d for d in diags if d.start > here), diags[0])
        else:
            target = next((d for d in reversed(diags) if d.start < here), diags[-1])
        self._select_in(win, target.start, target.end)

    def _rerender_after_save(self, path: Path) -> None:
        template = self.last_template
        if self.output_window() is None or template is None:
            return
        if path == template or path == self.data_file_for(template):
            self.rerender()

    @work(group="render")
    async def rerender(self) -> None:
        await self.render_template(keep_focus=True)

    async def choose_data_file(self) -> None:
        template = self.render_target()
        if template is None:
            await self.run_dialog(information("Data file", "Open a Div template first."))
            return
        current = self.data_file_for(template)
        dialog = FileDialog(f"Data for {template.name}", current.parent, name=current.name, pattern="*.json", ok_label="~O~K")
        if await self.run_dialog(dialog) == Command.OK and dialog.chosen:
            self.data_files[template] = dialog.chosen
            self.notify(f"{template.name} renders with {dialog.chosen.name}", timeout=2)

    def edit_data(self) -> None:
        """Open the template's data file (a new one if it does not exist yet)."""
        template = self.render_target()
        if template is None:
            self.notify("Open a Div template first", severity="warning")
            return
        win = self.open_file(self.data_file_for(template))
        if win is not None and not win.path.exists() and not win.editor.text:
            win.editor.load_text("{\n    \n}\n")
            win.saved_text = ""
            win.editor.move_cursor((1, 4))

    def tree_windows(self) -> list[JsonTreeWindow]:
        return [w for w in self.windows() if isinstance(w, JsonTreeWindow)]

    # ---------------------------------------------------------- dialector
    def dialector_windows(self) -> list[DialectorWindow]:
        return [w for w in self.windows() if isinstance(w, DialectorWindow)]

    async def open_dialector(self) -> None:
        """Tools > Dialector: on the active .dialect file, on the dialect of the active
        template, or on a new dialect file."""
        active = self.active_window()
        if isinstance(active, DialectorWindow):
            self.raise_window(active.source)
            return
        source: EditorWindow | None = None
        if isinstance(active, EditorWindow) and active.path is not None and active.path.suffix == ".dialect":
            source = active
        elif isinstance(active, EditorWindow) and active.editor.div_enabled and active.editor.dialect.source is not None:
            source = self.open_file(active.editor.dialect.source)
        else:
            dialog = InputDialog(
                "New dialect", "Dialect ~f~ile", "my.dialect",
                hint="Relative to the project; an existing file is opened", select=(0, 2),
                browse=("*.dialect", self.root),
            )
            if await self.run_dialog(dialog) != Command.OK or not dialog.value:
                return
            path = Path(dialog.value).expanduser()
            path = (path if path.is_absolute() else self.root / path).resolve()
            if path.suffix != ".dialect":
                path = path.with_name(path.name + ".dialect")
            if not path.exists():
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("{}\n", encoding="utf-8")
                except OSError as exc:
                    await self.run_dialog(information("Dialector", f"Cannot create {path.name}: {exc.strerror or exc}"))
                    return
                self.refresh_project()
            source = self.open_file(path)
        if source is None:
            return
        view = next((d for d in self.dialector_windows() if d.source is source), None)
        if view is None:
            view = DialectorWindow(source, number=self._free_number())
            for attr in ("offset", "width", "height"):
                setattr(view.styles, attr, getattr(source.styles, attr))
            self.insert_window(view)
        else:
            self.raise_window(view)

    async def dialector_verdict(self, tags: dict[str, str]) -> DialectVerdict | None:
        """Div's verdict on a dialect: valid? and does it read the dialector's example back?"""
        engine = self._include_engine(self.root / "x")
        if engine is None:
            return None
        changed = dx.overrides(tags)
        try:
            return await check_dialect(
                engine, changed, cwd=self.root,
                sample=dx.example(changed).text, expected=dx.example({}).text,
            )
        except RenderError as exc:
            return DialectVerdict(f"could not ask Div: {exc}")

    def dialector_action(self, win: DialectorWindow, action: str) -> None:
        self._dialector_action(win, action)

    @work(group="dialector")
    async def _dialector_action(self, win: DialectorWindow, action: str) -> None:
        if action == "menu":
            from textual_vision.menus import Menu, MenuItem as Item, Separator as Sep
            from divide.ui.explorer import LocalMenu

            menu = Menu(items=[
                Item("~E~dit section...", CM_DX_EDIT, "Enter"),
                Item("~R~estore section defaults", CM_DX_RESTORE, "Del"),
                Sep(),
                Item("~T~ransform all tags...", CM_DX_TRANSFORM),
                Item("Restore ~a~ll defaults", CM_DX_ALL_DEFAULTS),
                Sep(),
                Item("~I~mport tags...", CM_DX_IMPORT),
                Item("Export as ~P~HP code", CM_DX_PHP),
                Sep(),
                Item("Save e~x~ample template...", CM_DX_EXAMPLE),
                Item("Trans~l~ate a template...", CM_DX_TRANSLATE),
                Item("~C~heck with Div", CM_DX_CHECK),
            ])
            region = win.sections.content_region
            at = (region.x + 2, region.y + max(0, win.section_index - win.sections.scroll_offset.y))
            command = await self.push_screen_wait(LocalMenu(menu, at))
            action = {
                CM_DX_EDIT: "edit", CM_DX_RESTORE: "restore_section", CM_DX_TRANSFORM: "transform",
                CM_DX_ALL_DEFAULTS: "all_defaults", CM_DX_PHP: "php", CM_DX_EXAMPLE: "example", CM_DX_CHECK: "check",
                CM_DX_IMPORT: "import", CM_DX_TRANSLATE: "translate",
            }.get(command, "")
        section = win.section
        match action:
            case "edit":
                if not await win.can_rewrite():
                    return
                dialog = SectionDialog(section, win.tags, win)
                if await self.run_dialog(dialog) == Command.OK and dialog.values:
                    win.apply(dialog.values)
            case "restore_section":
                if await win.can_rewrite():
                    win.apply({k: DEFAULT_TAGS[k] for k in section.keys})
            case "transform":
                if not await win.can_rewrite():
                    return
                dialog = TransformDialog(win.tags)
                if await self.run_dialog(dialog) == Command.OK and dialog.changes:
                    win.apply(dialog.changes)
            case "all_defaults":
                if await win.can_rewrite() and await self.run_dialog(
                    confirm("Dialector", "Put every tag back to Div's default?")
                ) == Command.YES:
                    win.apply(dict(DEFAULT_TAGS))
            case "php":
                self.new_file(dx.php_code(win.tags, win.source.display_name), plain=True)
            case "example":
                await self.save_dialect_example(win)
            case "import":
                await self.import_dialect(win)
            case "translate":
                if win.source.dirty and not await self.save(win.source):
                    return
                template = self._focused_template.path if self._focused_template and self._focused_template.path else None
                await self.translate_wizard(
                    template=self._project_relative(template) if template else "",
                    target=self._project_relative(win.source.path) if win.source.path else "",
                )
            case "check":
                win.check_now()
        if win.is_attached:
            win.sections.focus()
        self.update_status()

    async def save_dialect_example(self, win: DialectorWindow) -> None:
        """A template written in the dialect (``@_DIALECT`` + the dialector's example), opened."""
        source = win.source
        assert source.path is not None
        if source.dirty and not await self.save(source):
            return
        default = source.path.stem + ".example.tpl"
        dialog = InputDialog(
            "Example template", "~F~ile", default, hint=f"Relative to {source.path.parent.name}/",
            select=(0, len(source.path.stem)), browse=("*.tpl", source.path.parent),
        )
        if await self.run_dialog(dialog) != Command.OK or not dialog.value:
            return
        target = (source.path.parent / dialog.value).resolve()
        if target.exists() and await self.run_dialog(confirm("Example template", f"{target.name} exists. Replace it?")) != Command.YES:
            return
        try:
            ref = source.path.relative_to(target.parent)
        except ValueError:
            ref = source.path
        text = f"@_DIALECT = {ref}\n\n" + dx.example(dx.overrides(win.tags)).text
        try:
            target.write_text(text, encoding="utf-8")
        except OSError as exc:
            await self.run_dialog(information("Example template", f"Cannot write {target.name}: {exc.strerror or exc}"))
            return
        self.refresh_project()
        existing = self.window_for(target)
        if existing is not None:
            existing.editor.load_text(text)
            existing.saved_text = text
        self.open_file(target)

    async def import_dialect(self, win: DialectorWindow) -> None:
        """Take the tags of another dialect file, or of PHP define() lines."""
        start = win.source.path.parent if win.source.path else self.root
        dialog = FileDialog("Import tags", start, pattern="*.dialect")
        if await self.run_dialog(dialog) != Command.OK or dialog.chosen is None:
            return
        try:
            text = dialog.chosen.read_text(encoding="utf-8")
            tags, unknown = dx.parse_import(text, php=dialog.chosen.suffix.lower() == ".php")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            await self.run_dialog(information("Import tags", f"Cannot read {dialog.chosen.name}: {exc}"))
            return
        if not tags:
            await self.run_dialog(information("Import tags", f"{dialog.chosen.name} has no Div tags."))
            return
        note = f" ({len(unknown)} names that are not Div tags are left out)" if unknown else ""
        text = f"Take {len(tags)} tags from {dialog.chosen.name}{note}? Tags it does not mention go back to Div's defaults."
        if await self.run_dialog(confirm("Import tags", text)) != Command.YES or not await win.can_rewrite():
            return
        win.apply({**DEFAULT_TAGS, **tags})

    def _project_path(self, text: str) -> Path | None:
        if not text:
            return None
        path = Path(text).expanduser()
        return (path if path.is_absolute() else self.root / path).resolve()

    async def translate_for_dialog(self, template: str, source: str, target: str) -> tuple[str, Dialect]:
        """Div's translation of a template between two dialect files (empty: Div's default).

        The ``@_DIALECT`` property of the result points at the target dialect."""
        tpl = self._project_path(template)
        if tpl is None:
            raise ValueError("Which template? Type its path.")
        code = self._text_of(tpl)
        if code is None:
            raise ValueError(f"Cannot read the template {template}")
        texts: list[str] = []
        for label, raw in (("source", source), ("target", target)):
            path = self._project_path(raw)
            text = "" if path is None else self._text_of(path)
            if text is None:
                raise ValueError(f"Cannot read the {label} dialect {raw}")
            texts.append(text)
        engine = self._include_engine(tpl)
        if engine is None:
            raise ValueError("Div was not found: Div translates the template (Options > Div engine).")
        try:
            translated = await translate_template(engine, code, texts[0], texts[1], cwd=self.root)
        except RenderError as exc:
            raise ValueError(str(exc)) from None
        target_path = self._project_path(target)
        ref = None
        if target_path is not None:
            ref = os.path.relpath(target_path, tpl.parent)
        try:
            tags, _ = dx.parse_import(texts[1]) if texts[1] else ({}, [])
        except ValueError:
            tags = {}
        dialect = Dialect.from_overrides(tags, name=target_path.stem if target_path else "default", source=target_path)
        return dx.set_dialect_property(translated, ref), dialect

    async def suggest_source_dialect(self, template: str) -> tuple[str, str]:
        """The source dialect a template declares: (path for the field, a note).

        A template in another dialect says so with ``@_DIALECT``; without it, it
        is in Div's default dialect. Div resolves the property's path the way it
        does when it renders (``getTplPath()``, as ``prepareDialect()`` does)."""
        tpl = self._project_path(template)
        text = self._text_of(tpl) if tpl is not None else None
        if tpl is None or text is None:
            return "", ""
        prop = template_properties(text).get("DIALECT")
        if prop is None or not prop[0].strip():
            return "", "Suggested: Div's default dialect (the template has no @_DIALECT)"
        ref = prop[0].strip()
        engine = self._include_engine(tpl)
        if engine is None:
            return ref, f"Suggested: the template's @_DIALECT = {ref} (Div not found to resolve it)"
        try:
            found = (await resolve_includes(engine, tpl, [ref], cwd=self.root)).get(ref)
        except RenderError:
            found = None
        if found is None or found.file is None:
            return ref, f"[!] The template says @_DIALECT = {ref}, but Div cannot find that file"
        return self._project_relative(found.file), f"Suggested: the template's @_DIALECT = {ref}"

    async def translate_wizard(self, *, template: str = "", source: str = "", target: str = "") -> None:
        """Tools > Translate a template: choose, preview, save as or open."""
        active = self.active_editor()
        if not template and active is not None and active.editor.div_enabled and active.path is not None:
            template = self._project_relative(active.path)
        # The source dialect is suggested by the dialog from the template itself.
        dialog = TranslateDialog(template, source, target, root=self.root)
        choice = await self.run_dialog(dialog)
        if dialog.text is None or choice not in (CM_SAVE_TRANSLATION, CM_OPEN_TRANSLATION):
            return
        if choice == CM_OPEN_TRANSLATION:
            self.new_file(dialog.text)
            return
        tpl = self._project_path(dialog.fields()[0])
        assert tpl is not None
        suffix = dialog.target_dialect.source.stem if dialog.target_dialect and dialog.target_dialect.source else "div"
        default = f"{tpl.stem}.{suffix}{tpl.suffix or '.tpl'}"
        name = InputDialog(
            "Save translation as", "~F~ile", default, hint=f"Relative to {tpl.parent.name}/", select=(0, len(default) - 4),
            browse=("*.tpl", tpl.parent),
        )
        if await self.run_dialog(name) != Command.OK or not name.value:
            return
        out = (tpl.parent / name.value).resolve()
        if out.exists() and await self.run_dialog(confirm("Save translation", f"{out.name} exists. Replace it?")) != Command.YES:
            return
        text = dialog.text
        if dialog.target_dialect and dialog.target_dialect.source is not None:
            text = dx.set_dialect_property(text, os.path.relpath(dialog.target_dialect.source, out.parent))
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
        except OSError as exc:
            await self.run_dialog(information("Save translation", f"Cannot write {out.name}: {exc.strerror or exc}"))
            return
        self.refresh_project()
        self.open_file(out)

    def toggle_data_tree(self) -> None:
        """Code <-> tree: from a tree go to its code; from JSON code (or a template's data) open its tree."""
        active = self.active_window()
        if isinstance(active, (JsonTreeWindow, DialectorWindow)):
            self.raise_window(active.source)
            return
        source = active if isinstance(active, EditorWindow) and active.editor.lang == "json" else None
        if source is None:
            template_window = active if isinstance(active, EditorWindow) else None
            self.edit_data()
            source = self.active_editor()
            if source is None or source.editor.lang != "json":
                return
            if template_window is not None and source is not template_window:
                # The data takes the template's place (next to the Output after a render).
                for attr in ("offset", "width", "height"):
                    setattr(source.styles, attr, getattr(template_window.styles, attr))
        tree = next((t for t in self.tree_windows() if t.source is source), None)
        if tree is None:
            tree = JsonTreeWindow(source, number=self._free_number())
            # Same place as the code window: Ctrl+T flips between the two views.
            for attr in ("offset", "width", "height"):
                setattr(tree.styles, attr, getattr(source.styles, attr))
            self.insert_window(tree)
        else:
            self.raise_window(tree)

    async def choose_engine(self) -> None:
        current = find_engine([self.root], config.load().get("div_engine"))
        start = current.parent if current else self.root
        dialog = FileDialog("Div engine (autoload.php or div.php)", start, name=current.name if current else "", pattern="*.php", ok_label="~O~K")
        if await self.run_dialog(dialog) == Command.OK and dialog.chosen:
            config.set_value("div_engine", str(dialog.chosen))
            self.notify(f"Div engine: {dialog.chosen}", timeout=3)

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
        if isinstance(event, DivEditor.Changed):
            for view in self.tree_windows() + self.dialector_windows():
                if view.source.editor is event.text_area:
                    view.reload()
        self.update_status()

    @on(DivEditor.DialectChanged)
    @on(DivEditor.JsonChecked)
    def _dialect_changed(self) -> None:
        self.update_status()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        win = self.active_editor()
        if win is not None and win.editor.div_enabled:
            if self._focused_template is not win:
                self.resolve_includes_of(win.editor)  # files may have changed meanwhile
            self._focused_template = win
        if not isinstance(self.active_window(), MessagesWindow):
            self.refresh_messages()  # the Messages window follows the active template
        self.update_status()

    @on(DivEditor.DiagnosticsChanged)
    def _diagnostics_changed(self, event: DivEditor.DiagnosticsChanged) -> None:
        target = self._check_target()
        if target is not None and target.editor is event.editor:
            self.refresh_messages()
        self.update_status()

    def update_status(self) -> None:
        status = self.status_line
        if not isinstance(status, HintStatusLine):
            return
        active = self.active_window()
        if isinstance(active, OutputWindow):
            status.set_hint(active.summary)
            return
        if isinstance(active, DialectorWindow):
            dirty = " *" if active.source.dirty else ""
            verdict = getattr(active.verdict, "reason", None)
            status.set_hint(f"{active.source.display_name}{dirty} · " + (f"Div: {verdict}" if verdict else DialectorWindow.HINT))
            return
        if isinstance(active, JsonTreeWindow):
            dirty = " *" if active.source.dirty else ""
            error = f"JSON [!] {active.error} · Ctrl+T code" if active.error else JsonTreeWindow.HINT
            status.set_hint(f"{active.source.display_name}{dirty} · {error}")
            return
        if isinstance(active, ProjectWindow):
            status.set_hint(TREE_HINT)
            return
        win = self.active_editor()
        if win is None:
            status.set_hint(str(self.root))
            return
        ed = win.editor
        if ed.lang == "json":
            if ed.json_error is not None:
                hint = f"JSON [!] {ed.json_error}"
            else:
                hint = "JSON ok"
            if ed.json_refs:
                hint += f" · {len(ed.json_refs)} $ref" + ("s" if len(ed.json_refs) > 1 else "")
            status.set_hint(hint)
            return
        if ed.div_enabled:
            here = ed.document.get_index_from_location(min(ed.selection.start, ed.selection.end))
            if (diag := ed.diagnostic_at(here)) is not None:
                status.set_hint(("Error: " if diag.severity == "error" else "Warning: ") + diag.message)
                return
            d = ed.dialect
            hint = "Div" + ("" if d.name == "default" else f" · {d.name}")
            errors = sum(x.severity == "error" for x in ed.diagnostics)
            warnings = len(ed.diagnostics) - errors
            if errors or warnings:
                hint += f" · {errors} error{'s' if errors != 1 else ''}, {warnings} warning{'s' if warnings != 1 else ''} (Alt+F8)"
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
