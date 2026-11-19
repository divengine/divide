"""Options > Div setup: the project's (or the user's) Div setup, section by section.

The window edits a setup file's buffer (``.div/setup.json`` or
``~/.div/setup.json``), as the dialector edits a dialect file: every change is
one undoable edit of the buffer, F2 saves it, Ctrl+T shows the file as a tree.

- The sections are on the left, with how many settings each file sets.
- On the right, what is in effect for the section: each value and where it
  comes from (the project, the user, or Div's own default).
- Below the sections, what divide would leave out (as you edit) and Div's
  verdict on the saved setup (``setup_check``): the dialect, the include
  paths, the PHP functions it found.
- Enter edits the section in a dialog (paths with a Browse button, lists,
  JSON values checked before they are taken); Del puts it back to Div's
  defaults; Alt+F10: the user's or the project's file, the JSON, the dialect
  in the dialector, trusting the project's PHP settings, asking Div again.
"""

from __future__ import annotations

from divide.i18n import _

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.style import Style
from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.cluster import CheckBoxes
from textual_vision.constants import Command
from textual_vision.input_line import InputLine
from textual_vision.label import Label
from textual_vision.list_box import ListBox

from divide import themes
from divide.lang import divjson
from divide.run import setup as div_setup
from divide.ui.dialogs import _Dialog, browse_into, shown_path
from divide.ui.filter import Filtered, FilteredList
from divide.ui.windows import EditorWindow, HRule, VRule, WheelList, _TVWindow

CM_SETUP_BROWSE = Command.USER + 120  # + the field's row


@dataclass(frozen=True)
class Field:
    key: str  # "engine", "paths.packages"...
    label: str  # with its ~hotkey~
    kind: str  # text, int, file, folder, folders, names, json, checks
    pattern: str = "*"  # files to browse
    options: tuple[str, ...] = ()  # checks


@dataclass(frozen=True)
class Section:
    name: str
    title: str
    about: str
    fields: tuple[Field, ...] = field(default_factory=tuple)


SECTIONS: tuple[Section, ...] = (
    Section("engine", _("Engine and paths"),
            _("Which Div, and where it looks for templates (PACKAGES, DIV_REPO, addIncludePath())."), (
                Field("engine", _("~E~ngine (autoload.php or div.php)"), "file", "*.php"),
                Field("paths.packages", _("~P~ackages: the templates' root (PACKAGES)"), "folder"),
                Field("paths.repository", _("~R~epository (DIV_REPO)"), "folder"),
                Field("paths.include", _("~I~nclude paths (separated by ;)"), "folders"),
            )),
    Section("files", _("File extensions"),
            _("What Div adds to a template's or a data file's name (without the dot)."), (
                Field("files.template_ext", _("~T~emplates (DIV_DEFAULT_TPL_FILE_EXT)"), "text"),
                Field("files.data_ext", _("~D~ata (DIV_DEFAULT_DATA_FILE_EXT)"), "text"),
            )),
    Section("parser", _("Parser"),
            _("How far Div goes, and which PHP errors its formulas report."), (
                Field("parser.max_cycles", _("~M~ax parse cycles (DIV_MAX_PARSE_CYCLES)"), "int"),
                Field("parser.max_filename", _("Max ~f~ile name size (DIV_MAX_FILENAME_SIZE)"), "int"),
                Field("parser.error_reporting", _("~E~rror reporting (E_ALL, E_NOTICE...)"), "text"),
            )),
    Section("dialect", _("Dialect"),
            _("The project's dialect: templates without @_DIALECT are in it, and a dialect file's missing tags are its."), (
                Field("dialect", _("~D~ialect file"), "file", "*.dialect"),
            )),
    Section("data", _("Data"),
            _("What every template gets besides its data: globals (setGlobal()), defaults, system variables."), (
                Field("data.globals", _("~G~lobals (a JSON object)"), "json"),
                Field("data.defaults", _("~D~efaults: [{\"search\": ..., \"replace\": ...}]"), "json"),
                Field("data.defaults_by_var", _("Defaults by ~v~ariable: [{\"var\": ..., \"search\": ..., \"replace\": ...}]"), "json"),
                Field("data.system_vars", _("~S~ystem variables (div.now, div.get... are always on)"), "checks",
                      options=("ascii", "server", "session", "script_name")),
            )),
    Section("php", _("PHP functions"),
            _("PHP that templates may call: functions in formulas and conditions, custom modifiers. A project's only once you trust it."), (
                Field("php.allowed_functions", _("~A~llowed functions (separated by ,)"), "names"),
                Field("php.modifiers", _("~M~odifiers: {\"prefix:\": \"php_function\"}"), "json"),
            )),
    Section("request", _("Simulated request"),
            _("The request templates see while you design them: div.get, div.post, div.server, div.session."), (
                Field("request.get", _("~G~ET (a JSON object)"), "json"),
                Field("request.post", _("~P~OST"), "json"),
                Field("request.server", _("~S~ERVER (added to PHP's)"), "json"),
                Field("request.session", _("S~E~SSION"), "json"),
                Field("request.cookie", _("~C~OOKIE"), "json"),
            )),
    Section("code", _("Custom PHP code"),
            _("Hooks (beforeBuild, afterParse...), subclasses of div, closures and sub-parsers are PHP code: "
              "divide does not run the application's code, so they cannot be set here."), ()),
)

# what Div does when nothing is set
DIV_DEFAULTS = {
    "paths.packages": "./", "paths.repository": "./", "files.template_ext": "tpl", "files.data_ext": "json",
    "parser.max_cycles": "100", "parser.max_filename": "250", "parser.error_reporting": "E_ALL",
}


def _get(data: dict, key: str) -> Any:
    node: Any = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _has(data: dict, key: str) -> bool:
    node: Any = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def set_value(data: dict, key: str, value: Any, *, remove: bool = False) -> None:
    """Set (or remove) ``key`` in a setup's data; empty sections go away."""
    parts = key.split(".")
    node = data
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            if remove:
                return
            node[part] = {}
        node = node[part]
    if remove:
        node.pop(parts[-1], None)
        if len(parts) > 1 and not node:
            data.pop(parts[0], None)
    else:
        node[parts[-1]] = value


def value_text(f: Field, value: Any) -> str:
    """A setting as its field shows it."""
    if value is None:
        return ""
    if f.kind == "folders":
        return "; ".join(value) if isinstance(value, list) else str(value)
    if f.kind == "names":
        return ", ".join(value) if isinstance(value, list) else str(value)
    if f.kind == "json":
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def parse_field(f: Field, text: str) -> tuple[Any, str | None]:
    """A field's text as the setting's value; ``(None, None)``: not set; ``(_, why)``: wrong."""
    text = text.strip()
    if not text:
        return None, None
    if f.kind == "int":
        try:
            return int(text), None
        except ValueError:
            return None, _('a whole number is expected')
    if f.kind == "folders":
        return [p.strip() for p in text.split(";") if p.strip()], None
    if f.kind == "names":
        return [n.strip() for n in text.split(",") if n.strip()], None
    if f.kind == "json":
        try:
            return divjson.loads(text), None
        except divjson.DivJsonError as exc:
            return None, str(exc)
    return text, None


def rewrite_loses(text: str) -> bool:
    """Would writing the setup back as plain JSON lose something (comments, quotes...)?"""
    if not text.strip():
        return False
    try:
        json.loads(text)
        return False
    except ValueError:
        return True


# ------------------------------------------------------------------ the window
class SetupSectionList(WheelList, FilteredList, ListBox):
    """The sections, in the editor's colours (as the dialector's)."""

    DEFAULT_CSS = "SetupSectionList { width: 1fr; height: 1fr; }"
    can_focus = True

    def get_component_rich_style(self, *names: str, partial: bool = False) -> Style:
        from divide.ui.dialector import _editor_styles

        normal, focused = _editor_styles(self._window.source.editor)
        if names == ("list-viewer--normal",):
            return normal
        if names == ("list-viewer--focused",):
            return normal + focused
        return super().get_component_rich_style(*names, partial=partial)

    def __init__(self, window: "DivSetupWindow") -> None:
        super().__init__([])
        self._window = window
        self._syncing = False

    def focus_item(self, item: int) -> None:
        super().focus_item(item)
        if not self._syncing:
            self._window.section_focused(self.current)

    def select_item(self, item: int) -> None:
        super().select_item(item)
        self._window.edit_section(self.original(item))

    def on_click(self, event: events.Click) -> None:
        if event.chain >= 2:
            self.select_item(self.focused)


class DivSetupWindow(_TVWindow):
    """Sections | what is in effect, with what is left out and Div's verdict below."""

    HINT = _('Enter edit section · Del Div\'s defaults · F2 save · Alt+F10 menu: user/project, JSON, trust')
    BINDINGS = [
        Binding("delete", "restore_section", show=False),
        Binding("ctrl+z", "undo", show=False),
        Binding("ctrl+y", "redo", show=False),
        Binding("alt+f10,shift+f10", "local_menu", show=False),
    ]
    DEFAULT_CSS = """
    DivSetupWindow .ds-left { width: 36; height: 1fr; }
    DivSetupWindow .ds-about { height: 5; padding: 0 1; }
    DivSetupWindow .ds-verdict { height: 7; padding: 0 1; }
    DivSetupWindow .ds-right { height: 1fr; width: 1fr; }
    DivSetupWindow .ds-effect { padding: 0 1; }
    """

    def __init__(self, source: EditorWindow, root: Path, *, user: bool, number: int = 0) -> None:
        self.source = source
        self.project_root = root
        self.user = user
        super().__init__(self._make_title(), number=number)
        self.section_index = 0
        self.sections = SetupSectionList(self)
        self.about = Static("", classes="ds-about", markup=False)
        self.verdict_box = Static(_('Asking Div...'), classes="ds-verdict", markup=False)
        self.effect = Static("", classes="ds-effect", markup=False)
        self.data: dict = {}
        self.error: str | None = None
        self.problems: list[div_setup.Problem] = []
        self.check = None  # Div's SetupCheck of the saved files
        self._written: str | None = None
        self._rewrite_ok = False

    def _make_title(self) -> str:
        which = _("user's") if self.user else _("project's")
        name = shown_path(self.source.path) if self.user and self.source.path else self.source.display_name
        return _("Div setup ({which}): {name}").format(which=which, name=name)

    def compose_content(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes="ds-left"):
                yield Filtered(self.sections)
                yield HRule()
                yield self.about
                yield HRule()
                yield self.verdict_box
            yield VRule()
            with VerticalScroll(classes="ds-right"):
                yield self.effect

    def on_mount(self) -> None:
        self.call_after_refresh(self.paint)
        self.call_after_refresh(self.reload)
        self.call_after_refresh(self.sections.focus)
        self.call_after_refresh(self.check_now)
        self.app.theme_changed_signal.subscribe(self, lambda _theme: self.call_after_refresh(self.paint))

    def paint(self) -> None:
        """The panels take the editor's colours, as the dialector's."""
        if self.closing:  # (Div's check ending as the window closes)
            return
        from divide.ui.dialector import _editor_styles

        normal, focused = _editor_styles(self.source.editor)
        bg = Color.from_rich_color(normal.bgcolor) if normal.bgcolor else None
        fg = Color.from_rich_color(normal.color) if normal.color else None
        for box in (self.about, self.verdict_box, self.effect, self.query_one(".ds-left"), self.query_one(".ds-right")):
            box.styles.background = bg
            box.styles.color = fg
        if self.verdict_box.has_class("-bad"):
            self.verdict_box.styles.color = Color.parse(themes.current().colour("verdict-error"))
        self.sections.refresh()

    # ------------------------------------------------------------- sync
    def reload(self) -> None:
        """Read the setup from the source buffer (skipping this window's own writes)."""
        text = self.source.editor.text
        if text == self._written and self.error is None:
            return
        self.problems = div_setup.check_text(self.source.path or Path(div_setup.FILE), text)
        try:
            value = divjson.loads(text) if text.strip() else {}
        except divjson.DivJsonError as exc:
            self.error = str(exc)
            self.refresh_view()
            return
        if not isinstance(value, dict):
            self.error = _('the setup must be a JSON object')
            self.refresh_view()
            return
        self.error = None
        self.data = value
        self.refresh_view()

    def write(self, data: dict) -> None:
        """The setup into the source buffer (one undoable edit)."""
        self.data = data
        text = json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n" if data else "{}\n"
        editor = self.source.editor
        self._written = text
        editor.replace(text, (0, 0), editor.document.end, maintain_selection_offset=False)
        self.problems = div_setup.check_text(self.source.path or Path(div_setup.FILE), text)
        self.refresh_view()

    async def can_rewrite(self) -> bool:
        if self.error is not None:
            from divide.ui.dialogs import information
            await self.app.run_dialog(information(_('Div setup'), _('Fix the setup file first:\n{error}').format(error=self.error)))  # type: ignore[attr-defined]
            return False
        if not self._rewrite_ok and rewrite_loses(self.source.editor.text):
            from divide.ui.dialogs import confirm
            text = _("Div setup rewrites {name} as standard JSON: its comments are dropped. Continue?").format(
                name=self.source.display_name)
            if await self.app.run_dialog(confirm(_('Div setup'), text)) != Command.YES:  # type: ignore[attr-defined]
                return False
        self._rewrite_ok = True
        return True

    # ------------------------------------------------------------ view
    @property
    def section(self) -> Section:
        return SECTIONS[self.section_index]

    def _section_rows(self) -> list[str]:
        bad = {p.text.split(":")[0] for p in self.problems}
        rows = []
        for section in SECTIONS:
            n = sum(_has(self.data, f.key) for f in section.fields)
            wrong = any(f.key in bad or f.key.split(".")[0] in bad for f in section.fields)
            mark = "!" if wrong else ("•" if n else " ")
            count = f"{n}/{len(section.fields)}" if n else (f"  {len(section.fields)}" if section.fields else "")
            rows.append(f"{mark} {section.title:<26.26}{count:>6}")
        return rows

    def refresh_view(self) -> None:
        keep = self.section_index
        self.sections._syncing = True
        self.sections.set_list(self._section_rows())
        self.sections.focus_original(keep)
        self.sections._syncing = False
        self.section_focused(keep)
        self.show_verdict()

    def section_focused(self, index: int) -> None:
        if not 0 <= index < len(SECTIONS):
            return
        self.section_index = index
        section = self.section
        n = sum(_has(self.data, f.key) for f in section.fields)
        about = section.about
        if section.fields:
            about += "\n" + _('{n} of {count} set in this file · Enter to edit').format(n=n, count=len(section.fields))
        self.about.update(about)
        self.effect.update(self.effect_text(section))

    def effect_text(self, section: Section) -> str:
        """What is in effect for ``section``: each setting, its value, where it comes from."""
        lines = [section.title, "─" * len(section.title)]
        if not section.fields:
            return "\n".join(lines + ["", section.about])
        layers = self.setup_layers()
        project = next((layer for layer in layers if not self._is_user(layer.file)), None)
        user = next((layer for layer in layers if self._is_user(layer.file)), None)
        for f in section.fields:
            origin = []
            for layer, name in ((project, _("project")), (user, _("user"))):
                if layer is not None and self._sets(layer, f.key):
                    origin.append(name)
                    if f.kind not in ("folders", "names", "json", "checks"):
                        break  # the stronger one only
            value = self._effective(layers, f)
            source = " + ".join(origin) if origin else _("Div")
            if not origin:
                value = self._default_text(f)
            lines.append("")
            lines.append(f"{f.label.replace('~', '')}")
            lines.append(f"  {value or '-'}")
            lines.append(f"  ({source})")
        if self.error:
            lines += ["", _("[!] The file is not valid JSON: {error}").format(error=self.error)]
        return "\n".join(lines)

    def _shown(self, path: Path | str) -> str:
        """A path as the project knows it: relative inside it, ~ for the home folder."""
        path = Path(path)
        try:
            return path.relative_to(self.project_root.resolve()).as_posix() + ("/" if path.is_dir() else "") or "./"
        except ValueError:
            return shown_path(path)

    def _sets(self, layer: div_setup.Layer, key: str) -> bool:
        return _has(layer.data, key) or (key.split(".")[0] in layer.data and layer.data[key.split(".")[0]] is None)

    def _effective(self, layers: list[div_setup.Layer], f: Field) -> str:
        if not layers:
            return ""
        merged = div_setup.merge(layers)
        key = f.key
        constants = {"paths.packages": "PACKAGES", "paths.repository": "DIV_REPO",
                     "files.template_ext": "DIV_DEFAULT_TPL_FILE_EXT", "files.data_ext": "DIV_DEFAULT_DATA_FILE_EXT",
                     "parser.max_cycles": "DIV_MAX_PARSE_CYCLES", "parser.max_filename": "DIV_MAX_FILENAME_SIZE"}
        if key in constants:
            value = merged.constants.get(constants[key])
            return self._shown(str(value)) if f.kind == "folder" and value else ("" if value is None else str(value))
        if key == "engine":
            return self._shown(merged.engine) if merged.engine else ""
        if key == "paths.include":
            return "; ".join(self._shown(p) for p in merged.include_paths)
        if key == "parser.error_reporting":
            return "" if merged.error_reporting is None else str(merged.error_reporting)
        if key == "dialect":
            if not merged.dialect_tags:
                return ""
            where = self._shown(merged.dialect_source) if merged.dialect_source else _("written in the setup")
            return _("{where}: {count} tags").format(where=where, count=len(merged.dialect_tags))
        values = {
            "data.globals": merged.globals, "data.defaults": [list(d) for d in merged.defaults],
            "data.defaults_by_var": [list(d) for d in merged.defaults_by_var], "data.system_vars": list(merged.system_vars),
            "php.allowed_functions": list(merged.allowed_functions), "php.modifiers": merged.modifiers,
            **{f"request.{name}": merged.request.get(name, {}) for name in div_setup.SUPERGLOBALS},
        }
        value = values.get(key)
        if not value:
            if key.startswith("php.") and merged.untrusted is not None:
                return _("(the project's, not trusted yet: Alt+F10)")
            return ""
        return value_text(f, value) if f.kind != "checks" else ", ".join(value)

    def _default_text(self, f: Field) -> str:
        if f.key == "engine":
            found = self.app.find_div_engine([self.project_root])  # type: ignore[attr-defined]
            return _("found by itself: {path}").format(path=self._shown(found)) if found else _("not found")
        if f.key == "dialect":
            return _("Div's default dialect")
        return DIV_DEFAULTS.get(f.key, _("none"))

    def _is_user(self, file: Path) -> bool:
        return file.parent.resolve() == div_setup.user_dir().resolve()

    def setup_layers(self) -> list[div_setup.Layer]:
        """The project's and the user's setups, this window's from its buffer (unsaved too)."""
        mine = div_setup.Layer(self.source.path or Path(div_setup.FILE), self.source.editor.text)
        other_file = div_setup.project_file(self.project_root) if self.user else div_setup.user_file()
        other = div_setup.Layer(other_file) if other_file.is_file() else None
        layers = [mine, other] if not self.user else [other, mine]
        return [layer for layer in layers if layer is not None]

    # ----------------------------------------------------------- verdict
    def show_verdict(self) -> None:
        lines: list[str] = []
        bad = False
        if self.error:
            lines.append(_("[!] Not valid JSON: {error}").format(error=self.error))
            bad = True
        elif self.problems:
            bad = True
            lines.append(_("[!] divide leaves out {count}:").format(count=len(self.problems)))
            lines += [f"  {p.text}" for p in self.problems[:3]]
        check = self.check
        if check is None:
            lines.append(_("Div: not asked yet (Alt+F10 > Check with Div)"))
        elif isinstance(check, str):
            lines.append(_("Div: {problem}").format(problem=check))
        else:
            lines.append(_("Div {version}: dialect {dialect}").format(
                version=check.version or "?", dialect=_("valid") if check.dialect is None else f"[!] {check.dialect}"))
            missing = [n for n, ok in {**check.functions, **check.modifiers}.items() if not ok]
            if missing:
                bad = True
                lines.append(_("[!] PHP lacks: {names}").format(names=", ".join(missing)))
            lines.append(_("{count} include paths").format(count=len(check.include_paths)))
        if self.source.dirty:
            lines.append(_("Unsaved: F2 saves (Div sees the saved file)"))
        setup = self.app.div_setup()  # type: ignore[attr-defined]
        if setup.untrusted is not None and not self.user:
            lines.append(_("The project's PHP settings wait for your trust (Alt+F10)"))
        self.verdict_box.set_class(bad, "-bad")
        self.verdict_box.update("\n".join(lines))
        self.paint()

    @work(exclusive=True, group="div-setup-check")
    async def check_now(self) -> None:
        self.check = await self.app.check_div_setup()  # type: ignore[attr-defined]
        self.show_verdict()

    # ---------------------------------------------------------- actions
    def edit_section(self, index: int) -> None:
        self.section_index = index
        self.app.div_setup_action(self, "edit")  # type: ignore[attr-defined]

    def action_restore_section(self) -> None:
        self.app.div_setup_action(self, "restore")  # type: ignore[attr-defined]

    def action_undo(self) -> None:
        self.source.editor.action_undo()

    def action_redo(self) -> None:
        self.source.editor.action_redo()

    def action_local_menu(self) -> None:
        self.app.div_setup_action(self, "menu")  # type: ignore[attr-defined]


# ------------------------------------------------------------------ a section's dialog
class SetupSectionDialog(_Dialog):
    """The settings of one section, as the setup file has them."""

    DEFAULT_CSS = """
    SetupSectionDialog { width: 84; }
    SetupSectionDialog .ss-row { height: 1; }
    SetupSectionDialog .ss-row InputLine { width: 1fr; }
    SetupSectionDialog .ss-row Button { margin-left: 1; min-width: 5; }
    SetupSectionDialog CheckBoxes { width: 1fr; }
    SetupSectionDialog .ss-note { color: $text-muted; background: $surface; height: auto; }
    SetupSectionDialog .ss-status { height: auto; color: $text; background: $surface; }
    SetupSectionDialog .ss-status.-bad { color: $error; }
    """

    def __init__(self, section: Section, data: dict, file: Path, base: Path, suggestions: dict[str, str]) -> None:
        super().__init__(title=section.title)
        self.section = section
        self.data = data
        self.file = file
        self.base = base
        self.inputs: dict[str, InputLine | CheckBoxes] = {}
        for f in section.fields:
            value = _get(data, f.key)
            if f.kind == "checks":
                boxes = CheckBoxes([f"div.{o}" for o in f.options])
                chosen = value if isinstance(value, list) else []
                boxes.value = sum(1 << i for i, o in enumerate(f.options) if o in chosen or f"div.{o}" in chosen)
                self.inputs[f.key] = boxes
            else:
                line = InputLine(max_len=4096)
                line.data = value_text(f, value)
                self.inputs[f.key] = line
        self.suggestions = suggestions
        self.note = Static(section.about + "\n" + _("An empty field: Div's default (or the user's setup)."),
                           classes="ss-note", markup=False)
        self.status = Static("", classes="ss-status", markup=False)
        self.values: dict[str, Any] = {}  # key -> value; None: removed

    def compose_content(self) -> ComposeResult:
        yield self.note
        for row, f in enumerate(self.section.fields):
            widget = self.inputs[f.key]
            yield Label(f.label, link=widget)
            if f.kind in ("file", "folder", "folders"):
                with Horizontal(classes="ss-row"):
                    yield widget
                    yield Button("...", CM_SETUP_BROWSE + row, id=f"browse-{row}")
            elif f.kind == "checks":
                yield widget
            else:
                with Horizontal(classes="ss-row"):
                    yield widget
            if f.key in self.suggestions and not self.inputs[f.key].data:  # type: ignore[union-attr]
                yield Static(_("Suggested: {value}").format(value=self.suggestions[f.key]), classes="ss-note", markup=False)
        yield self.status
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('O~K~'), Command.OK, is_default=True, id="ok")
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        # frame, margins, the note, each field (its label and its line or boxes), suggestions, status, buttons
        note = 1 + len(self.section.about) // 76 + 1
        rows = sum(1 + (len(f.options) if f.kind == "checks" else 1) for f in self.section.fields)
        self.styles.height = min(self.app.size.height - 2, 2 + 2 + note + rows + len(self.suggestions) + 1 + 3)

    def on_command_message(self, message) -> None:
        command = message.command
        if CM_SETUP_BROWSE <= command < CM_SETUP_BROWSE + len(self.section.fields):
            message.stop()
            message.prevent_default()
            self.run_worker(self._browse(self.section.fields[command - CM_SETUP_BROWSE]), exclusive=True)

    async def _browse(self, f: Field) -> None:
        line = self.inputs[f.key]
        assert isinstance(line, InputLine)
        if f.kind == "folders":  # one more folder at the end
            probe = InputLine(max_len=4096)
            if await browse_into(self, probe, f.label.replace("~", ""), "*", self.base, folders=True):
                line.data = "; ".join(p for p in [line.data.strip().rstrip(";"), probe.data] if p)
                line._cursor_pos = len(line.data)
                line.refresh()
        elif await browse_into(self, line, f.label.replace("~", ""), f.pattern, self.base, folders=f.kind == "folder"):
            line.tv_select_self()
        line.focus()

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        values: dict[str, Any] = {}
        problems: list[str] = []
        for f in self.section.fields:
            widget = self.inputs[f.key]
            if isinstance(widget, CheckBoxes):
                chosen = [o for i, o in enumerate(f.options) if widget.value & (1 << i)]
                values[f.key] = chosen or None
                continue
            value, why = parse_field(f, widget.data)
            if why is not None:
                problems.append(f"{f.label.replace('~', '')}: {why}")
            values[f.key] = value
        if not problems:
            # what divide would leave out of the file with these values
            trial = json.loads(json.dumps(self.data, default=str))
            for key, value in values.items():
                set_value(trial, key, value, remove=value is None)
            keys = {f.key for f in self.section.fields} | {self.section.name}
            for problem in div_setup.check_text(self.file, json.dumps(trial, default=str)):
                if any(problem.text.startswith(k) or f'"{k}"' in problem.text for k in keys):
                    problems.append(problem.text)
        if problems:
            self.status.set_class(True, "-bad")
            self.status.update("[!] " + "\n[!] ".join(problems[:4]))
            return False
        self.values = values
        return True
