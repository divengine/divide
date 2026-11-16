"""File operations of the project window: new file / folder, rename, delete.

``ExplorerMixin`` is part of the app (it needs the editor windows and the
dialogs); ``LocalMenu`` is the Borland-style local menu (Alt+F10 / right click).
"""

from __future__ import annotations

from divide.i18n import _, ngettext

import shutil
from pathlib import Path

from textual import events, on, work
from textual.screen import ModalScreen
from textual_vision.constants import Command
from textual_vision.menus import Menu, MenuBox, MenuItem, Separator

from divide.ui.dialogs import InputDialog, confirm, information
from divide.ui.shadow import install_shadows
from divide.ui.windows import ProjectTree

CM_TREE_OPEN = Command.USER + 40
CM_TREE_NEW_FILE = Command.USER + 41
CM_TREE_NEW_FOLDER = Command.USER + 42
CM_TREE_RENAME = Command.USER + 43
CM_TREE_DELETE = Command.USER + 44
CM_TREE_REFRESH = Command.USER + 45

LOCAL_ACTIONS = {
    CM_TREE_OPEN: "open",
    CM_TREE_NEW_FILE: "new_file",
    CM_TREE_NEW_FOLDER: "new_folder",
    CM_TREE_RENAME: "rename",
    CM_TREE_DELETE: "delete",
    CM_TREE_REFRESH: "refresh",
}

TREE_HINT = _('Ins new file · F7 folder · F2 rename · Del delete · Alt+F10 menu')


def local_menu(has_selection: bool) -> Menu:
    return Menu(
        items=[
            MenuItem(_('~O~pen'), CM_TREE_OPEN, _('Enter'), disabled=not has_selection),
            Separator(),
            MenuItem(_('New ~f~ile...'), CM_TREE_NEW_FILE, _('Ins')),
            MenuItem(_('New fol~d~er...'), CM_TREE_NEW_FOLDER, "F7"),
            MenuItem(_('~R~ename...'), CM_TREE_RENAME, "F2", disabled=not has_selection),
            MenuItem(_('De~l~ete...'), CM_TREE_DELETE, _('Del'), disabled=not has_selection),
            Separator(),
            MenuItem(_('Refre~s~h'), CM_TREE_REFRESH, "Ctrl+R"),
        ]
    )


class LocalMenu(ModalScreen[int | None]):
    """A MenuBox at a screen position; dismisses with the chosen command (or None)."""

    DEFAULT_CSS = """
    LocalMenu { background: transparent; layers: menus; }
    """

    def __init__(self, menu: Menu, at: tuple[int, int]) -> None:
        super().__init__()
        install_shadows(self)
        self.box = MenuBox(menu=menu)
        self.at = at
        self._done = False

    def compose(self):
        yield self.box

    def on_mount(self) -> None:
        width, height = self.box._box_width, self.box._item_count + 2
        sw, sh = self.app.size
        x, y = self.at
        x = max(0, min(x, sw - width - 2))
        y = y + 1 if y + 1 + height <= sh - 1 else max(1, y - height)
        self.box.styles.offset = (x, y)
        self.box.focus()

    def _finish(self, result: int | None) -> None:
        if not self._done:
            self._done = True
            self.dismiss(result)

    def on_command_message(self, message) -> None:
        message.stop()
        message.prevent_default()
        if message.command in LOCAL_ACTIONS:
            self._finish(int(message.command))

    @on(MenuBox.ItemSelected)
    def _selected(self, message: MenuBox.ItemSelected) -> None:
        message.stop()
        message.prevent_default()
        self._finish(int(message.command))

    @on(MenuBox.Closed)
    def _closed(self, message: MenuBox.Closed) -> None:
        message.stop()
        message.prevent_default()
        self._finish(None)

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if self.box.region.contains(event.screen_x, event.screen_y):
            return
        event.stop()
        self._finish(None)


def _bad_name(name: str) -> str | None:
    if not name or name in (".", ".."):
        return _('Type a name.')
    if Path(name).is_absolute() or ".." in Path(name).parts:
        return _('Use a name inside the project folder.')
    if "\0" in name:
        return _('Invalid name.')
    return None


class ExplorerMixin:
    """Project window file operations (mixed into the Divide app)."""

    # A plain handler name: @on() handlers of a non-widget mixin are not collected.
    def on_project_tree_request(self, event: ProjectTree.Request) -> None:
        event.stop()
        self.tree_action(event.tree, event.action, event.screen_at)

    @work(group="explorer")
    async def tree_action(self, tree: ProjectTree, action: str, at: tuple[int, int] | None = None) -> None:
        if action == "menu":
            screen = LocalMenu(local_menu(tree.selected_path is not None), at or tree.cursor_screen_at())
            command = await self.push_screen_wait(screen)  # type: ignore[attr-defined]
            if command is None:
                return
            action = LOCAL_ACTIONS[command]
        member = tree.member
        if member is not None and action in ("rename", "delete"):
            # a class, a method, a heading: part of a file, not a file
            self.notify(_('Rename and Delete work on files and folders: the bar is on a part of {name}').format(  # type: ignore[attr-defined]
                name=tree.selected_path.name), severity="warning", timeout=3)
            return
        match action:
            case "open" if member is not None:
                win = self.open_file(tree.selected_path)  # type: ignore[attr-defined]
                if win is not None:
                    self._select_in(win, member.start, member.end)  # type: ignore[attr-defined]
                return
            case "open":
                path = tree.selected_path
                if path is not None and path.is_file():
                    self.open_file(path)  # type: ignore[attr-defined]
                elif path is not None and tree.cursor_node is not None:
                    tree.cursor_node.toggle()
            case "new_file":
                await self.create_entry(tree, folder=False)
            case "new_folder":
                await self.create_entry(tree, folder=True)
            case "rename":
                await self.rename_entry(tree)
            case "delete":
                await self.delete_entry(tree)
            case "refresh":
                await tree.reload()
        self.recheck_includes()  # type: ignore[attr-defined]  # includes may now resolve, or not
        tree.focus()

    def _project_relative(self, path: Path) -> str:
        path = path.resolve()
        try:
            return str(path.relative_to(self.root)) or "."  # type: ignore[attr-defined]
        except ValueError:
            return str(path)

    async def create_entry(self, tree: ProjectTree, *, folder: bool) -> Path | None:
        base = tree.target_folder
        where = self._project_relative(base)
        title = _('New folder') if folder else _('New file')
        hint = _('Subfolders are created too (parts/menu.tpl)') if not folder else _('Nested folders are fine (a/b/c)')
        dialog = InputDialog(title, _('~N~ame (in {where}/)').format(where=where) if where != "." else _('~N~ame'), "", hint=hint)
        if await self.run_dialog(dialog) != Command.OK or not dialog.value:  # type: ignore[attr-defined]
            return None
        if error := _bad_name(dialog.value):
            await self.run_dialog(information(title, error))  # type: ignore[attr-defined]
            return None
        target = base / dialog.value
        if target.exists():
            await self.run_dialog(information(title, _('{target} already exists.').format(target=self._project_relative(target))))  # type: ignore[attr-defined]
            return None
        try:
            if folder:
                target.mkdir(parents=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
        except OSError as exc:
            await self.run_dialog(information(title, _('Cannot create {value}: {exc}').format(value=dialog.value, exc=exc.strerror or exc)))  # type: ignore[attr-defined]
            return None
        await tree.reveal(target)
        if not folder:
            self.open_file(target)  # type: ignore[attr-defined]
        return target

    async def rename_entry(self, tree: ProjectTree) -> Path | None:
        path = tree.selected_path
        if path is None:
            return None
        title = _('Rename')
        stem = len(path.stem) if path.is_file() and path.suffix else len(path.name)
        dialog = InputDialog(title, _('New ~n~ame'), path.name, hint=self._project_relative(path), select=(0, stem))
        if await self.run_dialog(dialog) != Command.OK or not dialog.value or dialog.value == path.name:  # type: ignore[attr-defined]
            return None
        if error := _bad_name(dialog.value):
            await self.run_dialog(information(title, error))  # type: ignore[attr-defined]
            return None
        target = path.parent / dialog.value
        if target.exists() and target.resolve() != path.resolve():
            await self.run_dialog(information(title, _('{target} already exists.').format(target=self._project_relative(target))))  # type: ignore[attr-defined]
            return None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            path.rename(target)
        except OSError as exc:
            await self.run_dialog(information(title, _('Cannot rename: {exc}').format(exc=exc.strerror or exc)))  # type: ignore[attr-defined]
            return None
        self.paths_moved(path, target)
        await tree.reveal(target)
        return target

    def paths_moved(self, old: Path, new: Path) -> None:
        """Open windows and remembered data files follow a renamed file or folder."""
        old, new = old.resolve(), new.resolve()

        def moved(p: Path | None) -> Path | None:
            if p is None:
                return None
            if p == old:
                return new
            try:
                return new / p.relative_to(old)
            except ValueError:
                return p

        for win in self.editor_windows():  # type: ignore[attr-defined]
            if win.path is not None and (new_path := moved(win.path)) != win.path:
                win.path = new_path
                win.editor.set_path(new_path)
                self._relabel(win)  # type: ignore[attr-defined]
        self.data_files = {moved(k): moved(v) for k, v in self.data_files.items()}  # type: ignore[attr-defined]
        self.last_template = moved(self.last_template)  # type: ignore[attr-defined]
        self.update_status()  # type: ignore[attr-defined]

    async def delete_entry(self, tree: ProjectTree) -> bool:
        path = tree.selected_path
        if path is None:
            return False
        rel = self._project_relative(path)
        if path.is_dir() and not path.is_symlink():
            count = sum(1 for _ in path.rglob("*"))
            text = _('Delete the folder {rel}').format(rel=rel) + (f" and the {count} item{'s' if count != 1 else ''} in it?" if count else "?")
        else:
            text = f"Delete {rel}?"
        if await self.run_dialog(confirm(_('Delete'), text)) != Command.YES:  # type: ignore[attr-defined]
            return False
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError as exc:
            await self.run_dialog(information(_('Delete'), _('Cannot delete {rel}: {exc}').format(rel=rel, exc=exc.strerror or exc)))  # type: ignore[attr-defined]
            await tree.reload()
            return False
        # Windows of deleted files close, unless they hold unsaved changes.
        resolved = path
        kept = 0
        for win in list(self.editor_windows()):  # type: ignore[attr-defined]
            if win.path is not None and (win.path == resolved or resolved in win.path.parents):
                if win.dirty:
                    kept += 1
                else:
                    self._remove_window(win)  # type: ignore[attr-defined]
        if kept:
            self.notify(ngettext("{n} window with unsaved changes kept open", "{n} windows with unsaved changes kept open",
                                 kept).format(n=kept), severity="warning")  # type: ignore[attr-defined]
        await tree.reload()
        return True


__all__ = ["ExplorerMixin", "LocalMenu", "TREE_HINT"]
