"""File operations of the project window: new file / folder, rename, delete,
move and copy (cut and paste, Move to..., drag and drop).

``ExplorerMixin`` is part of the app (it needs the editor windows and the
dialogs); ``LocalMenu`` is the Borland-style local menu (Alt+F10 / right click).
"""

from __future__ import annotations

from divide.i18n import _, ngettext

import os
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
CM_TREE_CUT = Command.USER + 46
CM_TREE_COPY = Command.USER + 47
CM_TREE_PASTE = Command.USER + 48
CM_TREE_MOVE = Command.USER + 49

LOCAL_ACTIONS = {
    CM_TREE_OPEN: "open",
    CM_TREE_NEW_FILE: "new_file",
    CM_TREE_NEW_FOLDER: "new_folder",
    CM_TREE_RENAME: "rename",
    CM_TREE_DELETE: "delete",
    CM_TREE_REFRESH: "refresh",
    CM_TREE_CUT: "cut",
    CM_TREE_COPY: "copy",
    CM_TREE_PASTE: "paste",
    CM_TREE_MOVE: "move",
}

TREE_HINT = _('Ins new file · F7 folder · F2 rename · Del delete · Alt+F10 menu')


def local_menu(has_selection: bool, can_paste: bool = False) -> Menu:
    return Menu(
        items=[
            MenuItem(_('~O~pen'), CM_TREE_OPEN, _('Enter'), disabled=not has_selection),
            Separator(),
            MenuItem(_('New ~f~ile...'), CM_TREE_NEW_FILE, _('Ins')),
            MenuItem(_('New fol~d~er...'), CM_TREE_NEW_FOLDER, "F7"),
            MenuItem(_('~R~ename...'), CM_TREE_RENAME, "F2", disabled=not has_selection),
            MenuItem(_('De~l~ete...'), CM_TREE_DELETE, _('Del'), disabled=not has_selection),
            Separator(),
            MenuItem(_('C~u~t'), CM_TREE_CUT, "Ctrl+X", disabled=not has_selection),  # (the Edit menu's letters
            MenuItem(_('Cop~y~'), CM_TREE_COPY, "Ctrl+C", disabled=not has_selection),  # are taken here)
            MenuItem(_('~P~aste'), CM_TREE_PASTE, "Ctrl+V", disabled=not can_paste),
            MenuItem(_('~M~ove to...'), CM_TREE_MOVE, "", disabled=not has_selection),
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


def _bad_name(name: str, *, up: bool = False) -> str | None:
    """Why ``name`` cannot be made (None: it can); ``up``: ``..`` is fine (the caller
    checks that the result stays in the project)."""
    if not name or name in (".", ".."):
        return _('Type a name.')
    if Path(name).is_absolute() or (not up and ".." in Path(name).parts):
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
            screen = LocalMenu(local_menu(tree.selected_path is not None, tree.clipboard is not None),
                               at or tree.cursor_screen_at())
            command = await self.push_screen_wait(screen)  # type: ignore[attr-defined]
            if command is None:
                return
            action = LOCAL_ACTIONS[command]
        member = tree.member
        if member is not None and action in ("rename", "delete", "cut", "copy", "move"):
            # a class, a method, a heading: part of a file, not a file
            self.notify(_('Rename, Delete, Cut, Copy and Move work on files and folders: the bar is on a part of {name}').format(  # type: ignore[attr-defined]
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
            case "cut" | "copy":
                path = tree.selected_path
                if path is None:
                    return
                tree.set_clipboard(path, cut=action == "cut")
                text = (_('{name} cut: Ctrl+V in another folder moves it there (Esc: never mind)') if action == "cut"
                        else _('{name} copied: Ctrl+V in a folder copies it there'))
                self.notify(text.format(name=path.name), timeout=4)  # type: ignore[attr-defined]
                return
            case "paste":
                await self.paste_entry(tree)
            case "move":
                await self.move_entry(tree)
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
        hint = _('{where} · a path moves it too (../{name})').format(where=self._project_relative(path), name=path.name)
        dialog = InputDialog(title, _('New ~n~ame'), path.name, hint=hint, select=(0, stem))
        if await self.run_dialog(dialog) != Command.OK or not dialog.value or dialog.value == path.name:  # type: ignore[attr-defined]
            return None
        if error := _bad_name(dialog.value, up=True):
            await self.run_dialog(information(title, error))  # type: ignore[attr-defined]
            return None
        target = Path(os.path.normpath(path.parent / dialog.value))
        if not self._in_project(target.parent) or target == path.parent:
            await self.run_dialog(information(title, _('Use a name inside the project folder.')))  # type: ignore[attr-defined]
            return None
        if path.is_dir() and (target == path or path in target.parents):
            await self.run_dialog(information(title, _('A folder cannot go inside itself.')))  # type: ignore[attr-defined]
            return None
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
        await self._show_moved(tree, path, target)
        return target

    def _in_project(self, path: Path) -> bool:
        root = Path(self.root).resolve()  # type: ignore[attr-defined]
        path = Path(os.path.normpath(path.resolve() if path.exists() else Path(os.path.abspath(path))))
        return path == root or root in path.parents

    async def _show_moved(self, tree: ProjectTree, old: Path, new: Path) -> None:
        """The tree after a move: where it was (reloaded), and the bar where it is now."""
        if old.parent != new.parent and old.parent not in new.parents:  # off the way that reveal reloads
            node = tree._node_for(old.parent)
            if node is not None:
                await tree.reload_node(node)
        await tree.reveal(new)

    @staticmethod
    def _copy_name(target: Path) -> Path:
        """``card copy.tpl``, ``card copy 2.tpl``... (a copy in its own folder)."""
        stem, suffix = (target.stem, target.suffix) if target.is_file() else (target.name, "")
        candidate, n = target.with_name(f"{stem} copy{suffix}"), 2
        while candidate.exists() or candidate.is_symlink():
            candidate, n = target.with_name(f"{stem} copy {n}{suffix}"), n + 1
        return candidate

    async def transfer(self, tree: ProjectTree, source: Path, folder: Path, *, copy: bool) -> Path | None:
        """Move (or copy) ``source`` into ``folder``: open windows, data files and
        breakpoints follow a moved file. Asks before replacing a file; a folder is
        never merged into another, nor put inside itself."""
        title = _('Copy') if copy else _('Move')
        source = source.parent.resolve() / source.name  # a symbolic link moves as itself
        folder = Path(os.path.normpath(folder.resolve() if folder.exists() else Path(os.path.abspath(folder))))
        rel = self._project_relative(source)

        async def say(text: str) -> None:
            await self.run_dialog(information(title, text))  # type: ignore[attr-defined]

        if not (source.exists() or source.is_symlink()):
            await say(_('{rel} is no longer there.').format(rel=rel))
            await tree.reload()
            return None
        if not self._in_project(folder):
            await say(_('Use a folder inside the project.'))
            return None
        if folder.exists() and not folder.is_dir():
            await say(_('{rel} is not a folder.').format(rel=self._project_relative(folder)))
            return None
        if source.is_dir() and not source.is_symlink() and (folder == source or source in folder.parents):
            await say(_('A folder cannot go inside itself.'))
            return None
        target = folder / source.name
        if target == source:
            if not copy:
                return None  # already there
            target = self._copy_name(target)
        if target.exists() or target.is_symlink():
            there = self._project_relative(target)
            if target.is_dir() and not target.is_symlink():
                await say(_('{rel} already exists: folders are not merged.').format(rel=there))
                return None
            if any(w.dirty and w.path == target for w in self.editor_windows()):  # type: ignore[attr-defined]
                await say(_('{rel} has unsaved changes in a window: save or close it first.').format(rel=there))
                return None
            if await self.run_dialog(confirm(title, _('{rel} already exists. Replace it?').format(rel=there))) != Command.YES:  # type: ignore[attr-defined]
                return None
            for win in list(self.editor_windows()):  # type: ignore[attr-defined]
                if win.path == target:
                    self._remove_window(win)  # type: ignore[attr-defined]
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                target.unlink()
            if not copy:
                shutil.move(str(source), str(target))
            elif source.is_dir() and not source.is_symlink():
                shutil.copytree(source, target, symlinks=True)
            else:
                shutil.copy2(source, target, follow_symlinks=False)
        except OSError as exc:
            text = _('Cannot copy {rel}: {exc}') if copy else _('Cannot move {rel}: {exc}')
            await say(text.format(rel=rel, exc=exc.strerror or exc))
            await tree.reload()
            return None
        if copy:
            await tree.reveal(target)
        else:
            self.paths_moved(source, target)
            await self._show_moved(tree, source, target)
        return target

    async def paste_entry(self, tree: ProjectTree) -> Path | None:
        """Ctrl+V: what was cut goes to the folder under the bar (what was copied, a copy of it)."""
        if tree.clipboard is None:
            self.notify(_('Nothing cut or copied: Ctrl+X or Ctrl+C on a file or a folder first'), timeout=3)  # type: ignore[attr-defined]
            return None
        source, cut = tree.clipboard
        target = await self.transfer(tree, source, tree.target_folder, copy=not cut)
        if target is not None and cut:
            tree.set_clipboard(None)
        return target

    async def move_entry(self, tree: ProjectTree) -> Path | None:
        """Move to...: the folder typed (from the project's) or chosen with Browse."""
        path = tree.selected_path
        if path is None:
            return None
        root = Path(self.root)  # type: ignore[attr-defined]
        where = self._project_relative(path.parent)
        dialog = InputDialog(_('Move'), _('~T~o folder'), "" if where == "." else where,
                             hint=_('{rel} · a folder of the project (created if missing)').format(rel=self._project_relative(path)),
                             browse=(".", root), browse_folders=True, allow_empty=True, history="move-to")
        if await self.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return None
        text = (dialog.value or "").strip()
        folder = Path(text).expanduser() if text else root
        folder = folder if folder.is_absolute() else root / folder
        return await self.transfer(tree, path, folder, copy=False)

    def on_project_tree_drop(self, event: ProjectTree.Drop) -> None:
        event.stop()
        self.drop_entry(event.tree, event.source, event.folder)

    @work(group="explorer")
    async def drop_entry(self, tree: ProjectTree, source: Path, folder: Path) -> Path | None:
        """A drag let go on a folder: asked first (a drag in a terminal is easy to slip)."""
        into = self._project_relative(folder)
        text = _('Move {rel} to {folder}?').format(rel=self._project_relative(source),
                                                    folder=_('the project folder') if into == "." else into + "/")
        if await self.run_dialog(confirm(_('Move'), text)) != Command.YES:  # type: ignore[attr-defined]
            tree.focus()
            return None
        target = await self.transfer(tree, source, folder, copy=False)
        self.recheck_includes()  # type: ignore[attr-defined]
        tree.focus()
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
        breakpoints = getattr(self, "breakpoints", None)
        if breakpoints:
            moved_points: dict = {}
            for k, v in breakpoints.items():
                there = moved(k.resolve())
                moved_points.setdefault(k if there == k.resolve() else there, set()).update(v)
            breakpoints.clear()
            breakpoints.update(moved_points)
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
