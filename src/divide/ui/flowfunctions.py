"""The Functions window: a Runner Flow's Modules and Functions, made and opened from the keyboard.

Run > Flow functions (F on the Flow Designer's board) shows where the Flow's
Functions are (the function root and where it comes from: ``--root``,
``_root_folder``, ``.div/runner.json`` or the project), its Modules, the
Functions in each, the Steps of the project's Flows that reference each one,
and the references that resolve to nothing (:mod:`divide.run.flowfunctions`).
The files are ordinary PHP: Enter opens one in the editor (lint, LSP and
Xdebug as for any PHP file), at its ``return``.

Keys: Enter opens a Function (or goes to a Step, or creates a missing one),
Ins makes a Function in the Module under the cursor, Shift+Ins a Module,
Alt+F10 the window's menu (also the project's ``.div/runner.json``), Ctrl+R
reads the disk again. Nothing is written without a dialog's OK, and never
over a file or outside the project.

The Step dialog uses :class:`FunctionDialog` too: its New function... button
fills the Step's ``module`` and ``activity`` (or ``condition``) and the file
is made when the Step dialog's OK writes the Step, as one edit.
"""

from __future__ import annotations

from divide.i18n import _

import textwrap
from dataclasses import dataclass
from pathlib import Path

from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, Tree
from textual_vision.button import Button
from textual_vision.cluster import RadioButtons
from textual_vision.constants import Command, OptionFlag
from textual_vision.group import TVViewMixin
from textual_vision.input_line import InputLine
from textual_vision.label import Label

from divide import themes
from divide.run import flowfunctions as ff
from divide.run import flowmodel as fm
from divide.ui.dialogs import _Dialog, confirm, information
from divide.ui.filter import Filtered, FilteredTree
from divide.ui.history import HistoryInput
from divide.ui.windows import EditorWindow, HRule, VRule, _TVWindow

CM_MENU_FUNCTION, CM_MENU_MODULE, CM_MENU_SETTINGS = Command.YES, Command.NO, Command.OK  # (a message box ends on these)
CM_MENU_SIMULATE = Command.USER + 246  # the selected Function's Mock Simulation
ROLE_LABELS = (_('~A~ctivity: does the work, its result kept under the Step id'),
               _('C~o~ndition: true runs the Step, false skips it'))


def _style(kind: str):
    return themes.current().token_styles()[kind]


CONTRACT = _(
    "A Function is a PHP file that returns a callable; Runner calls it with the Flow's shared context:\n\n"
    "  return function (array &$context): mixed { ... };\n\n"
    "- condition: true runs the Step's activity, call or jump; false skips them.\n"
    "- activity: what it returns is kept in $context[<the Step's id>].\n"
    "- module: the folder of a Step's condition and activity (not a Block).\n"
    "- $context['_importer']('name', 'module') gives another Function's callable.\n"
    "Any PHP is fine inside: Composer's autoload, other files, other Functions.")


# ---------------------------------------------------------------- dialogs
@dataclass(frozen=True)
class FunctionSpec:
    module: str | None
    name: str
    role: str  # activity | condition
    path: Path


class FunctionDialog(_Dialog):
    """A new Function: its Module (empty: the root), its name and what it is for; where it will be."""

    DEFAULT_CSS = """
    FunctionDialog { width: 72; height: 19; }
    FunctionDialog InputLine { width: 1fr; }
    FunctionDialog RadioButtons { width: 1fr; height: 2; }
    FunctionDialog .fn-where { height: 3; margin-top: 1; color: $text; background: $surface; }
    """

    def __init__(self, functions: fm.Functions, project: Path, *, module: str = "", name: str = "",
                 role: str = "activity", title: str = "") -> None:
        super().__init__(title=title or _('New Function'))
        self.functions, self.project = functions, project
        self.module_input = InputLine(max_len=128)
        self.module_input.data = module
        self.name_input = InputLine(max_len=128)
        self.name_input.data = name
        self.role = RadioButtons(list(ROLE_LABELS))
        self.role.value = 2 if role == "condition" else 1  # one bit per button
        self.where = Static("", classes="fn-where", markup=False)
        self.spec: FunctionSpec | None = None

    def compose_content(self) -> ComposeResult:
        yield Label(_('~M~odule (a folder of Functions; empty: the function root)'), link=self.module_input)
        yield HistoryInput(self.module_input, "flow-fn-module", offer=self.functions.module_names)
        yield Label(_('~N~ame (letters, digits, _ and -; in a Module also folder/name)'), link=self.name_input)
        yield self.name_input
        yield Label(_('~U~se'), link=self.role)
        yield self.role
        yield self.where
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('O~K~'), Command.OK, is_default=True, id="ok")
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.show_where()
        first = self.name_input if self.module_input.data or not self.functions.module_names() else self.module_input
        if self.name_input.data and self.module_input.data:
            first = self.name_input
        self.call_after_refresh(lambda: (first.tv_select_self(), first.select_all()))

    def on_input_line_changed(self, event) -> None:
        self.show_where()

    def _problem(self) -> tuple[str | None, Path | None]:
        module = self.module_input.data.strip() or None
        name = self.name_input.data.strip()
        if module and (problem := ff.module_name_problem(module)):
            return problem, None
        if not name:
            return _('Type its name'), None
        if problem := ff.function_name_problem(name, module):
            return problem, None
        path = ff.target(self.functions, module, name, self.project)
        if path.exists():
            return _('{path} is already there: open it instead').format(path=ff.shown(path, self.project)), path
        if problem := ff.where_problem(path, self.project):
            return problem, path
        return None, path

    def show_where(self) -> None:
        problem, path = self._problem()
        if problem is not None:
            self.where.update(Text("! " + problem, style=_style("diag.error")) if path is not None or self.name_input.data.strip() else problem)
            return
        module = self.module_input.data.strip()
        reference = f"module: {module}, " if module else ""
        made = "" if path.parent.is_dir() else " " + _('(its folder is made too)')
        self.where.update(_('Written to {path}{made}. The Step says {reference}{key}: {name}').format(
            path=ff.shown(path, self.project), made=made, reference=reference,
            key=self.role_name(), name=self.name_input.data.strip()))

    def role_name(self) -> str:
        return "condition" if self.role.value & 2 else "activity"

    def on_cluster_changed(self, event) -> None:
        self.show_where()

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        problem, path = self._problem()
        if problem is not None or path is None:
            self.app.notify(problem or _('Type its name'), severity="error", timeout=5)
            return False
        self.spec = FunctionSpec(self.module_input.data.strip() or None, self.name_input.data.strip(), self.role_name(), path)
        return True


class ModuleDialog(_Dialog):
    """A new Module: a folder under the function root."""

    DEFAULT_CSS = """
    ModuleDialog { width: 64; height: 11; }
    ModuleDialog InputLine { width: 1fr; }
    ModuleDialog .fn-where { height: 2; margin-top: 1; color: $text; background: $surface; }
    """

    def __init__(self, functions: fm.Functions, project: Path) -> None:
        super().__init__(title=_('New Module'))
        self.functions, self.project = functions, project
        self.name_input = InputLine(max_len=64)
        self.where = Static("", classes="fn-where", markup=False)
        self.module_name = ""

    def compose_content(self) -> ComposeResult:
        yield Label(_('~N~ame (letters, digits, _ and -): what a Step\'s module says'), link=self.name_input)
        yield self.name_input
        yield self.where
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('O~K~'), Command.OK, is_default=True, id="ok")
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.show_where()
        self.call_after_refresh(self.name_input.focus)

    def on_input_line_changed(self, event) -> None:
        self.show_where()

    def _problem(self) -> str | None:
        name = self.name_input.data.strip()
        if problem := ff.module_name_problem(name):
            return problem
        folder = ff.module_target(self.functions, name)
        if folder.exists():
            return _('Module {name} is already there: {path}').format(name=name, path=ff.shown(folder, self.project))
        return ff.where_problem(folder, self.project)

    def show_where(self) -> None:
        name = self.name_input.data.strip()
        if not name:
            self.where.update(_('A folder in {root}').format(root=ff.shown(self.functions.root, self.project)))
            return
        problem = self._problem()
        if problem is not None:
            self.where.update(Text("! " + problem, style=_style("diag.error")))
        else:
            self.where.update(_('Made at {path}').format(path=ff.shown(ff.module_target(self.functions, name), self.project)))

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        problem = self._problem()
        if problem is not None:
            self.app.notify(problem, severity="error", timeout=5)
            return False
        self.module_name = self.name_input.data.strip()
        return True


# ---------------------------------------------------------------- the window
@dataclass(frozen=True)
class Row:
    kind: str  # head | module | function | ref | missing | gone
    module: str | None = None
    name: str = ""
    ref: ff.Reference | None = None

    @property
    def key(self) -> tuple:
        if self.ref is not None:
            r = self.ref
            return (self.kind, str(r.flow), r.block, r.step, r.key)
        return (self.kind, self.module, self.name)


class FunctionTree(FilteredTree, Tree[Row], TVViewMixin):
    ICON_NODE = "► "  # Turbo Vision's own (CP437)
    ICON_NODE_EXPANDED = "▼ "
    DEFAULT_CSS = """
    FunctionTree {
        background: $window-content-background;
        color: $foreground;
        scrollbar-size: 1 1;
        scrollbar-background: $secondary;
        scrollbar-color: $background;
        scrollbar-corner-color: $secondary;
        padding: 0;
        width: 1fr;
    }
    FunctionTree > .tree--guides, FunctionTree > .tree--guides-hover, FunctionTree > .tree--guides-selected { color: $secondary; }
    FunctionTree > .tree--cursor, FunctionTree:focus > .tree--cursor { background: $secondary; text-style: none; }
    FunctionTree > .tree--highlight, FunctionTree > .tree--highlight-line { background: $window-content-background; }
    """
    BINDINGS = [
        Binding("enter", "enter", "Open", show=False),
        Binding("left", "close_node", "Close", show=False),
        Binding("right", "open_node", "Open", show=False),
    ]

    def __init__(self) -> None:
        super().__init__("", data=Row("head"))
        self.tv_options = OptionFlag.SELECTABLE
        self.guide_depth = 3
        self.auto_expand = False
        self.show_root = False

    def _window(self) -> "FunctionsWindow":
        return next(a for a in self.ancestors if isinstance(a, FunctionsWindow))

    def action_enter(self) -> None:
        self._window().enter()

    def action_close_node(self) -> None:
        node = self.cursor_node
        if node is None:
            return
        if node.allow_expand and node.is_expanded:
            node.collapse()
        elif node.parent is not None and node.parent is not self.root:
            self.move_cursor(node.parent)

    def action_open_node(self) -> None:
        node = self.cursor_node
        if node is None or not node.allow_expand:
            return
        if not node.is_expanded:
            node.expand()
        elif node.children:
            self.move_cursor(node.children[0])

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self.tv_select_self()


class FunctionsWindow(_TVWindow):
    """Modules and Functions | what the selected one is (its file, the Steps that use it, its callable)."""

    HINT = _('Enter open · ^F9 test · Alt+F10 menu (Simulate...) · Ins Function · Shift+Ins Module · ^R reload')
    BINDINGS = [
        Binding("insert", "new_function", show=False),
        Binding("shift+insert", "new_module", show=False),
        Binding("ctrl+r", "reload", show=False, priority=True),
        Binding("alt+f10,shift+f10", "local_menu", show=False),
    ]
    DEFAULT_CSS = """
    FunctionsWindow .fn-left { width: 1fr; height: 1fr; }
    FunctionsWindow .fn-right { width: 46; height: 1fr; }
    FunctionsWindow .fn-info { width: 1fr; height: auto; padding: 0 1; background: $window-content-background; color: $foreground; }
    FunctionsWindow VerticalScroll { background: $window-content-background; scrollbar-size: 1 1; }
    FunctionsWindow.narrow Horizontal { layout: vertical; }
    FunctionsWindow.narrow .fn-right { width: 1fr; height: 9; }
    FunctionsWindow.narrow VRule { display: none; }
    FunctionsWindow .fn-hrule { display: none; }
    FunctionsWindow.narrow .fn-hrule { display: block; }
    """

    def __init__(self, source: EditorWindow | None, number: int = 0) -> None:
        self.source = source  # the Flow it was opened from (its Run Flow settings), or None: the project's
        super().__init__(self._make_title(), number=number)
        self.fn_tree = FunctionTree()
        self.info = Static("", classes="fn-info")
        self.catalog: ff.Catalog | None = None

    def _make_title(self) -> str:
        if self.source is not None:
            return _('Functions: {flow}').format(flow=self.source.display_name)
        return _('Functions')

    def compose_content(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes="fn-left"):
                yield Filtered(self.fn_tree)
            yield VRule()
            yield HRule(classes="fn-hrule")
            with VerticalScroll(classes="fn-right"):
                yield self.info

    def on_mount(self) -> None:
        self.call_after_refresh(self.reload)
        self.call_after_refresh(self.fn_tree.focus)
        self.call_after_refresh(self.app.update_status)  # type: ignore[attr-defined]
        self.app.theme_changed_signal.subscribe(self, lambda _theme: self.call_after_refresh(self.rebuild))

    def on_resize(self, event: events.Resize) -> None:
        self._narrow(event.size.width)

    def _narrow(self, width: int) -> None:
        """Under 100 columns the panel goes under the tree. Also from the window's own size when it is
        filled (#33): its Resize may come after that, so the class never waits for it."""
        if width:
            self.set_class(width < 100, "narrow")

    # ------------------------------------------------------------ data
    @property
    def project(self) -> Path:
        return self.app.root  # type: ignore[attr-defined]

    def functions(self) -> fm.Functions:
        return self.app.flow_functions(self.source)  # type: ignore[attr-defined]

    def reload(self) -> None:
        """The disk (and the open Flows' buffers) again."""
        app = self.app
        texts = {w.path: w.editor.text for w in app.editor_windows()  # type: ignore[attr-defined]
                 if w.path is not None and app.is_flow_editor(w)}  # type: ignore[attr-defined]
        flows = ff.scan_flows(self.project)
        keys = {ff._key(p) for p in flows}
        for path in texts:
            if ff._key(path) not in keys:
                flows.append(path)
        self.catalog = ff.catalog(self.project, self.functions(), flows=flows, texts=texts)
        self._narrow(self.size.width)
        self.rebuild()

    def action_reload(self) -> None:
        self.reload()

    # ------------------------------------------------------------ the tree
    def _rel(self, path: Path) -> str:
        return ff.shown(path, self.project)

    def rebuild(self, cursor: tuple | None = None) -> None:
        cat = self.catalog
        if cat is None or not self.is_mounted:
            return
        tree = self.fn_tree
        if cursor is None and tree.cursor_node is not None and tree.cursor_node.data is not None:
            cursor = tree.cursor_node.data.key
        opened = self._opened()
        dim, key_style = _style("div.comment"), _style("json.key")
        err, warn = _style("diag.error"), _style("diag.warning")
        tree.clear()
        found: list = []

        def note(node, row: Row) -> None:
            if row.key == cursor:
                found.append(node)

        head = Text(_('Function root '), style=dim)
        head.append(self._rel(cat.functions.root) + "/", style=key_style)
        head.append(f"  ({self._origin(cat.functions.origin)})", style=dim)
        row = Row("head")
        node = tree.root.add(head, data=row, expand=True)
        note(node, row)
        for entry in cat.root_functions:
            self._function_node(node, entry, opened, note)
        if not cat.root_functions:
            node.add_leaf(Text(_('(no Functions here)'), style=dim), data=Row("gone"))
        for module in cat.modules:
            label = Text()
            label.append(module.name, style=key_style)
            label.append("/", style=dim)
            label.append(f"  {len(module.functions)}", style=dim)
            if module.origin != fm.MODULE_FOLDER:
                label.append(f"  -> {self._rel(module.folder)}", style=dim)
            if not module.exists:
                label.append("  " + _('(no folder)'), style=warn)
            elif not module.inside:
                label.append("  " + _('(outside: read-only)'), style=dim)
            row = Row("module", module.name)
            mnode = tree.root.add(label, data=row, expand=row.key in opened or not opened)
            note(mnode, row)
            for entry in module.functions:
                self._function_node(mnode, entry, opened, note)
        missing = cat.missing
        if missing:
            label = Text("! ", style=err)
            label.append(_('Not found'), style=key_style)
            label.append(f"  {len(missing)}", style=dim)
            row = Row("missing")
            mnode = tree.root.add(label, data=row, expand=True)
            note(mnode, row)
            for ref in missing:
                label = Text("! " if not ref.may_be_callable else "? ", style=err if not ref.may_be_callable else warn)
                label.append(ref.qualified, style=key_style)
                label.append(f"  {ref.key} · {self._step_label(ref)}", style=dim)
                row = Row("gone", ref.module, ref.name, ref)
                note(mnode.add_leaf(label, data=row), row)
        tree.root.expand()
        if found:
            target = found[0]
            parent = target.parent
            while parent is not None:
                parent.expand()
                parent = parent.parent
            self.call_after_refresh(lambda: (tree.move_cursor(target), self.show_selected()))
        else:
            self.call_after_refresh(self.show_selected)

    def _function_node(self, parent, entry: ff.FunctionEntry, opened: set, note) -> None:
        dim, err, warn = _style("div.comment"), _style("diag.error"), _style("diag.warning")
        label = Text()
        problems = [p for p in (entry.source.problems if entry.source else ()) if p[0] in ("error", "warning")]
        if problems:
            label.append("! ", style=err if any(p[0] == "error" for p in problems) else warn)
        label.append(entry.name)
        uses = ", ".join(entry.roles)
        count = len(entry.references)
        label.append("  " + (f"{uses} · " if uses else "") + (_('{n} Step(s)').format(n=count) if count else _('no Step')), style=dim)
        row = Row("function", entry.module, entry.name)
        if entry.references:
            node = parent.add(label, data=row, expand=row.key in opened)
            for ref in entry.references:
                rrow = Row("ref", entry.module, entry.name, ref)
                note(node.add_leaf(Text(f"{self._step_label(ref)}  ({ref.key})", style=dim), data=rrow), rrow)
        else:
            node = parent.add_leaf(label, data=row)
        note(node, row)

    def _step_label(self, ref: ff.Reference) -> str:
        if self.source is not None and self.source.path is not None and ff._key(self.source.path) == ff._key(ref.flow):
            return ref.step_name
        return f"{ref.flow.name}: {ref.step_name}"

    def _opened(self) -> set:
        out: set = set()

        def walk(node) -> None:
            for child in node.children:
                if child.is_expanded and child.data is not None:
                    out.add(child.data.key)
                walk(child)
        walk(self.fn_tree.root)
        return out

    def _origin(self, origin: str) -> str:
        return {fm.ROOT_OPTION: _('--root of the Run Flow dialog'), fm.ROOT_CONTEXT: _("the context's _root_folder"),
                fm.ROOT_SETTINGS: ".div/runner.json", fm.ROOT_PROJECT: _('the project: Runner\'s default')}.get(origin, origin)

    def rows(self) -> list[str]:
        """The visible rows as text (for tests)."""
        out = []
        for line in range(self.fn_tree.last_line + 1):
            node = self.fn_tree.get_node_at_line(line)
            if node is not None:
                out.append(node.label.plain if isinstance(node.label, Text) else str(node.label))
        return out

    # ------------------------------------------------------------ the selection
    def selected(self) -> Row | None:
        node = self.fn_tree.cursor_node
        return node.data if node is not None else None

    def select(self, key: tuple) -> None:
        self.rebuild(cursor=key)

    def on_tree_node_highlighted(self, event) -> None:
        self.show_selected()

    def show_selected(self) -> None:
        if self.is_mounted and self.catalog is not None:
            self.info.update(self.describe(self.selected()))

    def describe(self, row: Row | None) -> Text:
        cat = self.catalog
        text = Text()
        dim, key_style = _style("div.comment"), _style("json.key")
        err, warn = _style("diag.error"), _style("diag.warning")

        width = max(24, (self.info.size.width or 44) - 2)  # its padding

        def line(name: str, value: str, style=None) -> None:
            text.append(f"{name:<10} ", style=dim)
            filled = textwrap.fill(value, width=width, initial_indent=" " * 11, subsequent_indent=" " * 11,
                                   break_on_hyphens=False, break_long_words=False)
            text.append(filled[11:] + "\n", style=style)

        def head(kind: str, name: str) -> None:
            text.append(kind + " ", style=dim)
            text.append(name + "\n\n", style=key_style)

        functions = cat.functions
        if row is None or row.kind in ("head", "gone") and row.ref is None:
            head(_('Function root'), self._rel(functions.root) + "/")
            line(_('from'), self._origin(functions.origin))
            line(_('settings'), (ff.SETTINGS.as_posix() if cat.settings.exists else _('none (Alt+F10 makes one)')))
            for problem in cat.settings.problems:
                text.append("! " + problem + "\n", style=err)
            if not cat.root_inside():
                text.append(_('Outside the project: Functions are not made there.') + "\n", style=warn)
            text.append("\n" + _('Where Runner looks, first that gives one:') + "\n", style=dim)
            text.append(_('root: --root, the context\'s _root_folder, .div/runner.json "root", the project') + "\n")
            text.append(_('a Module: the context\'s _modules, .div/runner.json "modules", <root>/<module>') + "\n\n")
            text.append(CONTRACT + "\n")
            return text
        if row.kind == "module":
            module = cat.module(row.module or "")
            if module is None:
                return text
            head(_('Module'), module.name)
            line(_('folder'), self._rel(module.folder) + ("" if module.exists else "  " + _('(not there)')))
            line(_('from'), {fm.MODULE_FOLDER: _('a folder of the root'), fm.MODULE_CONTEXT: _("the context's _modules"),
                             fm.MODULE_SETTINGS: ".div/runner.json"}.get(module.origin, module.origin))
            line(_('functions'), str(len(module.functions)))
            if not module.inside:
                text.append(_('Outside the project: shown, never written (no new Functions there).') + "\n", style=warn)
            text.append("\n" + _('A Step uses it with module: {name}, and its condition and activity are files of this folder. '
                                 'A Module is not a Block.').format(name=module.name) + "\n", style=dim)
            text.append(_('Ins makes a Function here.') + "\n", style=dim)
            return text
        if row.kind == "missing":
            head(_('Not found'), str(len(cat.missing)))
            text.append(_('References of Steps that resolve to no file. Enter on one makes it (the Step is not changed). '
                          '? : not a file; Runner tries a PHP callable of that name (strlen, ns\\fn, Cls::method).') + "\n", style=dim)
            return text
        if row.kind == "gone" and row.ref is not None:
            ref = row.ref
            head(_('Missing'), ref.qualified)
            line(_('used by'), f"{self._step_label(ref)} ({ref.key})")
            tried = functions.candidates(ref.name, ref.module, self.project) if not (ref.module and fm.module_problem(ref.module, ref.name)) else []
            for i, path in enumerate(tried):
                line(_('looked at') if i == 0 else "", self._rel(path))
            if ref.may_be_callable:
                text.append("\n" + _('Runner also tries a PHP callable of that name: a function or Cls::method of the code.') + "\n", style=warn)
            text.append("\n" + _('Enter makes it, from a template, and opens it.') + "\n", style=dim)
            return text
        entry = cat.entry(row.module, row.name)
        if entry is None:
            return text
        head(_('Function'), entry.qualified)
        line(_('file'), self._rel(entry.path))
        if entry.module:
            line(_('module'), entry.module)
        source = entry.source
        if source is not None:
            form = {"closure": _('a closure'), "arrow": _('an arrow function'), "other": _('another callable (not read here)'),
                    "none": _('nothing'), "unknown": _('(cannot be read: see PHP\'s lint)')}.get(source.form, source.form)
            line(_('returns'), form + (f" {source.signature}" if source.signature else ""))
        refs = entry.references
        line(_('used by'), ", ".join(f"{self._step_label(r)} ({r.key})" for r in refs) if refs else _('no Step'))
        imports = source.imports if source is not None else ()
        if imports:
            line(_('imports'), ", ".join(f"{i.qualified} (line {i.line})" if not i.dynamic else _('? (line {n}: computed, unknown)').format(n=i.line)
                                       for i in imports))
        if entry.imported_by:
            line(_('imported'), ", ".join(f"{e.qualified} (line {i.line})" for e, i in entry.imported_by))
        for severity, message, at in (source.problems if source is not None else ()):
            style = err if severity == "error" else warn if severity == "warning" else dim
            text.append(f"\n{'!' if severity != 'note' else '-'} {at}: {message}", style=style)
        text.append("\n\n" + _('Enter opens it. Runner keeps an activity\'s result under the Step id.') + "\n", style=dim)
        return text

    # ------------------------------------------------------------ actions
    def enter(self) -> None:
        row = self.selected()
        if row is None:
            return
        app = self.app
        if row.kind == "function":
            entry = self.catalog.entry(row.module, row.name) if self.catalog else None
            if entry is not None:
                app.flow_open_function_file(entry.path)  # type: ignore[attr-defined]
        elif row.kind == "ref" and row.ref is not None:
            app.flow_goto_reference(row.ref)  # type: ignore[attr-defined]
        elif row.kind == "gone" and row.ref is not None:
            ref = row.ref
            self.new_function(ref.module or "", ref.name, ref.key)
        elif row.kind in ("module", "head", "missing"):
            node = self.fn_tree.cursor_node
            if node is not None and node.allow_expand:
                node.toggle()

    def action_new_function(self) -> None:
        row = self.selected()
        module = row.module or "" if row is not None and row.kind in ("module", "function") else ""
        self.new_function(module)

    def new_function(self, module: str = "", name: str = "", role: str = "activity") -> None:
        self.app.flow_new_function(self, module, name, role)  # type: ignore[attr-defined]

    def action_new_module(self) -> None:
        self.app.flow_new_module(self)  # type: ignore[attr-defined]

    def action_local_menu(self) -> None:
        self.app.flow_functions_menu(self)  # type: ignore[attr-defined]


# ---------------------------------------------------------------- app side
class FlowFunctionsMixin:
    """The Functions window and the making of Modules and Functions (mixed into the Divide app)."""

    def functions_windows(self) -> list[FunctionsWindow]:
        return [w for w in self.windows() if isinstance(w, FunctionsWindow)]  # type: ignore[attr-defined]

    def open_flow_functions(self, source: EditorWindow | None = None) -> FunctionsWindow:
        """Run > Flow functions: the window of the Flow's Functions (raised and read again if it is open)."""
        win = next((w for w in self.functions_windows() if w.source is source), None)
        if win is None:
            win = FunctionsWindow(source, number=self._free_number())  # type: ignore[attr-defined]
            self._insert(win)  # type: ignore[attr-defined]
        else:
            self.raise_window(win)  # type: ignore[attr-defined]
            win.reload()
        return win

    def refresh_functions_windows(self) -> None:
        for win in self.functions_windows():
            if win.is_mounted:
                win.reload()

    def flow_open_function_file(self, path: Path) -> EditorWindow | None:
        """A Function in the PHP editor, at its top-level ``return`` (the callable)."""
        win = self.open_file(path)  # type: ignore[attr-defined]
        if win is None:
            return None
        info = ff.inspect_source(path)
        if info.line:
            text = win.editor.text
            lines = text.split("\n")
            start = sum(len(x) + 1 for x in lines[: info.line - 1])
            self.call_after_refresh(lambda: self._select_in(win, start))  # type: ignore[attr-defined]
        return win

    def flow_goto_reference(self, ref: ff.Reference) -> None:
        """A Step that uses a Function: in the Flow Designer (the Flow opened if it is not)."""
        source = next((w for w in self.editor_windows() if w.path is not None  # type: ignore[attr-defined]
                       and ff._key(w.path) == ff._key(ref.flow)), None)
        if source is None:
            source = self.open_file(ref.flow)  # type: ignore[attr-defined]
        if source is not None:
            self.open_flow_window(source, "design", ("step", ref.block, ref.step))  # type: ignore[attr-defined]

    def flow_new_function(self, win: FunctionsWindow | None, module: str = "", name: str = "", role: str = "activity",
                          source: EditorWindow | None = None) -> None:
        self._flow_new_function(win, module, name, role, source)

    @work(group="flowfunctions", exclusive=True)
    async def _flow_new_function(self, win, module, name, role, source) -> None:
        source = win.source if win is not None else source
        functions = self.flow_functions(source)  # type: ignore[attr-defined]
        dialog = FunctionDialog(functions, self.root, module=module, name=name, role=role)  # type: ignore[attr-defined]
        if await self.run_dialog(dialog) != Command.OK or dialog.spec is None:  # type: ignore[attr-defined]
            return
        spec = dialog.spec
        try:
            made = ff.create_function(functions, self.root, spec.module, spec.name, spec.role)  # type: ignore[attr-defined]
        except ff.CreateError as exc:
            await self.run_dialog(information(_('New Function'), str(exc)))  # type: ignore[attr-defined]
            return
        self.notify(_('Made {path}').format(path=ff.shown(made.path, self.root)), timeout=3)  # type: ignore[attr-defined]
        self.refresh_functions_windows()
        self.refresh_flow_checks()
        if win is not None:
            win.select(("function", spec.module, spec.name))
        self.flow_open_function_file(made.path)

    def flow_new_module(self, win: FunctionsWindow) -> None:
        self._flow_new_module(win)

    @work(group="flowfunctions", exclusive=True)
    async def _flow_new_module(self, win: FunctionsWindow) -> None:
        functions = self.flow_functions(win.source)  # type: ignore[attr-defined]
        dialog = ModuleDialog(functions, self.root)  # type: ignore[attr-defined]
        if await self.run_dialog(dialog) != Command.OK or not dialog.module_name:  # type: ignore[attr-defined]
            return
        try:
            made = ff.create_module(functions, self.root, dialog.module_name)  # type: ignore[attr-defined]
        except ff.CreateError as exc:
            await self.run_dialog(information(_('New Module'), str(exc)))  # type: ignore[attr-defined]
            return
        self.notify(_('Made {path}').format(path=ff.shown(made.path, self.root)), timeout=3)  # type: ignore[attr-defined]
        win.reload()
        win.select(("module", dialog.module_name, ""))

    def flow_functions_menu(self, win: FunctionsWindow) -> None:
        self._flow_functions_menu(win)

    @work(group="flowfunctions", exclusive=True)
    async def _flow_functions_menu(self, win: FunctionsWindow) -> None:
        from divide.ui.dialogs import MessageBox
        box = MessageBox(_('Functions'), _('What now?'), [
            (_('~F~unction...'), CM_MENU_FUNCTION, "function"),
            (_('Si~m~ulate...'), CM_MENU_SIMULATE, "simulate"),
            (_('~M~odule...'), CM_MENU_MODULE, "module"),
            (_('~S~ettings'), CM_MENU_SETTINGS, "settings"),
            (_('Cancel'), Command.CANCEL, "cancel")], width=70)
        answer = await self.run_dialog(box)  # type: ignore[attr-defined]
        if answer == CM_MENU_FUNCTION:
            win.action_new_function()
        elif answer == CM_MENU_MODULE:
            win.action_new_module()
        elif answer == CM_MENU_SETTINGS:
            await self._flow_settings_file(win)
        elif answer == CM_MENU_SIMULATE:
            self.raise_window(win)  # type: ignore[attr-defined]
            await self.function_simulate_command()  # type: ignore[attr-defined]

    async def _flow_settings_file(self, win: FunctionsWindow) -> None:
        """The project's ``.div/runner.json`` in the editor, made (after asking) with the root shown now."""
        path = self.root / ff.SETTINGS  # type: ignore[attr-defined]
        if not path.exists():
            functions = win.catalog.functions if win.catalog is not None else self.flow_functions(win.source)  # type: ignore[attr-defined]
            root = ff.shown(functions.root, self.root) if ff.inside(functions.root, self.root) else ""  # type: ignore[attr-defined]
            root = "" if root == "." else root
            ask = _('Make {file}, the project\'s function root ({root}) and Module folders, shared with the team in Git?').format(
                file=ff.SETTINGS.as_posix(), root=root or _('the project'))
            if await self.run_dialog(confirm(_('Functions'), ask)) != Command.YES:  # type: ignore[attr-defined]
                return
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "x", encoding="utf-8", newline="\n") as handle:
                    handle.write(ff.settings_text(root))
            except OSError as exc:
                await self.run_dialog(information(_('Functions'), str(exc)))  # type: ignore[attr-defined]
                return
        self.open_file(path)  # type: ignore[attr-defined]

    def flow_functions_saved(self, path: Path) -> None:
        """A file was saved: a Function, a Flow or the project's settings may say something else now."""
        settings = ff._key(path) == ff._key(self.root / ff.SETTINGS)  # type: ignore[attr-defined]
        suffix = path.suffix.lower()
        if settings or suffix in (".php", ".yml", ".yaml"):
            self.refresh_functions_windows()
        if settings or suffix == ".php":
            self.refresh_flow_checks()

    def refresh_flow_checks(self) -> None:
        """The Flows' marks again (a Function was made, a settings file saved)."""
        for win in self.editor_windows():  # type: ignore[attr-defined]
            if self.is_flow_editor(win):  # type: ignore[attr-defined]
                self.check_flow(win.editor)  # type: ignore[attr-defined]
