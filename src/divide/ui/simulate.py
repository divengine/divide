"""Flow Simulation & Playback: a Flow simulated by Runner with test doubles, replayed on its board.

``SimulationMixin`` is part of the app. **Run > Simulate Flow with doubles**
(Shift+F9), or **S** on the Flow Designer's board, opens the Simulate Flow
dialog: the initial context, the doubles file (Runner's ``--simulate``
format) and which of the Flow's functions still lack a double. A simulation
with a reference without a double is refused before anything runs.

Runner simulates (:mod:`divide.run.simulate`): no Function of the project is
loaded or called. Its trace opens in the **Simulation window**, the Flow's
board as it was simulated, read-only, with the playback's marks over it
(current, visited, skipped, waiting for a call, paused, failed; the calls and
jumps taken) and the selected event in the panel. Moving through the events
only moves a cursor: nothing runs again, and neither the YAML nor any file
changes. A paused simulation resumes (Ctrl+F9) in a new PHP process, from
Runner's own session; the new segment is added to the same playback.

Keys in the Simulation window: F7 / Shift+F7 the next / previous event, F8 /
Shift+F8 the next / previous Step, Ctrl+Home / Ctrl+End the first / last event,
F4 (or Enter on a card) the selected Step's next event, F follows the current
Step or not, X the context at the event, Ctrl+F2 back to the start, Ctrl+F9
resumes (when paused) or simulates again. Ctrl+F9 in the Flow's code or
Designer stays the real Run.
"""

from __future__ import annotations

from divide.i18n import _

import json
import shutil
from pathlib import Path

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.cluster import CheckBoxes
from textual_vision.constants import Command
from textual_vision.input_line import InputLine
from textual_vision.label import Label

from divide import config, themes
from divide.run import flowmodel as fm
from divide.run import simulate as sim
from divide.run.flow import Runner, check_context_file, check_context_text, find_runner
from divide.run.script import size_text
from divide.ui.dialogs import _Dialog, confirm, information
from divide.ui.flowboard import FlowBoard, FlowDesignWindow, card_width
from divide.ui.flowlayout import MARKS, Board, Overlay
from divide.ui.progress import ProgressDialog, run_with_progress
from divide.ui.windows import EditorWindow

CM_SIM_EDIT = Command.USER + 231
CM_SIM_REPLAY = Command.USER + 234

NOTICE = _("SIMULATION: Runner answers every condition and activity from the doubles; no Function of the project is "
           "loaded or called. Not a sandbox: the YAML and the doubles are trusted inputs.")
VERDICTS = {
    "done": (_("Done"), True), "paused": (_("Paused"), True), "error": (_("Error"), False),
    "invocation": (_("Not run"), False), "crashed": (_("PHP ended"), False),
    "cancelled": (_("Stopped"), False), "timeout": (_("Time limit"), False),
}
MARK_SHORT = {"current": _("current"), "visited": _("visited"), "skipped": _("skipped"), "active": _("in a call"),
              "paused": _("paused"), "failed": _("failed")}
MARK_WORDS = {"current": _("current"), "visited": _("visited"), "skipped": _("skipped"), "paused": _("paused"),
              "failed": _("failed"), "active": _("waiting for its call")}


def sim_settings(flow: Path) -> dict:
    saved = config.load().get("simulations")
    here = saved.get(str(flow)) if isinstance(saved, dict) else None
    here = here if isinstance(here, dict) else {}
    return {"context": str(here.get("context") or ""), "doubles": str(here.get("doubles") or ""),
            "messages": bool(here.get("messages"))}


def save_sim_settings(flow: Path, values: dict) -> None:
    settings = config.load()
    saved = settings.get("simulations") if isinstance(settings.get("simulations"), dict) else {}
    saved[str(flow)] = {key: values[key] for key in ("context", "doubles", "messages")}
    settings["simulations"] = saved
    config.save(settings)


def last_session(project: Path, flow: Path) -> Path | None:
    """The newest recorded simulation of ``flow`` with a trace to replay, or None."""
    shown = _rel(flow, project)
    for folder in sim.sessions(project):
        try:
            meta = json.loads((folder / sim.META).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if isinstance(meta, dict) and meta.get("flow") == shown and (folder / "trace-1.json").is_file():
            return folder
    return None


def _rel(path: Path, project: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return str(path)


def _json(value, limit: int = 400) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
    return text if len(text) <= limit else text[:limit - 1] + "~"


# ---------------------------------------------------------------- the dialog
class SimulationDialog(_Dialog):
    """The initial context and the doubles of a simulation, and what is missing; Simulate."""

    DEFAULT_CSS = """
    SimulationDialog { width: 78; height: 23; }
    SimulationDialog InputLine { width: 1fr; }
    SimulationDialog .sim-about { color: $text; background: $surface; height: 1; }
    SimulationDialog .sim-status { color: $text; background: $surface; height: 4; margin-top: 1; }
    SimulationDialog .sim-notice { height: 3; margin-top: 1; }
    SimulationDialog CheckBoxes { height: 1; width: 1fr; }
    """

    def __init__(self, flow: Path, project: Path, runner: Runner, doc: fm.FlowDoc, settings: dict, *, dirty: bool) -> None:
        super().__init__(title=_('Simulate Flow'))
        self.flow, self.project, self.runner, self.doc, self.dirty = flow, project, runner, doc, dirty
        self.context_input = InputLine(max_len=65536)
        self.context_input.data = settings["context"]
        self.doubles_input = InputLine(max_len=1024)
        self.doubles_input.data = settings["doubles"] or _rel(sim.default_spec_path(flow, project), project)
        self.options = CheckBoxes([_('~K~eep error and log messages in the trace (--trace-messages)')])
        self.options.value = 1 if settings["messages"] else 0
        self.status = Static("", classes="sim-status", markup=False)
        self.values: dict = {}
        self.spec: dict = {}
        self.context: dict = {}
        self.check: sim.SpecCheck | None = None
        self.edit = False  # Edit doubles chosen: the doubles file opens in an editor, nothing runs
        self.last = last_session(project, flow)
        self.replay = False  # Replay last chosen: the last recorded simulation opens, nothing runs

    def compose_content(self) -> ComposeResult:
        snapshot = _(' · unsaved changes simulated as they are, the file not saved') if self.dirty else ""
        yield Static(_('Flow {flow} · Runner {version}{snapshot}').format(
            flow=_rel(self.flow, self.project), version=self.runner.version or "?", snapshot=snapshot), classes="sim-about", markup=False)
        yield Label(_('~I~nitial context: a JSON file, or a JSON object typed here (optional)'), link=self.context_input)
        yield self.context_input
        yield Label(_('~D~oubles: a JSON file in Runner\'s --simulate format'), link=self.doubles_input)
        yield self.doubles_input
        yield self.options
        yield self.status
        yield Static(Text(NOTICE, style=themes.current().token_styles()["diag.warning"]), classes="sim-notice")
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('~S~imulate'), Command.OK, is_default=True, id="simulate")
            yield Button(_('~E~dit doubles'), CM_SIM_EDIT, id="edit")
            yield Button(_('~R~eplay'), CM_SIM_REPLAY, id="replay", disabled=self.last is None)
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.show_status()
        self.call_after_refresh(self.context_input.select_all)

    def path_of(self, text: str) -> Path | None:
        text = text.strip()
        if not text:
            return None
        path = Path(text).expanduser()
        return (path if path.is_absolute() else self.project / path).resolve()

    def read(self) -> tuple[dict | None, sim.SpecCheck | None, str | None]:
        """The doubles file's data and its check, or why it cannot be read."""
        path = self.path_of(self.doubles_input.data)
        if path is None:
            return None, None, _('Give the doubles file (Edit doubles writes one with a double for each function).')
        if not path.is_file():
            return None, None, _('No file {path}: Edit doubles writes one with a double for each function.').format(path=_rel(path, self.project))
        try:
            data = sim.read_spec(path)
        except sim.SimulationError as exc:
            return None, None, str(exc)
        doubles = data.get("doubles") if isinstance(data, dict) and isinstance(data.get("doubles"), dict) else {}
        reqs = sim.requirements(self.doc, project=self.project, doubles=doubles)
        return data if isinstance(data, dict) else None, sim.check_spec(data, reqs, self.project), None

    def show_status(self) -> None:
        reqs = sim.requirements(self.doc, project=self.project)
        data, check, problem = self.read()
        lines = [_('{n} function(s) of the Flow need a double.').format(n=len(reqs))]
        if problem is not None:
            lines.append(problem)
        elif check is not None:
            if check.missing:
                lines.append(_('No double yet for: {names}').format(names=", ".join(r.key for r in check.missing[:8])
                                                                     + (" ..." if len(check.missing) > 8 else "")))
            lines += check.problems[:2]
            if check.ok:
                lines.append(_('Every function has a double: ready to simulate.'))
            lines += check.warnings[:1]
        self.status.update("\n".join(lines))

    def on_input_line_changed(self, event) -> None:
        self.show_status()

    def on_command_message(self, message) -> None:
        handlers = {CM_SIM_EDIT: self._edit}
        if message.command in handlers:
            message.stop()
            message.prevent_default()
            self.run_worker(handlers[message.command](), exclusive=True)
        elif message.command == CM_SIM_REPLAY:
            message.stop()
            message.prevent_default()
            if self.last is not None:
                self.replay = True
                self._remember()
                super().end_modal(Command.OK)

    async def _edit(self) -> None:
        """Edit doubles: the file made (or completed) first, then opened in an editor; nothing runs."""
        if await self._make():
            self.edit = True
            self._remember()
            super().end_modal(Command.OK)

    async def _make(self) -> bool:
        """A doubles file with a double for every function, or the missing ones added to it if you say so
        (the rest of the file as it was). Only on Edit doubles: divide never writes it otherwise. False
        when there is no file to open."""
        path = self.path_of(self.doubles_input.data) or sim.default_spec_path(self.flow, self.project)
        reqs = sim.requirements(self.doc, project=self.project)
        if path.exists():
            try:
                data = sim.read_spec(path)
            except sim.SimulationError:
                return True  # as it is, to fix in the editor
            if not isinstance(data, dict) or not isinstance(data.get("doubles", {}), dict):
                return True
            doubles = data.setdefault("doubles", {})
            missing = [r for r in reqs if r.key not in doubles]
            if not missing:
                return True
            if await self.app.run_dialog(confirm(_('Edit doubles'), _(  # type: ignore[attr-defined]
                    'Add a double for {names} to {path}? The rest of the file stays as it is.').format(
                    names=", ".join(r.key for r in missing), path=_rel(path, self.project)))) != Command.YES:
                return True
            doubles.update(sim.template(missing)["doubles"])
        else:
            data = sim.template(reqs, _('Doubles of {flow}: edit what each function returns').format(flow=_rel(self.flow, self.project)))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as exc:
            self.app.notify(str(exc), severity="error", timeout=6)
            return False
        self.doubles_input.data = _rel(path, self.project)
        self.show_status()
        self.app.notify(_('Written: {path}: edit what the doubles return, then Shift+F9').format(path=_rel(path, self.project)), timeout=5)
        return True

    def _remember(self) -> None:
        self.values = {"context": self.context_input.data.strip(), "doubles": self.doubles_input.data.strip(),
                       "messages": bool(self.options.value & 1)}

    def valid(self, command: Command) -> bool:
        if command != Command.OK or self.edit or self.replay:
            return True
        given = self.context_input.data.strip()
        problem = None
        context: object = {}
        if given.startswith("{"):
            problem = check_context_text(given)
            if problem is None:
                context = json.loads(given)
        elif given:
            path = self.path_of(given)
            problem = check_context_file(path) if path is not None else None
            if problem is None and path is not None:
                context = json.loads(path.read_text(encoding="utf-8"))
        if problem is None:
            data, check, problem = self.read()
            if problem is None and check is not None and not check.ok:
                problem = _('The simulation would not be complete, nothing was run:\n') + "\n".join(check.messages()[:6])
            if problem is None:
                self.spec, self.check = data or {}, check
        if problem is not None:
            self.app.notify(problem, severity="error", timeout=8)
            return False
        self.context = context if isinstance(context, dict) else {}
        self._remember()
        return True


# ---------------------------------------------------------------- the board, replayed
class PlaybackBoard(FlowBoard, inherit_bindings=False):
    """The Flow Designer's board, read-only: moving around it and through the playback, never editing."""

    BINDINGS = [
        Binding("up", "move(0, -1)", "Up", show=False),
        Binding("down", "move(0, 1)", "Down", show=False),
        Binding("left", "move(-1, 0)", "Left", show=False),
        Binding("right", "move(1, 0)", "Right", show=False),
        Binding("home", "edge(-1)", "Title", show=False),
        Binding("end", "edge(1)", "Last", show=False),
        Binding("pageup", "page(-1)", "Page up", show=False),
        Binding("pagedown", "page(1)", "Page down", show=False),
        Binding("enter", "enter", "Go to its event", show=False),
        Binding("backspace", "back", "Back", show=False),
        Binding("shift+f7", "playback('event', -1)", "Previous event", show=False),
        Binding("ctrl+home", "playback('first', 0)", "First event", show=False),
        Binding("ctrl+end", "playback('last', 0)", "Last event", show=False),
        Binding("f", "playback('follow', 0)", "Follow", show=False),
        Binding("x", "playback('context', 0)", "Context", show=False),
    ]

    def _window(self) -> "SimulationWindow":
        return next(a for a in self.ancestors if isinstance(a, SimulationWindow))

    def action_playback(self, what: str, step: int) -> None:
        self._window().playback_key(what, step)


class SimulationWindow(FlowDesignWindow):
    """A simulation's playback: the board as simulated, read-only, its marks at the cursor; the event
    and the context in the panel."""

    HINT = _('F7/F8 event/Step · Shift back · F4 to Step · F follow · X context · ^F9 resume')
    DEFAULT_CSS = """
    SimulationWindow.narrow .sim-legend { display: none; }
    SimulationWindow.narrow .design-right { height: 12; }
    """

    def compose_content(self) -> ComposeResult:
        from textual.containers import Vertical, VerticalScroll
        from divide.ui.windows import HRule, VRule
        with Vertical(classes="design-main"):
            with Vertical(classes="design-left"):
                yield self.board_view
            yield VRule(classes="design-vrule")
            yield HRule(classes="design-hrule-top")
            with Vertical(classes="design-right"):
                yield self.bar
                with VerticalScroll():
                    yield self.inspector
                yield HRule(classes="sim-legend")
                yield self.summary
                yield HRule()
                yield self.verdict

    def __init__(self, source: EditorWindow, session: sim.Session, number: int = 0) -> None:
        self.session = session
        super().__init__(source, number=number)
        self.board_view = PlaybackBoard()
        self.summary.add_class("sim-legend")  # the legend: left out when narrow, for the board and the event
        self.doc = fm.parse(session.snapshot_text)
        self.shown = self.doc
        self.playback = sim.Playback(session.traces, self.doc)
        self.playback.last()
        self.follow = True
        self.view: sim.View = sim.View()
        self.notice = ""  # what changed since (the YAML, the doubles)

    def _make_title(self) -> str:
        return _('Simulation: {name}').format(name=self.source.display_name)

    @property
    def read_only(self) -> bool:
        return True

    def _severity(self, item) -> str | None:
        return None  # the editor's diagnostics are about its text now, not the snapshot's

    def reload(self) -> None:
        """The Flow's code changed: the board stays the simulated one; the panel says it changed."""
        changed = self.session.changed(self.source.editor.text)
        notice = _('Changed since: {what}. The board is the Flow as simulated.').format(what=", ".join(changed)) if changed else ""
        if notice != self.notice:
            self.notice = notice
            self.repaint()

    def show_verdict(self, verdict: str, bad: bool) -> None:
        self.show_result()  # Runner's verdict on the code is the Designer's; here, the simulation's

    def source_range(self) -> tuple[int, int] | None:
        if self.session.changed(self.source.editor.text):
            return None  # the snapshot's places are not the code's any more
        return super().source_range()

    def action_switch_view(self) -> None:
        self.app.notify(_('The Simulation window has one view: the board as simulated'), timeout=3)

    # ------------------------------------------------------------ painting
    def rebuild(self, cursor=None) -> None:
        columns = self.board_view.size.width or max(40, (self.size.width or 120) - 42)
        self.board = Board(self.shown, card_width=card_width(columns), severity=self._severity)
        key = cursor or self.key
        if key is None or key not in self.board.boxes:
            key = self._nearest(key)
        self.key = key
        self._built = self.doc.text
        self.refresh_view()

    def refresh_view(self) -> None:
        self.view = self.playback.view()
        self.overlay = Overlay(dict(self.view.marks), set(self.view.taken))
        if self.follow and self.view.current is not None and self.board is not None and self.view.current in self.board.boxes:
            if self.key != self.view.current:
                self.connection = None
            self.key = self.view.current
        self.repaint()

    def repaint(self) -> None:
        if self.board is None or not self.is_mounted:
            return
        self.board_view.show(self.board, self.key, self.chosen(), self.overlay)
        self.show_bar()
        self.show_selected()
        self.show_result()

    def show_bar(self) -> None:
        playback = self.playback
        bar = Text()
        strong = Style(bold=True)
        event = playback.event
        bar.append(_('SIMULATION') + " ", style=strong)
        if event is None:
            bar.append(_('no events'))
        else:
            bar.append(_('event {n}/{total} · segment {s}/{segments}').format(
                n=playback.cursor + 1, total=len(playback), s=event.segment, segments=playback.segments))
            if not self.follow:
                bar.append(" · " + _('not following'))
        self.bar.display = True
        self.bar.update(bar)
        self.show_summary()

    def show_summary(self) -> None:
        dim = themes.current().token_styles().get("div.comment")
        text = Text()
        for n, mark in enumerate(("current", "visited", "skipped", "active", "paused", "failed")):
            text.append(MARKS[mark], style=Style(bold=True, reverse=True))
            text.append(f" {MARK_SHORT[mark]}" + ("\n" if n == 2 else "  "))
        text.append("\n")
        text.append("─", style=Style(bold=True))
        text.append(_(' CALL returns  '))
        text.append("═", style=Style(bold=True))
        text.append(_(' JUMP goes on  '))
        text.append(_('underlined: taken'), style=dim)
        self.summary.update(text)

    def show_result(self) -> None:
        if not self.is_mounted:
            return
        session = self.session
        lines = []
        last = session.segments[-1] if session.segments else None
        if last is not None:
            word = VERDICTS.get(last.state, (last.state, False))[0]
            where = self._paused_at()
            lines.append(_('Segment {n}: {state}{where}').format(n=last.number, state=word, where=where))
            if last.state == "paused":
                lines.append(_('Ctrl+F9 resumes it, simulated, in a new process.'))
            error = last.trace.result.get("error") if last.trace is not None else None
            if isinstance(error, dict):
                lines.append(_('Error: {cls} {message}').format(cls=error.get("class") or "", message=self._message(error.get("message"))))
            if last.problem:
                lines.append(last.problem)
        cut = [t for t in session.traces if t.truncated]
        if cut:
            info = cut[-1].truncation
            lines.append(_('Trace cut ({reason}): {dropped} event(s) dropped, {compacted} compacted.').format(
                reason=info.get("reason") or "?", dropped=info.get("dropped_events", 0), compacted=info.get("compacted_events", 0)))
        if self.notice:
            lines.append(self.notice)
        bad = last is None or not last.ok or bool(cut)
        self.verdict.update(Text("\n".join(lines), style=themes.current().token_styles().get("diag.error") if bad else None))

    def _paused_at(self) -> str:
        last = self.session.traces[-1] if self.session.traces else None
        if last is None or last.state != "paused":
            return ""
        pause = next((e for e in reversed(last.events) if e.get("type") == "pause"), None)
        if pause is None:
            return ""
        return _(' at {where}').format(where=f"{pause.get('block')}.{pause.get('step')}")

    @staticmethod
    def _message(value) -> str:
        if isinstance(value, dict) and value.get("$type") == "redacted":
            return _('(message left out of the trace: Keep messages to see it)')
        return str(value) if value is not None else ""

    # ------------------------------------------------------------ the inspector
    def describe(self, item) -> Text:
        playback, view = self.playback, self.view
        dim = themes.current().token_styles().get("div.comment")
        key_style = themes.current().token_styles().get("json.key")
        bad = themes.current().token_styles().get("diag.error")
        text = Text()
        event = playback.event
        if event is None:
            text.append(_('Runner recorded no events.'))
            return text
        data = event.data

        def row(name: str, value: str, style=None) -> None:
            text.append(f"{name:<9} ", style=dim)
            text.append(value + "\n", style=style)

        text.append(f"#{event.seq} ", style=dim)
        text.append(event.type + "\n", style=key_style)
        if event.block is not None:
            where = f"{event.block}.{event.step}" if event.step is not None else _('Block {block}').format(block=event.block)
            row(_('where'), where)
        if event.depth or data.get("call_depth"):
            row(_('depth'), _('flow {flow}, calls {calls}').format(flow=event.depth, calls=data.get("call_depth", 0)))
        if view.scope:
            row(_('scope'), _('nested Flow: {names}').format(names=" > ".join(view.scope)))
        kind = event.type
        if kind == "run.start":
            row(_('start'), _('resumed from its checkpoint') if data.get("resume") else _('from the initial context'))
            self._checkpoint(row, data.get("checkpoint"))
        elif kind == "run.end":
            row(_('state'), str(data.get("state")), None if data.get("state") in ("done", "paused") else bad)
            if isinstance(data.get("error"), dict):
                row(_('error'), f"{data['error'].get('class', '')} {self._message(data['error'].get('message'))}", bad)
            self._checkpoint(row, data.get("checkpoint"))
        elif kind == "block.enter":
            reasons = {"start": _('the Flow starts here'), "resume": _('resumed here'), "call": _('called'),
                       "jump": _('jumped to'), "return": _('a call returned here')}
            row(_('reason'), reasons.get(str(data.get("reason")), str(data.get("reason"))))
        elif kind == "step.skip":
            reasons = {"condition_false": _('its condition was false: the rest of the Step was skipped'),
                       "before_target": _('before the target of a call or jump'),
                       "before_checkpoint": _('already run before the pause')}
            row(_('skipped'), reasons.get(str(data.get("reason")), str(data.get("reason"))))
        elif kind == "step.start" and data.get("continuation"):
            row(_('step'), _('its call returns into it after the resume'))
        elif kind == "condition":
            result = data.get("result")
            row(_('function'), str(data.get("function")))
            row(_('result'), (_('true: the Step goes on') if result else _('false: the rest of the Step is skipped'))
                + (f" ({_json(data.get('value'))})" if "value" in data else ""))
        elif kind in ("condition.error", "activity.error"):
            row(_('function'), str(data.get("function")))
            error = data.get("error") if isinstance(data.get("error"), dict) else {}
            row(_('error'), f"{error.get('class', '')} {self._message(error.get('message'))}", bad)
        elif kind == "activity.start":
            row(_('function'), str(data.get("function")))
        elif kind in ("activity.end", "activity.pause"):
            row(_('function'), str(data.get("function")))
            if kind == "activity.end":
                row(_('result'), _json(data.get("result")) + "  " + _('(kept under the Step id)'))
            else:
                row(_('pause'), _('it asked to pause: a pause follows'))
        elif kind == "call":
            target = playback.target_key(data.get("target"))
            row(_('CALL'), (f"{target[1]}.{target[2]}" if target else _json(data.get("target")))
                + "  " + _('returns here when the Block ends'))
        elif kind == "jump":
            target = playback.target_key(data.get("target"))
            row(_('JUMP'), (f"{target[1]}.{target[2]}" if target else _json(data.get("target")))
                + "  " + _('goes on there, does not return'))
        elif kind == "call.return":
            back = playback.target_key(data.get("to"))
            row(_('RETURN'), _('from {block} to {step}').format(block=data.get("from"), step=f"{back[1]}.{back[2]}" if back else "?")
                + (" · " + _('the frame came from the checkpoint') if data.get("resumed") else ""))
        elif kind == "call.drop":
            row(_('dropped'), _('a jump left the called Blocks: {frames}').format(frames=_json(data.get("frames"))))
        elif kind == "pause":
            row(_('pause'), _('the run pauses after this Step'))
            self._checkpoint(row, data.get("checkpoint"))
        elif kind == "double":
            row(_('double'), _('{function}, call {n}: {outcome}').format(
                function=data.get("function"), n=data.get("call"), outcome=data.get("outcome")))
        elif kind == "function.missing":
            row(_('missing'), _('no double for {function}: the run fails').format(function=data.get("function")), bad)
        elif kind == "budget.exhausted":
            row(_('budget'), _('{budget}: {used} of {limit}').format(budget=data.get("budget"), used=data.get("used"),
                                                                     limit=data.get("limit")), bad)
        elif kind == "log":
            row(str(data.get("level") or "log"), self._message(data.get("message")))
        elif kind == "trace.truncated":
            row(_('cut'), _('{reason}: {dropped} dropped, {compacted} compacted').format(
                reason=data.get("reason"), dropped=data.get("dropped_events"), compacted=data.get("compacted_events")), bad)
        elif kind == "context.update":
            row("SET", _('the Step\'s context mapping, merged'))
        elif kind == "flow.enter":
            row(_('nested'), _('a Flow used as an activity starts at {block}').format(block=data.get("initial_block")))
        elif kind == "flow.exit":
            row(_('nested'), _('the nested Flow ends: {outcome}').format(outcome=data.get("outcome")))
        elif kind not in ("step.start", "block.exit"):
            known = {"seq", "type", "flow_depth", "call_depth", "block", "step", "index", "changes"}
            for name, value in data.items():
                if name not in known:
                    row(str(name), _json(value, 120))
        changes = data.get("changes")
        if isinstance(changes, list) and changes:
            text.append("\n" + _('Context changes') + "\n", style=dim)
            for change in changes[:30]:
                if not isinstance(change, dict) or "key" not in change:
                    text.append("  " + _json(change, 80) + "\n", style=dim)
                    continue
                op = change.get("op")
                mark = {"added": "+", "changed": "~", "removed": "-"}.get(str(op), "?")
                if op == "changed":
                    value = f"{_json(change.get('before'), 60)} -> {_json(change.get('after'), 60)}"
                elif op == "removed":
                    value = _json(change.get("before"), 60)
                else:
                    value = _json(change.get("after"), 120)
                text.append(f"  {mark} {change['key']} = {value}\n")
        logs = [e for e in playback.logs_near() if e is not event]
        if logs:
            text.append("\n" + _('Logs of this Step') + "\n", style=dim)
            for log in logs[:10]:
                text.append(f"  {log.data.get('level', '')}: {self._message(log.data.get('message'))}\n")
        if view.stack:
            text.append("\n")
            row(_('calls'), " > ".join(f"{k[1]}.{k[2]}" for k in view.stack))
        text.append("\n")
        row(_('context'), _('{n} key(s){approx} · X shows it').format(
            n=len(view.context), approx=_(', some values cut by the trace') if view.approximate else ""))
        if isinstance(item, fm.Step):
            key = ("step", item.block, item.id)
            mark = view.marks.get(key)
            text.append("\n")
            text.append(_('Card {name}').format(name=item.name), style=key_style)
            text.append("  " + _('{n} time(s) run · {state}').format(
                n=playback.occurrences(key), state=MARK_WORDS.get(mark, _('not reached'))) + "\n", style=dim)
            text.append(_('F4 or Enter: its next event') + "\n", style=dim)
        return text

    def _checkpoint(self, row, checkpoint) -> None:
        if not isinstance(checkpoint, dict):
            return
        state, stack = checkpoint.get("flow_state"), checkpoint.get("flow_stack")
        if isinstance(state, dict) and state:
            row("_flow_state", _json(state, 160))
        if isinstance(stack, list) and stack:
            row("_flow_stack", _json(stack, 200))

    # ------------------------------------------------------------ moving through the playback
    def playback_key(self, what: str, step: int) -> None:
        playback = self.playback
        if what == "event":
            playback.next(step)
        elif what == "step":
            playback.next_step(step)
        elif what == "first":
            playback.first()
        elif what == "last":
            playback.last()
        elif what == "reset":
            playback.first()
            self.follow = True
        elif what == "goto":
            self.goto_selected()
            return
        elif what == "follow":
            self.follow = not self.follow
            self.app.notify(_('The board follows the current Step') if self.follow else _('The board stays where you move'), timeout=2)
        elif what == "context":
            self.app.show_simulation_context(self)  # type: ignore[attr-defined]
            return
        self.refresh_view()

    def goto_selected(self) -> None:
        if self.key is None or self.key[0] != "step":
            self.app.notify(_('Choose a Step on the board'), timeout=2)
            return
        if not self.playback.find_step(self.key):
            self.app.notify(_('{step} was not reached in this simulation').format(step=f"{self.key[1]}.{self.key[2]}"), timeout=3)
            return
        self.refresh_view()

    def enter(self) -> None:
        if self.chosen() is not None:
            self.follow_connection()
        elif self.key is not None and self.key[0] == "step":
            self.goto_selected()

    def follow_connection(self) -> None:
        conn = self.chosen()
        other = (conn.target if conn.source == self.key else conn.source) if conn is not None else None
        if other is not None:
            self.follow = False
            self.select(other)

    def add_session_segment(self) -> None:
        """The session has one more segment: the playback goes on with it, at its end."""
        self.playback = sim.Playback(self.session.traces, self.doc)
        self.playback.last()
        self.follow = True
        self.refresh_view()

    def context_text(self) -> str:
        event = self.playback.event
        view = self.view
        head = [_('Context at event {n} of {total} ({type}{where}), rebuilt from the trace{approx}.').format(
            n=self.playback.cursor + 1, total=len(self.playback), type=event.type if event else "-",
            where=f", {event.block}.{event.step}" if event is not None and event.step else "",
            approx=_('; values marked $type were cut or redacted by the trace') if view.approximate else "")]
        return "\n".join(head) + "\n\n" + json.dumps(view.context, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------- the app's part
class SimulationMixin:
    """Flow simulations (mixed into the Divide app)."""

    def _simulation_init(self) -> None:
        self.last_simulation: sim.Session | None = None

    def simulation_windows(self) -> list[SimulationWindow]:
        return [w for w in self.windows() if isinstance(w, SimulationWindow)]  # type: ignore[attr-defined]

    def wants_simulation(self) -> bool:
        """Ctrl+F9 and the playback keys go to the Simulation window when it is the active one."""
        return isinstance(self.active_window(), SimulationWindow) and not getattr(self, "debugging", False)  # type: ignore[attr-defined]

    def playback_command(self, what: str, step: int = 0) -> None:
        win = self.active_window()  # type: ignore[attr-defined]
        if isinstance(win, SimulationWindow):
            win.playback_key(what, step)

    async def simulation_ctrl_f9(self) -> None:
        win = self.active_window()  # type: ignore[attr-defined]
        if isinstance(win, SimulationWindow) and win.session.paused:
            await self.resume_simulation(win)
        elif isinstance(win, SimulationWindow):
            await self.simulate_command(win.source)

    async def simulate_command(self, source: EditorWindow | None = None) -> None:
        """Run > Simulate Flow with doubles (Shift+F9, S on the board): the dialog, then the first segment."""
        source = source or self.flow_source()  # type: ignore[attr-defined]
        title = _('Simulate Flow')
        if source is None:
            self.notify(_('Open a Runner Flow first: a YAML file whose root has blocks'), timeout=3)  # type: ignore[attr-defined]
            return
        if source.path is None:
            await self.run_dialog(information(title, _('Save the Flow once (F2): a simulation names its file.')))  # type: ignore[attr-defined]
            return
        project = self.root  # type: ignore[attr-defined]
        if not shutil.which("php"):
            await self.run_dialog(information(title, _('php was not found in the PATH: Runner is PHP.')))  # type: ignore[attr-defined]
            return
        runner = find_runner(project)
        problem = sim.simulation_problem(runner)
        if problem is not None:
            await self.run_dialog(information(title, problem))  # type: ignore[attr-defined]
            return
        text = source.editor.text
        doc = fm.parse(text)
        if doc.problems:
            await self.run_dialog(information(title, _('The YAML has errors; fix them first (Ctrl+T):\n{error}').format(  # type: ignore[attr-defined]
                error=doc.problems[0].message)))
            return
        flow = source.path.resolve()
        dialog = SimulationDialog(flow, project, runner, doc, sim_settings(flow), dirty=bool(source.dirty))
        if await self.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        save_sim_settings(flow, dialog.values)
        if dialog.replay and dialog.last is not None:
            try:
                session = sim.load_session(dialog.last, project)
            except sim.SimulationError as exc:
                await self.run_dialog(information(title, str(exc)))  # type: ignore[attr-defined]
                return
            self.open_simulation(source, session)
            return
        if dialog.edit:
            path = dialog.path_of(dialog.values["doubles"])
            if path is not None and path.is_file():
                self.open_file(path)  # type: ignore[attr-defined]
            return
        spec_from = dialog.path_of(dialog.values["doubles"])
        context_from = _('typed') if dialog.values["context"].startswith("{") else dialog.values["context"]
        try:
            session = sim.new_session(project, flow, text, dialog.spec, spec_from, dialog.context,
                                      context_from=context_from, messages=dialog.values["messages"])
        except OSError as exc:
            await self.run_dialog(information(title, str(exc)))  # type: ignore[attr-defined]
            return
        sim.cleanup(project, active={w.session.folder for w in self.simulation_windows()} | {session.folder})
        segment = await self._run_segment(runner, session)
        if segment is None or segment.trace is None:
            await self._segment_failed(session, segment)
            return
        self.open_simulation(source, session)
        self._say_segment(session, segment)

    def open_simulation(self, source: EditorWindow, session: sim.Session) -> SimulationWindow:
        """The Simulation window of a recorded session: its traces replayed, nothing run."""
        self.last_simulation = session
        win = SimulationWindow(source, session, number=self._free_number())  # type: ignore[attr-defined]
        for attr in ("offset", "width", "height"):
            setattr(win.styles, attr, getattr(source.styles, attr))
        self.insert_window(win)  # type: ignore[attr-defined]
        return win

    async def resume_simulation(self, win: SimulationWindow) -> None:
        """Ctrl+F9 on a paused simulation: its next segment, from Runner's session, in a new process."""
        session = win.session
        changed = session.changed(win.source.editor.text)
        if changed:
            answer = await self.run_dialog(confirm(_('Resume simulation'), _(  # type: ignore[attr-defined]
                'Changed since this simulation started: {what}. Resume simulates the snapshot it started with, '
                'as the board shows it, not the changes (Shift+F9 starts a new simulation for them). Resume?').format(
                what=", ".join(changed))))
            if answer != Command.YES:
                return
        runner = find_runner(session.project)
        problem = sim.simulation_problem(runner)
        if problem is not None:
            await self.run_dialog(information(_('Resume simulation'), problem))  # type: ignore[attr-defined]
            return
        segment = await self._run_segment(runner, session)
        if segment is None or segment.trace is None:
            await self._segment_failed(session, segment)
            win.show_result()
            return
        win.add_session_segment()
        self._say_segment(session, segment)

    async def _run_segment(self, runner: Runner, session: sim.Session) -> sim.Segment | None:
        number = len(session.segments) + 1
        box = ProgressDialog(_('Simulating Flow') if number == 1 else _('Resuming simulation'), [
            (_('Flow'), session.meta.get("flow") or session.flow.name),
            (_('Segment'), str(number)),
            (_('Doubles'), session.meta.get("doubles_from") or "-"),
            (_('Said'), size_text(b"")),
        ], width=60)

        def progress(out: bytes, err: bytes) -> None:
            box.set(_('Said'), size_text(err))

        def verdict(segment: sim.Segment) -> tuple[str, bool, list[tuple[str, str]]]:
            word, ok = VERDICTS.get(segment.state, (segment.state, False))
            rows = [(_('Exit code'), str(segment.exit_code))]
            if segment.trace is not None:
                rows.append((_('Events'), str(len(segment.trace.events))))
            return word, ok and segment.trace is not None, rows

        try:
            return await run_with_progress(self, box, sim.run_segment(runner, session, on_data=progress), verdict)
        except sim.SimulationError as exc:
            await self.run_dialog(information(_('Simulate Flow'), str(exc)))  # type: ignore[attr-defined]
            return None

    async def _segment_failed(self, session: sim.Session, segment: sim.Segment | None) -> None:
        if segment is None:
            return
        word = VERDICTS.get(segment.state, (segment.state, False))[0]
        lines = [_('Segment {n}: {state} (exit code {code}).').format(n=segment.number, state=word, code=segment.exit_code)]
        if segment.problem:
            lines.append(segment.problem)
        if segment.stderr.strip() and segment.stderr.strip() != (segment.problem or "").strip():
            lines += ["", segment.stderr.strip()[-1500:]]
        await self.run_dialog(information(_('Simulate Flow'), "\n".join(lines)))  # type: ignore[attr-defined]

    def _say_segment(self, session: sim.Session, segment: sim.Segment) -> None:
        word, ok = VERDICTS.get(segment.state, (segment.state, False))
        hint = _(' · Ctrl+F9 resumes it') if segment.state == "paused" else ""
        self.notify(_('Simulation of {name}, segment {n}: {state}{hint}').format(  # type: ignore[attr-defined]
            name=session.flow.name, n=segment.number, state=word, hint=hint), timeout=4, severity="information" if ok else "error")

    def show_simulation_context(self, win: SimulationWindow) -> None:
        """X in the Simulation window: the context at the event, in the Output window (read-only)."""
        from divide.ui.windows import OutputWindow
        output = self.output_window()  # type: ignore[attr-defined]
        if output is None:
            output = OutputWindow(number=self._free_number())  # type: ignore[attr-defined]
            self.insert_window(output)  # type: ignore[attr-defined]
        output.show(win.session.flow, win.context_text(), _('simulated context · event {n}').format(n=win.playback.cursor + 1))
        self.raise_window(output)  # type: ignore[attr-defined]
