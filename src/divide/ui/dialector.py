"""The dialector: a Turbo Vision assistant to build Div dialects.

A port of divengine/dialector to the terminal. The dialector is a view of a
``.dialect`` editor window, as the data tree is of a JSON one: the file is the
source of truth, so F2, undo and the unsaved-changes checks work as usual.

- The window lists the sections of the language (how many tags each one
  changes) next to a preview: the dialector's example written with the
  dialect, highlighted by divide's own lexer in that dialect, with the tags of
  the chosen section marked.
- Enter opens the section's dialog: one field per tag, Div's default beside
  it, and a live preview of the section's example.
- Div judges the dialect: ``isValidCurrentDialect()`` and a round trip through
  ``translateFrom()`` (see ``divide.run.render.check_dialect``).
"""

from __future__ import annotations

import json
from pathlib import Path

from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from rich.style import Style
from textual.color import Color
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.constants import Command
from textual_vision.input_line import InputLine
from textual_vision.label import Label
from textual_vision.list_box import ListBox

from divide.editor.theme import CGA
from divide.lang.div import dialector as dx
from divide.lang.div.dialect import DEFAULT_TAGS, Dialect
from divide.ui.dialogs import _Dialog, browse_into
from divide.ui.windows import EditorView, EditorWindow, HRule, VRule, _TVWindow

CM_DEFAULTS = Command.USER + 60


def _preview_view(height: str = "1fr") -> EditorView:
    view = EditorView("", read_only=True)
    view.show_line_numbers = False
    view.styles.height = height
    return view


def _show(view: EditorView, filled: dx.Filled, tags: dict[str, str], marks: list[tuple[int, int, str]]) -> None:
    view.forced_dialect = Dialect.from_overrides(dx.overrides(tags), name="dialector")
    view.marks = marks
    if view.text != filled.text:
        view.load_text(filled.text)
    else:
        view.set_marks(marks)
        view._build_highlight_map()
        view.refresh()


def _verdict_text(verdict, tags: dict[str, str], section: dx.Section | None = None) -> tuple[str, bool]:
    """Div's verdict in words, and whether it is bad news (``verdict`` None: no Div).

    For a ``section``, only what concerns it; otherwise the whole example."""
    if verdict is None:
        return "Div was not found: Div judges the dialect (Options > Div engine).", True
    if verdict.reason:
        return f"[!] Div: {verdict.reason}", True
    if verdict.translated is None:
        return "Div: valid ✓", False
    diffs = dx.differences(tags, verdict.translated)
    if section is not None:
        mine = next((d for d in diffs if d.section == section.title), None)
        if mine is None:
            return "Div: valid ✓ · reads this section back exactly", False
        return f"Div reads line {mine.line} otherwise: {mine.read.strip()}", True
    total = len(dx.SECTIONS)
    if not diffs:
        return f"Div: valid ✓\nIt reads all {total} sections of the example back exactly.", False
    d = diffs[0]
    more = f" (+{len(diffs) - 1} more)" if len(diffs) > 1 else ""
    return (
        f"Div: valid ✓ · reads {total - len(diffs)}/{total} sections back\n"
        f"≠ {d.section}{more}, line {d.line}:\n"
        f"wrote {d.wrote.strip()}\nread  {d.read.strip()}"
    ), True


# ------------------------------------------------------------------ window
def _editor_styles(view: EditorView) -> tuple[Style, Style]:
    """The editor's colours (text, and the dialector's mark) for the panels beside it."""
    theme = getattr(view, "_theme", None)
    if theme is None or theme.base_style is None:
        return Style(), Style(reverse=True)
    return theme.base_style, theme.syntax_styles.get("dialector.focus", Style(reverse=True))


class SectionList(ListBox):
    """The sections, in the editor's colours; the focused one as its tags in the preview."""

    DEFAULT_CSS = "SectionList { width: 1fr; height: 1fr; }"
    can_focus = True

    def __init__(self, window: "DialectorWindow") -> None:
        super().__init__([])
        self._window = window
        self._syncing = False

    def focus_item(self, item: int) -> None:
        super().focus_item(item)
        if not self._syncing:
            self._window.section_focused(self.focused)

    def select_item(self, item: int) -> None:
        super().select_item(item)
        self._window.edit_section(item)

    def on_click(self, event: events.Click) -> None:
        if event.chain >= 2:
            self.select_item(self.focused)

    def get_component_rich_style(self, *names: str, partial: bool = False) -> Style:
        normal, focused = _editor_styles(self._window.preview)
        if names == ("list-viewer--normal",):
            return normal
        if names == ("list-viewer--focused",):
            return normal + focused
        return super().get_component_rich_style(*names, partial=partial)


class DialectorWindow(_TVWindow):
    """Sections | preview, with Div's verdict below the sections."""

    HINT = "Enter edit section · Del defaults · Alt+F10 menu: transform, PHP, example"
    BINDINGS = [
        Binding("delete", "restore_section", show=False),
        Binding("ctrl+z", "undo", show=False),
        Binding("ctrl+y", "redo", show=False),
        Binding("alt+f10,shift+f10", "local_menu", show=False),
    ]
    DEFAULT_CSS = """
    DialectorWindow .dx-left { width: 39; height: 1fr; }
    DialectorWindow .dx-about { height: 3; padding: 0 1; }
    DialectorWindow .dx-verdict { height: 5; padding: 0 1; }
    """

    def __init__(self, source: EditorWindow, number: int = 0) -> None:
        self.source = source
        super().__init__(self._make_title(), number=number)
        self.tags: dict[str, str] = dict(DEFAULT_TAGS)
        self.error: str | None = None
        self.verdict = None
        self.section_index = 0
        self.sections = SectionList(self)
        self.about = Static("", classes="dx-about", markup=False)
        self.verdict_box = Static("Asking Div...", classes="dx-verdict", markup=False)
        self.preview = _preview_view()
        self._written: str | None = None
        self._rewrite_ok = False
        self._check_timer = None

    def _make_title(self, invalid: bool = False) -> str:
        return f"Dialector: {self.source.display_name}" + (" [invalid JSON]" if invalid else "")

    def compose_content(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes="dx-left"):
                yield self.sections
                yield HRule()
                yield self.about
                yield HRule()
                yield self.verdict_box
            yield VRule()
            yield self.preview

    def on_mount(self) -> None:
        self.call_after_refresh(self.paint)
        self.call_after_refresh(self.reload)
        self.call_after_refresh(self.sections.focus)

    def paint(self) -> None:
        """The panels take the editor's colours (Options > Editor theme included)."""
        normal, _ = _editor_styles(self.preview)
        bg = Color.from_rich_color(normal.bgcolor) if normal.bgcolor else None
        fg = Color.from_rich_color(normal.color) if normal.color else None
        for box in (self.about, self.verdict_box, self.query_one(".dx-left")):
            box.styles.background = bg
            box.styles.color = fg
        if self.verdict_box.has_class("-bad"):
            self.verdict_box.styles.color = Color.parse(CGA["lightred"])
        self.sections.refresh()

    # ------------------------------------------------------------- sync
    def reload(self) -> None:
        """Read the tags from the source buffer (skipping this window's own writes)."""
        text = self.source.editor.text
        if text == self._written and self.error is None:
            return
        self._decode(text)

    @work(exclusive=True, group="dialector-decode")
    async def _decode(self, text: str) -> None:
        """Div decodes the buffer with its ``jsonDecode()``, as when it loads the file."""
        if text.strip():
            value, problem = await self.app.decode_dialect_text(text)  # type: ignore[attr-defined]
        else:
            value, problem = {}, None
        if self.source.editor.text != text:
            return  # changed meanwhile: a newer reload follows
        if value is None:
            self.error = problem or "Div cannot decode it as a JSON object"
            self.title = self._make_title(invalid=True)
            self._set_verdict(f"[!] {self.error}\nFix it in the code (Ctrl+T on the file shows it as a tree).", True)
            return
        self.error = None
        self.title = self._make_title()
        self.tags = {**DEFAULT_TAGS, **{k: v for k, v in value.items() if k in DEFAULT_TAGS}}
        self.refresh_view()
        self.schedule_check()

    def _set_verdict(self, text: str, bad: bool) -> None:
        self.verdict_box.set_class(bad, "-bad")
        self.verdict_box.update(text)
        self.paint()

    def apply(self, changes: dict[str, str]) -> None:
        """Change tags, write the dialect file's buffer (one undoable edit) and refresh."""
        tags = {**self.tags, **changes}
        if tags == self.tags:
            return
        self.tags = tags
        editor = self.source.editor
        text = dx.dialect_json(tags)
        self._written = text
        editor.replace(text, (0, 0), editor.document.end, maintain_selection_offset=False)
        self.refresh_view()
        self.schedule_check()

    async def can_rewrite(self) -> bool:
        if self.error is not None:
            await self.app.run_dialog(_message("Dialector", f"Fix the dialect file first:\n{self.error}"))  # type: ignore[attr-defined]
            return False
        if not self._rewrite_ok and _rewrite_loses(self.source.editor.text):
            from divide.ui.dialogs import confirm

            text = (
                f"The dialector rewrites {self.source.display_name} as standard JSON with only "
                "the tags that differ from Div's: comments and other tags are dropped. Continue?"
            )
            if await self.app.run_dialog(confirm("Dialector", text)) != Command.YES:  # type: ignore[attr-defined]
                return False
        self._rewrite_ok = True
        return True

    # ------------------------------------------------------------ view
    @property
    def section(self) -> dx.Section:
        return dx.SECTIONS[self.section_index]

    def _section_rows(self) -> list[str]:
        bad = self._bad_key()
        misread = self._misread()
        rows = []
        for section in dx.SECTIONS:
            n = dx.changed_in(section, self.tags)
            mark = "!" if bad in section.keys else "≠" if section.title in misread else ("•" if n else " ")
            count = f"{n}/{len(section.keys)}" if n else f"  {len(section.keys)}"
            rows.append(f"{mark} {section.title:<31.31}{count:>6}")
        return rows

    def _misread(self) -> set[str]:
        translated = getattr(self.verdict, "translated", None)
        return {d.section for d in dx.differences(self.tags, translated)} if translated is not None else set()

    def _bad_key(self) -> str | None:
        reason = getattr(self.verdict, "reason", None) or ""
        return next((k for k in dx.ALL_KEYS if reason.startswith(k)), None)

    def refresh_view(self) -> None:
        keep = self.section_index
        self.sections._syncing = True
        self.sections.set_list(self._section_rows())
        self.sections.focus_item(keep)
        self.sections._syncing = False
        self.section_focused(keep)

    def section_focused(self, index: int) -> None:
        if not 0 <= index < len(dx.SECTIONS):
            return
        self.section_index = index
        section = self.section
        changed = dx.changed_in(section, self.tags)
        self.about.update(f"{section.about}\n{changed} of {len(section.keys)} tags changed · Enter to edit")
        filled = dx.example(dx.overrides(self.tags))
        marks = [(a, b, "dialector.focus") for key in section.keys for a, b in filled.spans.get(key, [])]
        _show(self.preview, filled, self.tags, marks)
        start, _ = filled.sections[section.title]
        row = filled.text.count("\n", 0, start)
        self.call_after_refresh(lambda: self.preview.scroll_to(y=row, animate=False))

    # ----------------------------------------------------------- Div's verdict
    def schedule_check(self) -> None:
        if self._check_timer is not None:
            self._check_timer.stop()
        self._check_timer = self.set_timer(0.4, self.check_now)

    @work(exclusive=True, group="dialector-check")
    async def check_now(self) -> None:
        self._check_timer = None
        verdict = await self.app.dialector_verdict(self.tags)  # type: ignore[attr-defined]
        if self.error is not None:
            return
        self.verdict = verdict
        self._set_verdict(*_verdict_text(verdict, self.tags))
        self.sections._syncing = True
        self.sections.set_list(self._section_rows())
        self.sections.focus_item(self.section_index)
        self.sections._syncing = False
        self.app.update_status()  # type: ignore[attr-defined]

    # ---------------------------------------------------------- actions
    def edit_section(self, index: int) -> None:
        self.section_index = index
        self.app.dialector_action(self, "edit")  # type: ignore[attr-defined]

    def action_restore_section(self) -> None:
        self.app.dialector_action(self, "restore_section")  # type: ignore[attr-defined]

    def action_undo(self) -> None:
        self.source.editor.action_undo()  # the buffer changes; the app reloads this window

    def action_redo(self) -> None:
        self.source.editor.action_redo()

    def action_local_menu(self) -> None:
        self.app.dialector_action(self, "menu")  # type: ignore[attr-defined]


def _rewrite_loses(text: str) -> bool:
    """Would rewriting the file as standard JSON lose something (comments, single
    quotes, keys that are not Div tags...)? Plain JSON of tags loses nothing."""
    if not text.strip():
        return False
    try:
        value = json.loads(text)
    except ValueError:
        return True
    return not isinstance(value, dict) or any(k not in DEFAULT_TAGS or not isinstance(v, str) for k, v in value.items())


def _message(title: str, text: str):
    from divide.ui.dialogs import information

    return information(title, text)


# ----------------------------------------------------------------- dialogs
class _TagRow(Horizontal):
    DEFAULT_CSS = """
    _TagRow { height: 1; }
    _TagRow .tr-label { width: 26; color: $text; }
    _TagRow InputLine { width: 18; }
    _TagRow .tr-default { width: 1fr; color: $text-muted; padding-left: 2; }
    """


class SectionDialog(_Dialog):
    """The tags of one section, with Div's defaults and a live preview."""

    DEFAULT_CSS = """
    SectionDialog { width: 78; }
    SectionDialog .sd-about { height: 1; color: $text-muted; background: $surface; }
    SectionDialog .sd-rows { height: auto; max-height: 12; background: $surface; margin-bottom: 1; }
    SectionDialog .sd-preview { height: 8; border: none; }
    SectionDialog .sd-verdict { height: 1; color: $text; background: $surface; }
    SectionDialog .sd-verdict.-bad { color: $error; }
    """

    def __init__(self, section: dx.Section, tags: dict[str, str], window: DialectorWindow) -> None:
        super().__init__(title=section.title)
        self.section = section
        self.tags = dict(tags)
        self.window_ref = window
        self.inputs: dict[str, InputLine] = {}
        for key in section.keys:
            line = InputLine(max_len=64)
            line.data = tags.get(key, DEFAULT_TAGS[key])
            self.inputs[key] = line
        self.preview = _preview_view("8")
        self.preview.add_class("sd-preview")
        self.verdict = Static("", classes="sd-verdict", markup=False)
        self.values: dict[str, str] = {}
        self.focused_key = section.keys[0]
        self._timer = None
        rows = min(12, len(section.keys))
        self.styles.height = rows + 15

    def compose_content(self) -> ComposeResult:
        yield Static(self.section.about, classes="sd-about", markup=False)
        with VerticalScroll(classes="sd-rows"):
            for key, label in self.section.fields:
                with _TagRow():
                    yield Label(label, link=self.inputs[key], classes="tr-label")
                    yield self.inputs[key]
                    default = DEFAULT_TAGS[key]
                    yield Static(f"default: {default}" if default else "default: (empty)", classes="tr-default", markup=False)
        yield self.preview
        yield self.verdict
        with Horizontal(classes="dlg-buttons"):
            yield Button("O~K~", Command.OK, is_default=True, id="ok")
            yield Button("~D~efaults", CM_DEFAULTS, id="defaults")
            yield Button("Cancel", Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self.update_preview)

    def current_tags(self) -> dict[str, str]:
        return {**self.tags, **{k: line.data for k, line in self.inputs.items()}}

    def update_preview(self) -> None:
        tags = self.current_tags()
        filled = dx.example(dx.overrides(tags), (self.section,), headings=False)
        marks = [(a, b, "dialector.focus") for a, b in filled.spans.get(self.focused_key, [])]
        _show(self.preview, filled, tags, marks)
        if self._timer is not None:
            self._timer.stop()
        self._timer = self.set_timer(0.4, self.check)

    @work(exclusive=True, group="dialector-dialog")
    async def check(self) -> None:
        tags = self.current_tags()
        verdict = await self.app.dialector_verdict(tags)  # type: ignore[attr-defined]
        text, bad = _verdict_text(verdict, tags, self.section)
        self.verdict.set_class(bad, "-bad")
        self.verdict.update(text)

    def on_input_line_changed(self, message) -> None:
        message.stop()
        self.update_preview()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        for key, line in self.inputs.items():
            if event.widget is line and key != self.focused_key:
                self.focused_key = key
                line.scroll_visible()
                self.update_preview()

    def on_command_message(self, message) -> None:
        if message.command == Command.OK:
            self.values = {k: line.data for k, line in self.inputs.items()}
        elif message.command == CM_DEFAULTS:
            message.stop()
            message.prevent_default()
            for key, line in self.inputs.items():
                line.data = DEFAULT_TAGS[key]
                line._cursor_pos = len(line.data)
                line.refresh()
            self.update_preview()


class TransformDialog(_Dialog):
    """Replace a piece of text in every tag at once (``{`` -> ``{{``...)."""

    DEFAULT_CSS = """
    TransformDialog { width: 70; height: 21; }
    TransformDialog InputLine { width: 1fr; margin-bottom: 1; }
    TransformDialog .tf-summary { height: 7; color: $text; background: $surface; }
    """

    def __init__(self, tags: dict[str, str]) -> None:
        super().__init__(title="Transform all tags")
        self.tags = tags
        self.find_input = InputLine(max_len=32)
        self.replace_input = InputLine(max_len=32)
        self.summary = Static("Type what to find in the tags, and what to write instead.", classes="tf-summary", markup=False)
        self.changes: dict[str, str] = {}

    def compose_content(self) -> ComposeResult:
        yield Label("~F~ind in the tags", link=self.find_input)
        yield self.find_input
        yield Label("~R~eplace with", link=self.replace_input)
        yield self.replace_input
        yield self.summary
        with Horizontal(classes="dlg-buttons"):
            yield Button("O~K~", Command.OK, is_default=True, id="ok")
            yield Button("Cancel", Command.CANCEL, id="cancel")

    def on_input_line_changed(self, message) -> None:
        message.stop()
        self.changes = dx.transform(self.tags, self.find_input.data, self.replace_input.data)
        if not self.find_input.data:
            self.summary.update("Type what to find in the tags, and what to write instead.")
            return
        lines = [f"{len(self.changes)} tag{'s' if len(self.changes) != 1 else ''} change:"]
        for key, value in list(self.changes.items())[:5]:
            lines.append(f"  {dx.LABELS[key]:<24} {self.tags[key]:>8}  →  {value}")
        if len(self.changes) > 5:
            lines.append(f"  ... and {len(self.changes) - 5} more")
        self.summary.update("\n".join(lines))


CM_PREVIEW = Command.USER + 61
CM_SAVE_TRANSLATION = Command.USER + 62
CM_OPEN_TRANSLATION = Command.USER + 63
CM_BROWSE_TEMPLATE = Command.USER + 64
CM_BROWSE_SOURCE = Command.USER + 65
CM_BROWSE_TARGET = Command.USER + 66


class TranslateDialog(_Dialog):
    """Translate a template from one dialect to another, as Div does it.

    Paths are relative to the project; an empty dialect is Div's default. The
    template's editor buffer is used when it is open. Preview shows Div's
    translation highlighted in the target dialect; Save as / Open end the
    dialog with ``text`` holding it.
    """

    DEFAULT_CSS = """
    TranslateDialog { width: 92; }
    TranslateDialog .tr-row { height: 1; margin-top: 1; }
    TranslateDialog .tr-row Label { width: 18; }
    TranslateDialog .tr-row InputLine { width: 1fr; }
    TranslateDialog .tr-row Button { margin-left: 1; min-width: 5; }
    TranslateDialog .tr-note { height: 1; color: $text-muted; background: $surface; }
    TranslateDialog .tr-preview { height: 1fr; }
    TranslateDialog .tr-status { height: 1; color: $text; background: $surface; }
    TranslateDialog .tr-status.-bad { color: $error; }
    """

    def __init__(self, template: str = "", source: str = "", target: str = "", *, root: Path | None = None) -> None:
        super().__init__(title="Translate a template")
        self.root = root or Path.cwd()
        self.template_input = InputLine(max_len=1024)
        self.template_input.data = template
        self.source_input = InputLine(max_len=1024)
        self.source_input.data = source
        self.target_input = InputLine(max_len=1024)
        self.target_input.data = target
        self.preview = _preview_view()
        self.preview.add_class("tr-preview")
        self.status = Static("Preview shows the template as Div translates it.", classes="tr-status", markup=False)
        self.source_note = Static("", classes="tr-note", markup=False)
        self.text: str | None = None
        self.target_dialect: Dialect | None = None
        self._asked: tuple[str, str, str] | None = None
        self._suggested: str | None = None  # the source field as last suggested (None: typed by the user)
        self._last = self.fields()

    def compose_content(self) -> ComposeResult:
        for label, line, command in (
            ("~T~emplate", self.template_input, CM_BROWSE_TEMPLATE),
            ("~F~rom dialect", self.source_input, CM_BROWSE_SOURCE),
        ):
            with Horizontal(classes="tr-row"):
                yield Label(label, link=line)
                yield line
                yield Button("...", command, id=f"browse-{command - CM_BROWSE_TEMPLATE}")
        yield self.source_note
        with Horizontal(classes="tr-row"):
            yield Label("T~o~ dialect", link=self.target_input)
            yield self.target_input
            yield Button("...", CM_BROWSE_TARGET, id="browse-2")
        yield Static("Paths relative to the project · an empty dialect is Div's default", classes="tr-note", markup=False)
        yield self.preview
        yield self.status
        with Horizontal(classes="dlg-buttons"):
            yield Button("~P~review", CM_PREVIEW, is_default=True, id="preview")
            yield Button("~S~ave as...", CM_SAVE_TRANSLATION, id="save")
            yield Button("Op~e~n", CM_OPEN_TRANSLATION, id="open")
            yield Button("Cancel", Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.styles.height = max(20, min(36, self.app.size.height - 2))
        if self.template_input.data:
            self.suggest(translate=True)

    @work(exclusive=True, group="translate-suggest")
    async def suggest(self, translate: bool = False) -> None:
        """Suggest the source dialect from the template's @_DIALECT (or Div's default)."""
        source, note = await self.app.suggest_source_dialect(self.template_input.data.strip())  # type: ignore[attr-defined]
        if self._suggested is not None or not self.source_input.data:
            self.source_input.data = source
            self.source_input._cursor_pos = len(source)
            self.source_input.refresh()
            self._suggested = source
            self.source_note.update(note)
        self._last = self.fields()
        if translate:
            self.run_translation()

    def fields(self) -> tuple[str, str, str]:
        return self.template_input.data.strip(), self.source_input.data.strip(), self.target_input.data.strip()

    @work(exclusive=True, group="translate-dialog")
    async def run_translation(self, then: Command | None = None) -> None:
        asked = self.fields()
        self.status.set_class(False, "-bad")
        self.status.update("Asking Div...")
        try:
            text, dialect = await self.app.translate_for_dialog(*asked)  # type: ignore[attr-defined]
        except ValueError as exc:
            self.text = None
            self.status.set_class(True, "-bad")
            self.status.update(f"[!] {exc}")
            return
        self.text, self.target_dialect, self._asked = text, dialect, asked
        self.preview.forced_dialect = dialect
        self.preview.load_text(text)
        lines = text.count("\n") + 1
        self.status.update(f"Div translated {lines} lines · shown in the target dialect")
        if then is not None:
            self.end_modal(then)

    def on_input_line_changed(self, message) -> None:
        message.stop()
        now = self.fields()
        if now[1] != self._last[1] and now[1] != self._suggested:
            self._suggested = None  # the user chose the source: no more suggestions
            self.source_note.update("Your choice (the template's own @_DIALECT is ignored)")
        if now[0] != self._last[0]:
            self.suggest()
        self._last = now
        if self._asked is not None and now != self._asked:
            self.status.update("Changed: Preview again (Enter)")

    @work(exclusive=True, group="translate-browse")
    async def browse(self, command: int) -> None:
        line, title, pattern = {
            CM_BROWSE_TEMPLATE: (self.template_input, "Template to translate", "*.tpl"),
            CM_BROWSE_SOURCE: (self.source_input, "Source dialect", "*.dialect"),
            CM_BROWSE_TARGET: (self.target_input, "Target dialect", "*.dialect"),
        }[command]
        if not await browse_into(self, line, title, pattern, self.root):
            return
        line.tv_select_self()  # back in the field (the TV focus, not only Textual's)
        line.focus()
        if line is self.source_input:
            self._suggested = None
            self.source_note.update("Your choice (the template's own @_DIALECT is ignored)")
        self._last = self.fields()
        # a chosen file is a clear intent: preview right away (a new template: its dialect first)
        if line is self.template_input:
            self.suggest(translate=True)
        else:
            self.run_translation()

    def on_command_message(self, message) -> None:
        if message.command in (CM_BROWSE_TEMPLATE, CM_BROWSE_SOURCE, CM_BROWSE_TARGET):
            message.stop()
            message.prevent_default()
            self.browse(message.command)
            return
        if message.command in (CM_PREVIEW, CM_SAVE_TRANSLATION, CM_OPEN_TRANSLATION):
            message.stop()
            message.prevent_default()
            if message.command == CM_PREVIEW:
                self.run_translation()
            elif self.text is not None and self.fields() == self._asked:
                self.end_modal(message.command)
            else:
                self.run_translation(then=message.command)


__all__ = ["DialectorWindow", "SectionDialog", "TransformDialog", "TranslateDialog"]
