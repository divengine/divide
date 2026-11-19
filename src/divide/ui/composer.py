"""Tools > Composer packages: the project's packages, and composer run for them.

``ComposerMixin`` is part of the app. The window lists what ``composer.json``
requires (and its dev packages, the dependencies composer installed with
them, and the platform: php, extensions), with the installed version from
``composer.lock``; beside the list, the focused package. Composer itself does
every change, under the progress box, its output in the "Composer" window:

- **Ins**: add a package (an assistant: search Packagist as you type, the
  version suggested from the newest stable one, dev or not);
- **Del**: remove a package the project requires;
- **Enter**: the package's folder in the project window;
- **Alt+F10**: update the package or everything, install, look for newer
  versions, validate, dump the autoloader, open composer.json, choose
  composer, and a new composer.json (an assistant) when there is none.
"""

from __future__ import annotations

from divide.i18n import _

from dataclasses import dataclass
from pathlib import Path

from rich.style import Style
from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, Tree
from textual_vision.button import Button
from textual_vision.cluster import CheckBoxes, RadioButtons
from textual_vision.constants import Command, OptionFlag
from textual_vision.group import TVViewMixin
from textual_vision.input_line import InputLine
from textual_vision.label import Label
from textual_vision.list_box import ListBox

from divide import config, themes
from divide.editor.theme import OUTPUT
from divide.run import composer as cmp
from divide.ui.dialogs import _Dialog, information, confirm
from divide.ui.filter import Filtered, FilteredTree
from divide.ui.progress import ProgressDialog, run_with_progress
from divide.ui.windows import EditorView, HRule, OUTPUT_CSS, VRule, WheelList, _TVWindow

LOG_LINES = 2000

CM_CP_ADD = Command.USER + 140
CM_CP_REMOVE = Command.USER + 141
CM_CP_UPDATE = Command.USER + 142
CM_CP_UPDATE_ALL = Command.USER + 143
CM_CP_INSTALL = Command.USER + 144
CM_CP_OUTDATED = Command.USER + 145
CM_CP_VALIDATE = Command.USER + 146
CM_CP_DUMP = Command.USER + 147
CM_CP_JSON = Command.USER + 148
CM_CP_NEW = Command.USER + 149
CM_CP_PROGRAM = Command.USER + 150
CM_CP_FOLDER = Command.USER + 151


def _styles(view: EditorView) -> tuple[Style, Style]:
    from divide.ui.dialector import _editor_styles
    return _editor_styles(view)


# Colour slots of the rows (every palette gives each a colour that reads on its windows).
GROUP, VENDOR, REQUIRED, DEPENDENCY, PLATFORM, NEWER = (
    "lightcyan", "cyan", "white", "lightgray", "lightmagenta", "lightgreen")


@dataclass(frozen=True)
class Row:
    """A row of the tree: a group (runtime, development, platform), a vendor, or a package."""

    kind: str  # "group" | "vendor" | "package"
    key: str  # the group's id, "group:vendor", or the package's name
    package: cmp.Package | None = None


def tree_of(packages: list[cmp.Package]) -> list[tuple[str, str, list[tuple[str, list[cmp.Package]]]]]:
    """(group id, title, [(vendor, packages)]): runtime, development, platform; each
    vendor and its packages in alphabetical order. The platform has no vendors ("")."""
    groups = [("runtime", _("Runtime (require)")), ("dev", _("Development (require-dev)")),
              ("platform", _("Platform (php, extensions)"))]
    out = []
    for gid, title in groups:
        members = [p for p in packages if (p.platform if gid == "platform" else not p.platform and p.dev == (gid == "dev"))]
        if not members:
            continue
        vendors: dict[str, list[cmp.Package]] = {}
        for p in members:
            vendor = "" if p.platform else p.name.split("/", 1)[0]
            vendors.setdefault(vendor, []).append(p)
        out.append((gid, title, [(v, sorted(vendors[v], key=lambda p: p.name)) for v in sorted(vendors)]))
    return out


class PackageTree(FilteredTree, Tree[Row], TVViewMixin):
    """Runtime / development / platform, the vendors under them, then the packages:
    a required one (composer.json) bright, a dependency (it came with them) dim."""

    ICON_NODE = "► "  # Turbo Vision's own (CP437), like the outline's
    ICON_NODE_EXPANDED = "▼ "
    BINDINGS = [
        Binding("right", "unfold", "Unfold", show=False),
        Binding("left", "fold", "Fold", show=False),
    ]
    DEFAULT_CSS = """
    PackageTree {
        width: 1fr; height: 1fr;
        background: $divide-editor-bg;
        color: $divide-editor-text;
        scrollbar-size: 0 0;
        padding: 0;
    }
    PackageTree > .tree--guides, PackageTree > .tree--guides-hover, PackageTree > .tree--guides-selected {
        color: $divide-editor-gutter;
    }
    PackageTree > .tree--cursor, PackageTree:focus > .tree--cursor {
        color: $divide-editor-selection; background: $divide-editor-selection-bg; text-style: none;
    }
    PackageTree > .tree--highlight, PackageTree > .tree--highlight-line { background: $divide-editor-bg; }
    """

    def __init__(self, window: "ComposerWindow") -> None:
        super().__init__("packages")
        self._window = window
        self.show_root = False
        self.auto_expand = False  # Enter: the package's folder; Space and the arrows fold
        self.guide_depth = 2
        self.tv_options = OptionFlag.SELECTABLE
        self.name_width = 24

    def on_mount(self) -> None:
        self.app.theme_changed_signal.subscribe(self, lambda _theme: self.repaint())

    def repaint(self) -> None:
        self._invalidate()
        self.refresh()

    def filter_text_of(self, node) -> str:
        row: Row | None = node.data
        return row.key if row is not None and row.kind == "package" else str(node.label)

    def render_label(self, node, base_style, style):
        row: Row | None = node.data
        palette = themes.current()
        if row is None:  # (no packages)
            return Text.assemble(("  ", base_style), (str(node.label), base_style + style))
        if row.kind == "group":
            label = Text(str(node.label), Style(color=palette.hex(GROUP), bold=True))
        elif row.kind == "vendor":
            label = Text(str(node.label), Style(color=palette.hex(VENDOR)))
        else:
            p = row.package
            assert p is not None
            colour = PLATFORM if p.platform else REQUIRED if p.direct else DEPENDENCY
            short = p.name if p.platform else p.name.split("/", 1)[1]
            newer = p.name in self._window.latest
            label = Text.assemble(
                ("↑" if newer else " ", Style(color=palette.hex(NEWER), bold=True)),
                (f"{short:<{self.name_width}.{self.name_width}} ", Style(color=palette.hex(colour), bold=p.direct)),
                (p.version or p.constraint or "", Style(color=palette.hex(colour))),
            )
        if self.cursor_node is node:
            label.stylize(style)  # the bar: one colour from end to end
        if node.allow_expand:
            prefix = (self.ICON_NODE_EXPANDED if node.is_expanded else self.ICON_NODE, base_style)
        else:
            prefix = ("  ", base_style)
        return Text.assemble(prefix, label)

    def action_unfold(self) -> None:
        node = self.cursor_node
        if node is not None and node.allow_expand:
            if node.is_expanded and node.children:
                self.move_cursor(node.children[0])
            else:
                node.expand()

    def action_fold(self) -> None:
        node = self.cursor_node
        if node is None:
            return
        if node.allow_expand and node.is_expanded:
            node.collapse()
        elif node.parent is not None and node.parent is not self.root:
            self.move_cursor(node.parent)

    async def _on_click(self, event: events.Click) -> None:
        # a click puts the bar on a row, a double click opens it; ► ▼ fold
        meta = event.style.meta
        if event.button == 1 and "line" in meta and not meta.get("toggle", False):
            event.prevent_default()
            self.cursor_line = meta["line"]
            if event.chain >= 2:
                self.action_select_cursor()


class ComposerWindow(_TVWindow):
    """Packages | the focused one, with the project's state below the tree."""

    HINT = _('Ins add · Del remove · Enter its folder · Space fold · Ctrl+R reload · Alt+F10 update, install, outdated')
    BINDINGS = [
        Binding("insert", "add", show=False),
        Binding("delete", "remove", show=False),
        Binding("ctrl+r", "reload", show=False),
        Binding("alt+f10,shift+f10", "local_menu", show=False),
    ]
    DEFAULT_CSS = """
    ComposerWindow .cp-left { width: 50; height: 1fr; }
    ComposerWindow .cp-state { height: 4; padding: 0 1; }
    ComposerWindow .cp-right { height: 1fr; width: 1fr; }
    ComposerWindow .cp-info { padding: 0 1; }
    """

    def __init__(self, root: Path, number: int = 0) -> None:
        self.project_root = root
        super().__init__(_('Composer packages'), number=number)
        self.packages = PackageTree(self)
        self.state = Static("", classes="cp-state", markup=False)
        self.info = Static("", classes="cp-info", markup=False)
        self.palette_view = EditorView("", read_only=True)  # only lends its colours
        self.project: cmp.Project = cmp.read(root)
        self.latest: dict[str, str] = {}
        self.package: cmp.Package | None = None  # the focused one
        self._folded: set[str] = set()  # the groups and vendors folded, kept across reloads
        self.last: str | None = None  # the last command and how it ended

    def compose_content(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes="cp-left"):
                yield Filtered(self.packages)
                yield HRule()
                yield self.state
            yield VRule()
            with VerticalScroll(classes="cp-right"):
                yield self.info

    def on_mount(self) -> None:
        self.call_after_refresh(self.paint)
        self.call_after_refresh(self.reload)
        self.call_after_refresh(self.packages.focus)
        self.app.theme_changed_signal.subscribe(self, lambda _theme: self.call_after_refresh(self.paint))

    def paint(self) -> None:
        normal, _focused = _styles(self.palette_view)
        bg = Color.from_rich_color(normal.bgcolor) if normal.bgcolor else None
        fg = Color.from_rich_color(normal.color) if normal.color else None
        for box in (self.state, self.info, self.query_one(".cp-left"), self.query_one(".cp-right")):
            box.styles.background = bg
            box.styles.color = fg
        self.packages.repaint()

    # ------------------------------------------------------------ view
    def reload(self) -> None:
        """composer.json and composer.lock again (after composer ran, or Ctrl+R)."""
        self.project = cmp.read(self.project_root)
        tree = self.packages
        cursor = tree.cursor_node
        keep = cursor.data.key if cursor is not None and cursor.data is not None else None
        tree.clear()
        names = [p.name if p.platform else p.name.split("/", 1)[-1] for p in self.project.packages]
        tree.name_width = min(28, max([12, *map(len, names)]))
        first = None
        for gid, title, vendors in tree_of(self.project.packages):
            count = sum(len(members) for _vendor, members in vendors)
            group = tree.root.add(f"{title}  {count}", Row("group", gid), expand=gid not in self._folded)
            for vendor, members in vendors:
                parent = group
                if vendor:
                    key = f"{gid}:{vendor}"
                    parent = group.add(f"{vendor}/", Row("vendor", key), expand=key not in self._folded)
                for p in members:
                    leaf = parent.add_leaf(p.name, Row("package", p.name, p))
                    first = first or leaf
        if not self.project.packages:
            tree.root.add_leaf(_('(no packages)'), None)
        kept = self._node(keep) if keep else None
        if kept is not None and kept.data.kind != "package":  # a group or a vendor, maybe folded
            tree.call_after_refresh(lambda: tree.move_cursor(kept, animate=False))
            self.package_focused(None, kept.data)
        elif (kept or first) is None or not self.focus_package((kept or first).data.key):
            self.package_focused(None)
        self.show_state()

    def rows(self) -> list[str]:
        """The visible rows as text (the tree's lines, without colours)."""
        out = []
        for line in range(self.packages.last_line + 1):
            node = self.packages.get_node_at_line(line)
            if node is None:
                continue
            row = node.data
            if row is not None and row.kind == "package" and row.package is not None:
                p = row.package
                mark = "↑" if p.name in self.latest else " "
                out.append(f"{mark}{p.name} {p.version or p.constraint or ''}")
            else:
                out.append(str(node.label))
        return out

    def _node(self, key: str):
        """The tree's node of a row (a package's name, a group's id, "group:vendor")."""
        def find(node):
            for child in node.children:
                if child.data is not None and child.data.key == key:
                    return child
                found = find(child)
                if found is not None:
                    return found
            return None
        return find(self.packages.root)

    def focus_package(self, name: str) -> bool:
        """Put the bar on a package (unfolding its group and vendor)."""
        node = self._node(name)
        if node is None or node.data.kind != "package":
            return False
        parent = node.parent
        while parent is not None and parent is not self.packages.root:
            parent.expand()
            parent = parent.parent
        tree = self.packages
        tree.call_after_refresh(lambda: tree.move_cursor(node, animate=False))  # once its line is known
        self.package_focused(node.data.package)
        return True

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        event.stop()
        row = event.node.data
        self.package_focused(row.package if row is not None and row.kind == "package" else None, row)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        event.stop()
        row = event.node.data
        if row is None:
            return
        if row.kind == "package":
            self.app.composer_action(self, "folder")  # type: ignore[attr-defined]
        else:
            event.node.toggle()

    def on_tree_node_collapsed(self, event: Tree.NodeCollapsed) -> None:
        event.stop()
        if event.node.data is not None:
            self._folded.add(event.node.data.key)

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        event.stop()
        if event.node.data is not None:
            self._folded.discard(event.node.data.key)

    def show_state(self) -> None:
        project = self.project
        if project.problem:
            lines = [f"[!] {project.problem}"]
        elif project.json is None:
            lines = [_("No composer.json: Alt+F10 > New composer.json"), _("starts the project with Div in it.")]
        else:
            direct = sum(p.direct and not p.platform for p in project.packages)
            deps = sum(not p.direct for p in project.packages)
            lines = [_("{name}: {direct} required, {deps} with them").format(name=project.name, direct=direct, deps=deps),
                     _("Bright: in composer.json · dim: came with them")]
            if project.lock is None:
                lines.append(_("Not installed yet: Alt+F10 > Install"))
            elif not project.installed:
                lines.append(_("vendor/ is missing: Alt+F10 > Install"))
            if self.latest:
                lines.append(_("{count} with a newer version (marked ↑)").format(count=len(self.latest)))
        if self.last:
            lines.append(self.last)
        self.state.update("\n".join(lines))

    def package_focused(self, package: cmp.Package | None, row: Row | None = None) -> None:
        self.package = package
        p = package
        if p is None:
            if row is not None and row.kind == "vendor":
                vendor = row.key.split(":", 1)[1]
                members = [q for q in self.project.packages if q.name.startswith(vendor + "/")]
                self.info.update("\n".join([f"{vendor}/", "─" * (len(vendor) + 1)] + [f"  {q.name}  {q.version or q.constraint or ''}" for q in members]))
            elif row is not None and row.kind == "group":
                self.info.update(str({"runtime": _("What the project needs to run (require), and what came with it."),
                                      "dev": _("What the project needs only while it is developed (require-dev), and what came with it."),
                                      "platform": _("PHP and its extensions: composer checks them, it does not install them.")}[row.key]))
            else:
                self.info.update(_("Ins adds a package (Div is divengine/div)."))
            return
        lines = [p.name, "─" * len(p.name)]
        if p.description:
            lines += [p.description, ""]
        rows = [
            (_("Kind"), p.kind),
            (_("Required"), p.constraint or ""),
            (_("Installed"), p.version or _("not installed")),
            (_("Newer"), self.latest.get(p.name, "")),
            (_("Type"), p.type),
            (_("License"), ", ".join(p.license)),
            (_("Homepage"), p.homepage),
            (_("Source"), p.source),
        ]
        width = max(len(label) for label, _value in rows)
        lines += [f"{label:<{width}}  {value}" for label, value in rows if value]
        if p.requires:
            lines += ["", _("It requires:")]
            lines += [f"  {name} {constraint}" for name, constraint in sorted(p.requires.items())]
        users = [q.name for q in self.project.packages if p.name in q.requires]
        if users:
            lines += ["", _("Required by:")] + [f"  {name}" for name in users]
        self.info.update("\n".join(lines))

    # ---------------------------------------------------------- actions
    def action_add(self) -> None:
        self.app.composer_action(self, "add")  # type: ignore[attr-defined]

    def action_remove(self) -> None:
        self.app.composer_action(self, "remove")  # type: ignore[attr-defined]

    def action_reload(self) -> None:
        self.reload()

    def action_local_menu(self) -> None:
        self.app.composer_action(self, "menu")  # type: ignore[attr-defined]


class ComposerLogWindow(_TVWindow):
    """What composer said (read only; white on black, like Output)."""

    DEFAULT_CSS = OUTPUT_CSS.replace("{name}", "ComposerLogWindow")

    def __init__(self, number: int = 0) -> None:
        super().__init__(_('Composer'), number=number)
        self.view = EditorView("", read_only=True, kind=OUTPUT)
        self.lines: list[str] = []

    def compose_content(self) -> ComposeResult:
        yield self.view

    def add(self, line: str) -> None:
        self.lines.append(line)
        del self.lines[:-LOG_LINES]
        self.call_after_refresh(self._show)

    def _show(self) -> None:
        text = "\n".join(self.lines)
        if text != self.view.text:
            self.view.load_text(text)
            last = len(self.lines) - 1
            self.view.move_cursor((max(0, last), len(self.lines[last]) if self.lines else 0))


# ------------------------------------------------------------------ add a package
class ResultList(WheelList, ListBox):
    """Packagist's answer; the bar on a package chooses it."""

    def __init__(self, dialog: "AddPackageDialog") -> None:
        super().__init__([])
        self._dialog = dialog

    def focus_item(self, item: int) -> None:
        super().focus_item(item)
        self._dialog.choose(self.focused)

    def select_item(self, item: int) -> None:
        """Enter (or a double click) on a package adds it, as the Add button would."""
        super().select_item(item)
        self._dialog.end_modal(Command.OK)


class AddPackageDialog(_Dialog):
    """Search Packagist as you type, pick a package, its version (suggested), dev or not."""

    DEFAULT_CSS = """
    AddPackageDialog { width: 90; }
    AddPackageDialog InputLine { width: 1fr; }
    AddPackageDialog .ap-results { height: 1fr; }
    AddPackageDialog .ap-about { height: 2; color: $text; background: $surface; }
    AddPackageDialog .ap-row { height: 1; }
    AddPackageDialog .ap-row Label { width: 14; }
    AddPackageDialog CheckBoxes { width: 1fr; }
    AddPackageDialog .ap-status { height: 1; color: $text-muted; background: $surface; }
    AddPackageDialog .ap-status.-bad { color: $error; }
    """

    def __init__(self, command: list[str], root: Path, query: str = "") -> None:
        super().__init__(title=_('Add a package'))
        self.command = command
        self.project_root = root
        self.query_input = InputLine(max_len=200)
        self.query_input.data = query
        self.results = ResultList(self)
        self.results.add_class("ap-results")
        self.about = Static("", classes="ap-about", markup=False)
        self.version_input = InputLine(max_len=100)
        self.flags = CheckBoxes([_('~D~evelopment only (require-dev)')])
        self.status = Static(_('Type a few letters: Packagist is searched as you type.'), classes="ap-status", markup=False)
        self.found: list[cmp.Found] = []
        self.chosen: str | None = None
        self.constraint = ""
        self.dev = False
        self._timer = None
        self._suggested: str | None = None
        self._query = query

    def compose_content(self) -> ComposeResult:
        yield Label(_('~S~earch Packagist (or type vendor/package)'), link=self.query_input)
        yield self.query_input
        yield Label(_('~P~ackages'), link=self.results)
        yield self.results
        yield self.about
        with Horizontal(classes="ap-row"):
            yield Label(_('~V~ersion'), link=self.version_input)
            yield self.version_input
        yield self.flags
        yield self.status
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('~A~dd'), Command.OK, is_default=True, id="ok")
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.styles.height = max(20, min(30, self.app.size.height - 2))
        if self.query_input.data:
            self.schedule_search()

    def on_input_line_changed(self, message) -> None:
        message.stop()
        if self.query_input.data != self._query:
            self._query = self.query_input.data
            self.schedule_search()
        elif self._suggested is not None and self.version_input.data != self._suggested:
            self._suggested = None  # the user's own version: no more suggestions

    def schedule_search(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        self._timer = self.set_timer(0.6, self.search)

    @work(exclusive=True, group="composer-search")
    async def search(self) -> None:
        self._timer = None
        query = self.query_input.data.strip()
        if len(query) < 2:
            return
        self.status.set_class(False, "-bad")
        self.status.update(_('Searching Packagist for {query}...').format(query=query))
        try:
            found = await cmp.search(self.command, query, self.project_root)
        except (cmp.ComposerError, TimeoutError) as exc:
            self.status.set_class(True, "-bad")
            self.status.update(str(exc) or _('Packagist did not answer'))
            return
        if query != self.query_input.data.strip():
            return
        if cmp.NAME.match(query) and all(f.name != query for f in found):
            found.insert(0, cmp.Found(query, _("(as typed)")))
        self.found = found[:200]
        self.results.set_list([f"{f.name:<40.40} {f.description}" for f in self.found] or [_("  (nothing found)")])
        self.status.update(_('{count} found · ↓ to choose').format(count=len(found)))
        if self.found:
            self.results.focus_item(0)
            self.choose(0)

    def choose(self, index: int) -> None:
        if not 0 <= index < len(self.found):
            return
        found = self.found[index]
        if found.name == self.chosen:
            return
        self.chosen = found.name
        self.about.update(f"{found.name}\n{found.description}")
        self.suggest_version(found.name)

    @work(exclusive=True, group="composer-versions")
    async def suggest_version(self, name: str) -> None:
        if self.version_input.data and self._suggested is None:
            return  # the user typed their own
        self.status.update(_('Asking Packagist for the versions of {name}...').format(name=name))
        try:
            available = await cmp.versions(self.command, name, self.project_root)
        except (cmp.ComposerError, TimeoutError):
            available = []
        if name != self.chosen:
            return
        constraint = cmp.suggest_constraint(available) or ""
        self.version_input.data = constraint
        self.version_input._cursor_pos = len(constraint)
        self.version_input.refresh()
        self._suggested = constraint
        newest = available[0] if available else "?"
        self.status.update(_('Suggested from the newest stable version · newest: {newest}').format(newest=newest))

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        typed = self.query_input.data.strip()
        name = self.chosen or (typed if cmp.NAME.match(typed) else None)
        if name is None:
            self.status.set_class(True, "-bad")
            self.status.update(_('Choose a package (vendor/package)'))
            return False
        self.chosen = name
        self.constraint = self.version_input.data.strip()
        self.dev = bool(self.flags.value & 1)
        return True


# ------------------------------------------------------------------ a new composer.json
class NewComposerDialog(_Dialog):
    """``composer init`` as a dialog: the project's name and kind, PHP, Div, its classes."""

    DEFAULT_CSS = """
    NewComposerDialog { width: 76; height: 19; }
    NewComposerDialog InputLine { width: 1fr; }
    NewComposerDialog .nc-row { height: 1; }
    NewComposerDialog .nc-row Label { width: 24; }
    NewComposerDialog RadioButtons, NewComposerDialog CheckBoxes { width: 1fr; }
    NewComposerDialog .nc-status { height: 2; color: $text-muted; background: $surface; }
    NewComposerDialog .nc-status.-bad { color: $error; }
    """

    def __init__(self, root: Path) -> None:
        super().__init__(title=_('New composer.json'))
        self.project_root = root
        self.inputs: dict[str, InputLine] = {}
        for key, value in (("name", cmp.suggest_name(root)), ("description", ""), ("license", "MIT"),
                           ("php", ">=8.0"), ("div", "^6.1"), ("namespace", ""), ("source", "src/")):
            line = InputLine(max_len=200)
            line.data = value
            self.inputs[key] = line
        self.kind = RadioButtons([_('~P~roject (an application)'), _('~L~ibrary (a package for others)')])
        self.kind.value = 1
        self.flags = CheckBoxes([_('Require ~D~iv (divengine/div)'), _('~I~nstall it now (composer install)')])
        self.flags.value = 3
        self.status = Static(_('divide writes composer.json as composer init would; composer installs it.'),
                             classes="nc-status", markup=False)
        self.result: cmp.NewProject | None = None
        self.install = True

    def compose_content(self) -> ComposeResult:
        rows = (
            ("name", _('~N~ame (vendor/project)')), ("description", _('D~e~scription')),
            ("license", _('Li~c~ense')), ("php", _('P~H~P version')), ("div", _('Div ~v~ersion')),
            ("namespace", _('Cl~a~ss namespace (PSR-4)')), ("source", _('Classes ~f~older')),
        )
        for key, label in rows:
            with Horizontal(classes="nc-row"):
                yield Label(label, link=self.inputs[key])
                yield self.inputs[key]
        yield Label(_('Kind'), link=self.kind)
        yield self.kind
        yield self.flags
        yield self.status
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('C~r~eate'), Command.OK, is_default=True, id="ok")
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        get = {key: line.data.strip() for key, line in self.inputs.items()}
        project = cmp.NewProject(
            name=get["name"], description=get["description"], license=get["license"], php=get["php"],
            type="project" if self.kind.value & 1 else "library",
            require_div=bool(self.flags.value & 1), div_constraint=get["div"],
            namespace=get["namespace"], source=get["source"] or "src/",
        )
        problems = project.problems()
        if problems:
            self.status.set_class(True, "-bad")
            self.status.update("[!] " + "\n[!] ".join(problems))
            return False
        self.result = project
        self.install = bool(self.flags.value & 2)
        return True


# ------------------------------------------------------------------ the app's part
class ComposerMixin:
    """Tools > Composer packages, and composer run under the progress box."""

    def composer_windows(self) -> list[ComposerWindow]:
        return [w for w in self.windows() if isinstance(w, ComposerWindow)]  # type: ignore[attr-defined]

    def composer_log(self) -> ComposerLogWindow | None:
        return next((w for w in self.windows() if isinstance(w, ComposerLogWindow)), None)  # type: ignore[attr-defined]

    def composer_command(self) -> list[str] | None:
        return cmp.find(self.root, config.load().get("composer"))  # type: ignore[attr-defined]

    async def open_composer(self) -> None:
        """Tools > Composer packages: the window (raised if it is open)."""
        view = next(iter(self.composer_windows()), None)
        if view is None:
            view = ComposerWindow(self.root, number=self._free_number())  # type: ignore[attr-defined]
            self._insert(view)  # type: ignore[attr-defined]
        else:
            self.raise_window(view)  # type: ignore[attr-defined]
            view.reload()
        if view.project.json is None and not view.project.problem:
            self.composer_action(view, "new")

    def composer_action(self, win: ComposerWindow, action: str) -> None:
        self._composer_action(win, action)

    @work(group="composer", exclusive=True)
    async def _composer_action(self, win: ComposerWindow, action: str) -> None:
        if action == "menu":
            action = await self._composer_menu(win)
        package = win.package
        command = self.composer_command()
        needs_composer = action in ("add", "remove", "update", "update_all", "install", "outdated", "validate", "dump", "new")
        if needs_composer and command is None and action != "new":
            await self.run_dialog(information(_('Composer'), _(  # type: ignore[attr-defined]
                'Composer was not found. Install it (https://getcomposer.org/download/), put composer.phar '
                'in the project, or choose it: Alt+F10 > Composer program.')))
            return
        match action:
            case "add":
                if win.project.json is None:
                    await self._composer_new(win, command)
                    return
                dialog = AddPackageDialog(command, self.root)  # type: ignore[arg-type,attr-defined]
                if await self.run_dialog(dialog) == Command.OK and dialog.chosen:  # type: ignore[attr-defined]
                    spec = f"{dialog.chosen}:{dialog.constraint}" if dialog.constraint else dialog.chosen
                    await self._composer_run(win, command, ["require", *(["--dev"] if dialog.dev else []), spec],
                                             _('Adding {name}').format(name=dialog.chosen))
            case "remove":
                if package is None or not package.direct or package.platform:
                    self.notify(_('Only a package the project requires can be removed (not a dependency of another one)'), timeout=3)  # type: ignore[attr-defined]
                    return
                text = _('Remove {name} from the project (composer remove)?').format(name=package.name)
                if await self.run_dialog(confirm(_('Composer'), text)) == Command.YES:  # type: ignore[attr-defined]
                    await self._composer_run(win, command, ["remove", *(["--dev"] if package.dev else []), package.name],
                                             _('Removing {name}').format(name=package.name))
            case "update":
                if package is not None and not package.platform:
                    await self._composer_run(win, command, ["update", package.name, "--with-dependencies"],
                                             _('Updating {name}').format(name=package.name))
            case "update_all":
                await self._composer_run(win, command, ["update"], _('Updating every package'))
            case "install":
                await self._composer_run(win, command, ["install"], _('Installing the packages'))
            case "outdated":
                await self._composer_outdated(win, command)
            case "validate":
                await self._composer_run(win, command, ["validate", "--no-check-publish"], _('Validating composer.json'))
            case "dump":
                await self._composer_run(win, command, ["dump-autoload"], _('Writing the autoloader'))
            case "json":
                self.open_file(self.root / "composer.json")  # type: ignore[attr-defined]
            case "new":
                await self._composer_new(win, command)
            case "program":
                await self._composer_program()
            case "folder":
                if package is not None and not package.platform:
                    folder = self.root / "vendor" / package.name  # type: ignore[attr-defined]
                    if folder.is_dir():
                        if self.project_window() is None:  # type: ignore[attr-defined]
                            self.toggle_project()  # type: ignore[attr-defined]
                        tree = self.project_window().project_tree  # type: ignore[attr-defined]
                        await tree.reveal(folder)
                        self.raise_window(self.project_window())  # type: ignore[attr-defined]
                    else:
                        self.notify(_('{name} is not installed (vendor/{name})').format(name=package.name), timeout=3)  # type: ignore[attr-defined]
        if win.is_attached:
            win.packages.focus()
        self.update_status()  # type: ignore[attr-defined]

    async def _composer_menu(self, win: ComposerWindow) -> str:
        from textual_vision.menus import Menu, MenuItem as Item, Separator as Sep
        from divide.ui.explorer import LocalMenu

        items = [
            Item(_('~A~dd a package...'), CM_CP_ADD, _('Ins')),
            Item(_('~R~emove the package'), CM_CP_REMOVE, _('Del')),
            Item(_('~U~pdate the package'), CM_CP_UPDATE),
            Item(_('Its ~f~older'), CM_CP_FOLDER, _('Enter')),
            Sep(),
            Item(_('Update ~e~very package'), CM_CP_UPDATE_ALL),
            Item(_('~I~nstall'), CM_CP_INSTALL),
            Item(_('Look for ~n~ewer versions'), CM_CP_OUTDATED),
            Item(_('~V~alidate composer.json'), CM_CP_VALIDATE),
            Item(_('~D~ump the autoloader'), CM_CP_DUMP),
            Sep(),
            Item(_('Open ~c~omposer.json'), CM_CP_JSON),
            Item(_('Ne~w~ composer.json...'), CM_CP_NEW),
            Item(_('Composer ~p~rogram...'), CM_CP_PROGRAM),
        ]
        region = win.packages.content_region
        at = (region.x + 2, region.y + max(0, win.packages.cursor_line - win.packages.scroll_offset.y))
        chosen = await self.push_screen_wait(LocalMenu(Menu(items=items), at))  # type: ignore[attr-defined]
        return {
            CM_CP_ADD: "add", CM_CP_REMOVE: "remove", CM_CP_UPDATE: "update", CM_CP_UPDATE_ALL: "update_all",
            CM_CP_INSTALL: "install", CM_CP_OUTDATED: "outdated", CM_CP_VALIDATE: "validate", CM_CP_DUMP: "dump",
            CM_CP_JSON: "json", CM_CP_NEW: "new", CM_CP_PROGRAM: "program", CM_CP_FOLDER: "folder",
        }.get(chosen, "")

    def _show_composer_log(self) -> ComposerLogWindow:
        log = self.composer_log()
        if log is None:
            log = ComposerLogWindow(number=self._free_number())  # type: ignore[attr-defined]
            desktop = self.desktop  # type: ignore[attr-defined]
            height = desktop.size.height if desktop is not None and desktop.size.height else 24
            log.styles.offset = (0, max(0, height - 10))
            log.styles.width = "100%"
            log.styles.height = 10
            self.insert_window(log)  # type: ignore[attr-defined]
        return log

    async def _composer_run(self, win: ComposerWindow, command: list[str], args: list[str], title: str) -> cmp.Result | None:
        """``composer args`` under the progress box; its output in the Composer window."""
        log = self._show_composer_log()
        log.add(f"$ composer {' '.join(args)}")
        dialog = ProgressDialog(title, [(_('Project'), str(self.root)), (_('Composer'), "...")], width=72)  # type: ignore[attr-defined]

        def line(text: str) -> None:
            log.add(text)
            if text.strip():
                dialog.set(_('Composer'), text.strip())

        def verdict(result: cmp.Result) -> tuple[str, bool, list[tuple[str, str]]]:
            return (_("Success"), True, []) if result.ok else (_("Failed"), False, [(_('Exit code'), str(result.code))])

        try:
            result = await run_with_progress(self, dialog, cmp.run(command, args, self.root, line), verdict)  # type: ignore[arg-type,attr-defined]
        except cmp.ComposerError as exc:
            await self.run_dialog(information(_('Composer'), str(exc)))  # type: ignore[attr-defined]
            return None
        win.last = None if result is None else (
            _("Last: {command}: done").format(command=args[0]) if result.ok
            else _("Last: {command}: failed (see the Composer window)").format(command=args[0]))
        log.add(_("[stopped]") if result is None else _("[exit code {code}]").format(code=result.code))
        win.reload()
        self.refresh_project()  # type: ignore[attr-defined]
        self.recheck_includes()  # type: ignore[attr-defined]  # Div may have come with it
        if result is not None and not result.ok:
            self.raise_window(log)  # type: ignore[attr-defined]
        return result

    async def _composer_outdated(self, win: ComposerWindow, command: list[str]) -> None:
        dialog = ProgressDialog(_('Looking for newer versions'), [(_('Project'), str(self.root))], width=72)  # type: ignore[attr-defined]

        def verdict(found: dict[str, str]) -> tuple[str, bool, list[tuple[str, str]]]:
            return _("Done"), True, [(_('Newer'), str(len(found)))]

        found = await run_with_progress(self, dialog, cmp.outdated(command, self.root), verdict)  # type: ignore[arg-type,attr-defined]
        if found is not None:
            win.latest = found
            win.last = _("{count} packages have a newer version").format(count=len(found)) if found else _("Every package is up to date")
            win.reload()

    async def _composer_new(self, win: ComposerWindow, command: list[str] | None) -> None:
        file = self.root / "composer.json"  # type: ignore[attr-defined]
        if file.exists():
            await self.run_dialog(information(_('New composer.json'), _('The project has a composer.json already.')))  # type: ignore[attr-defined]
            return
        dialog = NewComposerDialog(self.root)  # type: ignore[attr-defined]
        if await self.run_dialog(dialog) != Command.OK or dialog.result is None:  # type: ignore[attr-defined]
            return
        try:
            file.write_text(dialog.result.text(), encoding="utf-8")
            if dialog.result.namespace:
                (self.root / dialog.result.source).mkdir(parents=True, exist_ok=True)  # type: ignore[attr-defined]
        except OSError as exc:
            await self.run_dialog(information(_('New composer.json'), str(exc)))  # type: ignore[attr-defined]
            return
        win.reload()
        self.refresh_project()  # type: ignore[attr-defined]
        if dialog.install:
            if command is None:
                self.notify(_('composer.json written; composer was not found to install it'), timeout=4)  # type: ignore[attr-defined]
            else:
                await self._composer_run(win, command, ["install"], _('Installing the packages'))

    async def _composer_program(self) -> None:
        from divide.ui.dialogs import FileDialog

        current = self.composer_command()
        start = Path(current[-1]).parent if current else self.root  # type: ignore[attr-defined]
        dialog = FileDialog(_('Composer program (composer or composer.phar)'), start, ok_label=_('~O~K'))
        if await self.run_dialog(dialog) == Command.OK and dialog.chosen:  # type: ignore[attr-defined]
            config.set_value("composer", str(dialog.chosen))
            self.notify(_('Composer: {path}').format(path=dialog.chosen), timeout=3)  # type: ignore[attr-defined]

