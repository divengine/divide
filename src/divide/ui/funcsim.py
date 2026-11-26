"""Function Mock Simulation: one Runner Function run with declared dependency doubles, replayed line by line.

**MOCK SIMULATION: real PHP runs.** The Function's own PHP code runs, in a PHP process of its own
(:mod:`divide.run.funcsim`); only what it asks its context for is replaced: other Functions
(``$context['_importer']``), Runner's logger and service objects under context keys. PHP's own
functions (files, PDO, curl, ``mail``, ``time()``) and the file's top-level code run for real. It is
not a sandbox and never side-effect-free, and it is not the Flow simulation (Shift+F9,
:mod:`divide.ui.simulate`), where Runner simulates the Flow and no Function code runs.

From the Functions window (Alt+F10 > Simulate...), the Flow Designer (Shift+T on a Step), the Step
dialog (Function... > Simulate...) or Run > Mock Simulation of a Function. Test Function (Ctrl+F9,
T) stays the real Run / Debug.

The **dialog** holds a ``divide.function-simulation`` v1 scenario: the context, the doubles
(pre-filled from a static scan of the file, :mod:`divide.run.funcscan`), the expectations, the
limits and the options; the scenario is refused before anything runs when it is wrong or a
dependency the scan found has no double. A scenario is shown as **pinned** only when it holds the
file's sha256; a pinned scenario whose file changed is **stale** and is re-pinned only by an explicit
Re-pin. The project's opt-in is asked once, in the user's settings.

The **playback window** shows the Function's file, read-only, with the line about to run marked in
the gutter, and the state before it in the panel (the locals, the context so far, the doubles'
calls, the output, the result). Moving only moves a cursor: nothing runs again. Keys: F7 / Shift+F7
the next / previous line, F8 / Shift+F8 the next / previous at the same depth (over a closure's
lines), F4 the next event on the cursor's line, Ctrl+Home / Ctrl+End the first / last, X the full
context in Output, S save as scenario.
"""

from __future__ import annotations

from divide.i18n import _

import json
import shutil
import textwrap
from pathlib import Path
from types import SimpleNamespace

from rich.style import Style
from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.cluster import CheckBoxes
from textual_vision.constants import Command
from textual_vision.input_line import InputLine
from textual_vision.label import Label

from divide import config, themes
from divide.run import flowmodel as fm
from divide.run import funcscan
from divide.run import funcsim as fs
from divide.run import functest as ft
from divide.run import functrace as ftr
from divide.ui.dialogs import MessageBox, _Dialog, confirm, information
from divide.ui.history import HistoryInput
from divide.ui.progress import ProgressDialog, run_with_progress
from divide.ui.windows import EditorView, HRule, IndicatorFrame, VRule, _TVWindow

CM_FS_EDIT = Command.USER + 240
CM_FS_SAVE = Command.USER + 241
CM_FS_REPIN = Command.USER + 242
CM_FS_REPLAY = Command.USER + 243
CM_FS_ALLOW = Command.YES
CM_FS_UNTRACED = Command.YES
CM_FS_KEEP_NULL = Command.USER + 247

NOT_SANDBOX = _('Not a sandbox, not a Flow simulation: files, network, databases are real.')
STATUS_WORDS = {
    "returned": _('Returned'), "exception": _('Exception'), "fatal": _('Fatal error'), "exit": _('exit() called'),
    "stale": _('Stale: the file changed'), "missing": _('No such Function file'), "timeout": _('Time limit'),
    "line_limit": _('Line limit'), "stopped": _('Stopped'), "crashed": _('PHP ended'), "protocol": _('No result'),
}
OPTIONS = ("trace", "pin", "tripwire", "autoload")  # the dialog's check boxes, in order


def _json(value, limit: int = 400) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
    return text if len(text) <= limit else text[:limit - 1] + "~"


def _short(sha: str | None) -> str:
    return sha[:8] if sha else "-"


def _style(token: str):
    return themes.current().token_styles().get(token)


def pin_state(scenario: dict, file: Path | None) -> tuple[str, str]:
    """(state, words): ``pinned``, ``stale``, ``unpinned``. Pinned only when the scenario holds a sha256."""
    sha = (scenario.get("function") or {}).get("sha256")
    if not sha:
        return "unpinned", _('NOT pinned to a source version: it runs whatever the file is now')
    current = fs.sha256(file) if file is not None and file.is_file() else None
    if current is not None and current != sha:
        return "stale", _('STALE: the file changed since the pin ({sha}): Re-pin to run it').format(sha=_short(sha))
    return "pinned", _('pinned to the file\'s version {sha}').format(sha=_short(sha))


# ---------------------------------------------------------------- what the user typed last
def _last_key(project: Path, module: str | None, name: str) -> str:
    return f"{project}|{module or ''}:{name}"


PREFERENCES = ("name", "trace", "tripwire")  # what the user's settings keep: never a context or a double


def _preferences(entry) -> dict:
    if not isinstance(entry, dict):
        return {}
    kept = {key: entry[key] for key in PREFERENCES if key in entry}
    if not isinstance(kept.get("name", ""), str):
        kept.pop("name")
    return {key: value for key, value in kept.items() if key == "name" or isinstance(value, bool)}


def last_input(project: Path, module: str | None, name: str) -> dict:
    """The options last used for a Function and the name of its scenario (the scenario itself is in the
    project, if it was saved)."""
    saved = config.load().get("function_simulations")
    return _preferences(saved.get(_last_key(project, module, name)) if isinstance(saved, dict) else None)


def remember_input(project: Path, module: str | None, name: str, entry: dict) -> None:
    """The options and the scenario's name, in the user's own settings (never in the project). The context
    and the doubles are never kept there; an older entry that held them is cut down to its preferences."""
    settings = config.load()
    saved = settings.get("function_simulations") if isinstance(settings.get("function_simulations"), dict) else {}
    saved = {key: _preferences(value) for key, value in saved.items()}
    saved[_last_key(project, module, name)] = _preferences(entry)
    settings["function_simulations"] = saved
    config.save(settings)


def last_run(project: Path, qualified: str) -> Path | None:
    """The newest traced run of the Function kept in the project's cache, or None."""
    for folder in ftr.runs(project):
        try:
            meta = json.loads((folder / ftr.META).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if isinstance(meta, dict) and meta.get("function") == qualified and (folder / ftr.TRACE_FILE).is_file():
            return folder
    return None


# ---------------------------------------------------------------- the dialog
class FunctionSimulationDialog(_Dialog):
    """A Mock Simulation's scenario; Simulate."""

    DEFAULT_CSS = """
    FunctionSimulationDialog { width: 78; height: 22; }
    FunctionSimulationDialog InputLine { width: 1fr; }
    FunctionSimulationDialog .fs-about { height: 2; color: $text; background: $surface; }
    FunctionSimulationDialog .fs-banner { height: auto; }
    FunctionSimulationDialog .fs-row { height: 1; }
    FunctionSimulationDialog .fs-half { width: 1fr; height: 2; }
    FunctionSimulationDialog .fs-pair { height: 2; }
    FunctionSimulationDialog .fs-limit { width: 10; }
    FunctionSimulationDialog .fs-row Label { width: auto; padding: 0 1 0 0; }
    FunctionSimulationDialog CheckBoxes { height: 2; width: 1fr; }
    FunctionSimulationDialog .fs-status { height: 1; color: $text; background: $surface; }
    """

    def __init__(self, project: Path, module: str | None, name: str, file: Path, *, last: dict,
                 scenarios: dict[str, Path], replay: Path | None = None) -> None:
        super().__init__(title=_('Mock Simulation of {name}').format(name=f"{module}:{name}" if module else name))
        banner = sum(len(textwrap.wrap(part, 72)) or 1 for part in (fs.LABEL, NOT_SANDBOX))
        self.styles.height = 20 + banner  # the banner whole, in every language
        self.project, self.module, self.func_name, self.file = project, module, name, file
        self.scenarios = scenarios
        self.scan = funcscan.scan_file(file)
        self.last_replay = replay
        last_name = str(last.get("name") or "") if last else ""
        scenario = None
        if last_name in scenarios:  # the scenario last used, from the project (the settings keep only its name)
            try:
                scenario = fs.load_scenario(scenarios[last_name])
            except fs.SimulationError:
                scenario = None
        # the names whose double the scan put in and that answer null: simulated only once the user confirms
        self.scanned: set[str] = set()
        self.nulls_ok: set[str] = set()
        self._asking = False
        if scenario is None:
            scenario = fs.new_scenario(module, name, file)  # a new one is pinned to the file as it is
            scenario["doubles"] = self.scan.doubles()
            self.scanned = set(self.scan.missing({}))
        self.scenario: dict = scenario
        self.scenario_input = InputLine(max_len=64)
        self.scenario_input.data = last_name
        self.context_input = InputLine(max_len=65536)
        self.doubles_input = InputLine(max_len=65536)
        self.return_input = InputLine(max_len=8192)
        self.expected_input = InputLine(max_len=65536)
        self.lines_input = InputLine(max_len=6)
        self.seconds_input = InputLine(max_len=3)
        self.stdout_input = InputLine(max_len=7)
        self.options = CheckBoxes([_('~T~race the PHP lines (Xdebug)'), _('~P~in to the file\'s version'),
                                   _('Trip~w~ire (not a sandbox)'), _('Composer ~a~utoload (real classes)')], columns=2)
        trace = last.get("trace", True) if last else True
        tripwire = last.get("tripwire", False) if last else False
        self._options = {"trace": bool(trace), "tripwire": bool(tripwire)}
        self.about = Static("", classes="fs-about", markup=False)
        self.status = Static("", classes="fs-status", markup=False)
        self.trace = bool(trace)
        self.tripwire = bool(tripwire)
        self.replay = False  # Replay chosen: the last traced run opens, nothing runs
        self._loaded = self.scenario_input.data.strip()  # the saved scenario the fields came from
        self._fill(scenario)

    # ------------------------------------------------------------ the fields <-> the scenario
    def _fill(self, scenario: dict) -> None:
        self.scenario = scenario
        expect = scenario.get("expect") or {}
        limits = scenario.get("limits") or {}
        self.context_input.data = json.dumps(scenario.get("context") or {}, ensure_ascii=False)
        self.doubles_input.data = json.dumps(scenario.get("doubles") or {}, ensure_ascii=False)
        self.return_input.data = json.dumps(expect["returns"], ensure_ascii=False) if "returns" in expect else ""
        self.expected_input.data = json.dumps(expect["context"], ensure_ascii=False) if "context" in expect else ""
        self.lines_input.data = str(limits.get("lines", fs.LIMITS["lines"][0]))
        self.seconds_input.data = str(limits.get("seconds", fs.LIMITS["seconds"][0]))
        self.stdout_input.data = str(limits.get("stdout", fs.LIMITS["stdout"][0]))
        self.pin_sha: str | None = (scenario.get("function") or {}).get("sha256")
        self.options.value = self._bits()

    def _bits(self) -> int:
        on = {"trace": self._options["trace"], "pin": bool(self.pin_sha), "tripwire": self._options["tripwire"],
              "autoload": bool(self.scenario.get("autoload"))}
        return sum(1 << i for i, key in enumerate(OPTIONS) if on[key])

    def _checked(self, key: str) -> bool:
        return bool(self.options.value & (1 << OPTIONS.index(key)))

    def build(self) -> tuple[dict | None, list[str]]:
        """The scenario the fields say, and what is wrong with it."""
        problems: list[str] = []

        def parsed(text: str, what: str, default):
            text = text.strip()
            if not text:
                return default
            try:
                return json.loads(text)
            except ValueError as exc:
                problems.append(_('{what} is not JSON: {why}').format(what=what, why=exc))
                return default

        scenario = json.loads(json.dumps(self.scenario))  # what Edit... or a saved scenario gave, the fields over it
        scenario["context"] = parsed(self.context_input.data, _('The context'), {})
        scenario["doubles"] = parsed(self.doubles_input.data, _('The doubles'), {})
        expect = {}
        if self.return_input.data.strip():
            expect["returns"] = parsed(self.return_input.data, _('The expected return'), None)
        if self.expected_input.data.strip():
            expect["context"] = parsed(self.expected_input.data, _('The expected context'), {})
        scenario["expect"] = expect
        limits = {}
        for key, field in (("lines", self.lines_input), ("seconds", self.seconds_input), ("stdout", self.stdout_input)):
            try:
                limits[key] = int(field.data.strip() or fs.LIMITS[key][0])
            except ValueError:
                problems.append(_('limits.{key}: 1..{top}').format(key=key, top=fs.LIMITS[key][1]))
        scenario["limits"] = limits
        scenario["autoload"] = self._checked("autoload")
        func = dict(scenario.get("function") or {})
        func.update({"module": self.module, "name": self.func_name})
        func.pop("sha256", None)
        if self.pin_sha:
            func["sha256"] = self.pin_sha
        scenario["function"] = func
        if problems:
            return None, problems
        problems = fs.check_scenario(scenario)
        if not problems and (missing := self.scan.missing(scenario["doubles"])):
            problems.append(_('No double for {names}: the Function calls it (Edit... or the doubles field)').format(
                names=", ".join(missing[:6]) + (" ..." if len(missing) > 6 else "")))
        return (scenario if not problems else None), problems

    def placeholders(self, doubles: dict) -> list[str]:
        """The doubles the scan put in that still answer null and were not confirmed."""
        found = []
        for key, value in (doubles.get("importer") or {}).items():
            if key in self.scanned and key not in self.nulls_ok and value == funcscan.PLACEHOLDER:
                found.append(key)
        for service, methods in (doubles.get("services") or {}).items():
            for method, value in (methods.items() if isinstance(methods, dict) else ()):
                key = f"{service}->{method}"
                if key in self.scanned and key not in self.nulls_ok and value == funcscan.PLACEHOLDER:
                    found.append(key)
        return found

    async def confirm_nulls(self, names: list[str], *, saving: bool) -> bool:
        """Null is a valid answer, but one the user says: a scanned double is never null by default."""
        box = MessageBox(_('Mock Simulation'), _('These doubles come from the scan and answer null: {names}. Null is a '
                                                 'valid answer when you mean it. Keep null for them, or go back and give '
                                                 'them a value?').format(names=", ".join(names[:8]) + (" ..." if len(names) > 8 else "")),
                         [(_('~K~eep null and save') if saving else _('~K~eep null and simulate'), CM_FS_KEEP_NULL, "keep-null"),
                          (_('~B~ack'), Command.CANCEL, "back")], width=66)
        if await self.app.run_dialog(box) != CM_FS_KEEP_NULL:  # type: ignore[attr-defined]
            self.status.update(_('Not run: give the doubles a value, or keep null when asked'))
            return False
        self.nulls_ok.update(names)
        self.show_state()
        return True

    async def _simulate_after_nulls(self, names: list[str]) -> None:
        try:
            confirmed = await self.confirm_nulls(names, saving=False)
        finally:
            self._asking = False
        if confirmed:
            self.end_modal(Command.OK)

    # ------------------------------------------------------------ layout
    def compose_content(self) -> ComposeResult:
        yield self.about
        yield Static(Text(fs.LABEL + "\n" + NOT_SANDBOX, style=_style("diag.warning")), classes="fs-banner")
        yield Label(_('~S~cenario (Save keeps it in .div/function-simulations/)'), link=self.scenario_input)
        yield HistoryInput(self.scenario_input, "function-simulation-scenario", offer=lambda: sorted(self.scenarios))
        yield Label(_('C~o~ntext: a JSON object (Edit... the whole scenario as a tree or JSON)'), link=self.context_input)
        yield self.context_input
        yield Label(_('~D~oubles: importer, services (--simulate outcomes); the rest fails'), link=self.doubles_input)
        yield self.doubles_input
        with Horizontal(classes="fs-pair"):
            with Vertical(classes="fs-half"):
                yield Label(_('Expected ret~u~rn (JSON)'), link=self.return_input)
                yield self.return_input
            with Vertical(classes="fs-half"):
                yield Label(_('Expected conte~x~t keys (JSON)'), link=self.expected_input)
                yield self.expected_input
        with Horizontal(classes="fs-row"):
            yield Label(_('~L~ines'), link=self.lines_input)
            yield self.lines_input
            yield Label(_(' Seconds'), link=self.seconds_input)
            yield self.seconds_input
            yield Label(_(' Output bytes'), link=self.stdout_input)
            yield self.stdout_input
        yield self.options
        yield self.status
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('Si~m~ulate'), Command.OK, is_default=True, id="simulate")
            yield Button(_('~E~dit...'), CM_FS_EDIT, id="edit")
            yield Button(_('Sa~v~e'), CM_FS_SAVE, id="save")
            # one place: Re-pin while the scenario is stale, else Replay (the last traced run, nothing run)
            yield Button(_('~R~e-pin'), CM_FS_REPIN, id="repin")
            yield Button(_('Repla~y~'), CM_FS_REPLAY, id="replay", disabled=self.last_replay is None)
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        for field in (self.lines_input, self.seconds_input, self.stdout_input):
            field.add_class("fs-limit")
        self.show_state()
        self.call_after_refresh(lambda: (self.context_input.tv_select_self(), self.context_input.select_all()))

    def show_state(self) -> None:
        """The about line (the file, the pin) and the status line (the doubles against the scan)."""
        shown = fm._shown(self.file, self.project)
        state, words = pin_state({"function": {"sha256": self.pin_sha}}, self.file)
        about = Text(shown + "\n")
        about.append(words, style=_style("diag.error") if state == "stale" else _style("diag.warning") if state == "unpinned" else None)
        self.about.update(about)
        try:
            repin, replay = self.query_one("#repin", Button), self.query_one("#replay", Button)
        except Exception:  # (not composed yet)
            repin = replay = None
        if repin is not None and replay is not None:
            repin.display, replay.display = state == "stale", state != "stale"
        _scenario, problems = self.build()
        if problems:
            line = problems[0]
        else:
            doubles = json.loads(self.doubles_input.data or "{}")
            placeholders = self.placeholders(doubles)
            if placeholders:
                line = _('From the scan, answering null until you say: {names}').format(names=", ".join(placeholders[:5]))
            elif self.scan.dynamic:
                line = _('Line {lines}: an import computed at run time; double it by its name').format(
                    lines=", ".join(map(str, self.scan.dynamic[:3])))
            else:
                line = _('Ready: every dependency the scan found has a double.')
        self.status.update(line)

    # ------------------------------------------------------------ events
    def on_input_line_changed(self, event) -> None:
        name = self.scenario_input.data.strip()  # another saved scenario chosen: its fields
        if name != self._loaded and name in self.scenarios:
            self._loaded = name
            try:
                self._fill(fs.load_scenario(self.scenarios[name]))
            except fs.SimulationError as exc:
                self.status.update(str(exc))
                return
            self.scanned = set()  # a saved scenario's nulls are what was saved: intended
        self.show_state()

    def on_cluster_changed(self, message) -> None:
        message.stop()
        self._options["trace"] = self._checked("trace")
        self._options["tripwire"] = self._checked("tripwire")
        self.scenario["autoload"] = self._checked("autoload")
        if self._checked("pin") and not self.pin_sha:
            self.pin_sha = fs.sha256(self.file) if self.file.is_file() else None  # pinned: a visible choice
        elif not self._checked("pin"):
            self.pin_sha = None  # the pin removed: a visible choice too
        self.show_state()

    def on_command_message(self, message) -> None:
        handlers = {CM_FS_EDIT: self._edit, CM_FS_SAVE: self._save}
        if message.command in handlers:
            message.stop()
            message.prevent_default()
            self.run_worker(handlers[message.command](), exclusive=True)
        elif message.command == CM_FS_REPIN:
            message.stop()
            message.prevent_default()
            self.repin()
        elif message.command == CM_FS_REPLAY:
            message.stop()
            message.prevent_default()
            if self.last_replay is not None:
                self.replay = True
                super().end_modal(Command.OK)

    def repin(self) -> None:
        """Re-pin: the scenario fixed to the file as it is now (only ever on this explicit choice)."""
        if not self.file.is_file():
            return
        state, _words = pin_state({"function": {"sha256": self.pin_sha}}, self.file)
        if state != "stale":
            return
        self.pin_sha = fs.sha256(self.file)
        self.options.value = self._bits()
        saved = self.scenario_input.data.strip() in self.scenarios
        self.app.notify(_('Re-pinned to {sha}') .format(sha=_short(self.pin_sha))
                        + (_(': Save writes it in the saved scenario') if saved else ""), timeout=4)
        self.show_state()

    async def _edit(self) -> None:
        """The whole scenario as a tree or JSON (the Step dialog's context editor), back in the fields."""
        from divide.ui.flowcontext import ContextDialog
        scenario, problems = self.build()
        if scenario is None:
            scenario = json.loads(json.dumps(self.scenario))
        dialog = ContextDialog(_('Scenario'), scenario)
        if await self.app.run_dialog(dialog) != Command.OK or dialog.result is None:  # type: ignore[attr-defined]
            return
        if problems := fs.check_scenario(dialog.result):
            self.app.notify(problems[0], severity="error", timeout=6)
            return
        func = dialog.result.get("function") or {}
        if (func.get("module") or None) != self.module or str(func.get("name", "")).strip() != self.func_name:
            self.app.notify(_('The scenario is for {name}: its function stays').format(name=self.title), severity="error", timeout=5)
            return
        self._fill(dialog.result)
        self.show_state()

    async def _save(self) -> None:
        name = self.scenario_input.data.strip()
        if problem := fs.scenario_problem(name):
            self.app.notify(problem, severity="error", timeout=5)
            return
        scenario, problems = self.build()
        if scenario is None:
            self.app.notify(problems[0], severity="error", timeout=6)
            return
        if (names := self.placeholders(scenario["doubles"])) and not await self.confirm_nulls(names, saving=True):
            return
        path = fs.scenario_file(self.project, self.module, self.func_name, name)
        if name in self.scenarios and await self.app.run_dialog(confirm(  # type: ignore[attr-defined]
                _('Save scenario'), _('Replace the scenario {name} in {path}?').format(name=name, path=fm._shown(path, self.project)))) != Command.YES:
            return
        try:
            path = fs.save_scenario(self.project, name, scenario)
        except (fs.SimulationError, OSError) as exc:
            self.app.notify(str(exc), severity="error", timeout=6)
            return
        self.scenarios[name] = path
        self.scenario = scenario
        self.app.notify(_('Saved in {path}').format(path=fm._shown(path, self.project)), timeout=3)

    def valid(self, command: Command) -> bool:
        if command != Command.OK or self.replay:
            return True
        scenario, problems = self.build()
        if scenario is None:
            self.app.notify(problems[0], severity="error", timeout=6)
            self.status.update(problems[0])
            return False
        if names := self.placeholders(scenario["doubles"]):  # asked first; simulated once confirmed
            if not self._asking:  # (valid() is called twice per end_modal: one question)
                self._asking = True
                self.run_worker(self._simulate_after_nulls(names), exclusive=True)
            return False
        self.scenario = scenario
        self.trace = self._checked("trace")
        self.tripwire = self._checked("tripwire")
        return True

    def entry(self) -> dict:
        """What the user's settings keep: the options and the scenario's name, never its context or doubles."""
        return {"name": self.scenario_input.data.strip(), "trace": self.trace, "tripwire": self.tripwire}


class SaveScenarioDialog(_Dialog):
    """Save as scenario: a name, and whether to expect what this run did."""

    DEFAULT_CSS = """
    SaveScenarioDialog { width: 64; height: 11; }
    SaveScenarioDialog InputLine { width: 1fr; }
    SaveScenarioDialog CheckBoxes { height: 1; width: 1fr; margin-top: 1; }
    """

    def __init__(self, names: list[str], *, returned: bool) -> None:
        super().__init__(title=_('Save as scenario'))
        self.names = names
        self.name_input = InputLine(max_len=64)
        self.options = CheckBoxes([_('~E~xpect this run\'s return and context changes') if returned
                                   else _('~E~xpect this run\'s context changes')])
        self.chosen = ""
        self.expect = False

    def compose_content(self) -> ComposeResult:
        yield Label(_('~N~ame (.div/function-simulations/, for the team in Git)'), link=self.name_input)
        yield HistoryInput(self.name_input, "function-simulation-scenario", offer=lambda: sorted(self.names))
        yield self.options
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('O~K~'), Command.OK, is_default=True, id="ok")
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        name = self.name_input.data.strip()
        if problem := fs.scenario_problem(name):
            self.app.notify(problem, severity="error", timeout=5)
            return False
        self.chosen, self.expect = name, bool(self.options.value & 1)
        return True


# ---------------------------------------------------------------- the playback window
class FunctionPlaybackWindow(_TVWindow):
    """A Mock Simulation replayed: the Function's file, read-only, the line about to run marked; the
    state before it in the panel. Moving through the lines only moves a cursor."""

    HINT = _('MOCK SIMULATION · F7/F8 line/same depth · Shift back · F4 cursor line · ^Home/^End · X context · S save')
    DEFAULT_CSS = """
    FunctionPlaybackWindow .fp-main { height: 1fr; }
    FunctionPlaybackWindow .fp-code { width: 1fr; height: 1fr; }
    FunctionPlaybackWindow .fp-right { width: 46; height: 1fr; }
    FunctionPlaybackWindow .fp-bar { height: auto; padding: 0 1; background: $window-content-background; color: $foreground; }
    FunctionPlaybackWindow .fp-info { height: auto; padding: 0 1; background: $window-content-background; color: $foreground; }
    FunctionPlaybackWindow .fp-result { height: auto; max-height: 8; padding: 0 1; background: $window-content-background; color: $foreground; }
    FunctionPlaybackWindow VerticalScroll { background: $window-content-background; scrollbar-size: 1 1; }
    FunctionPlaybackWindow .fp-hrule { display: none; }
    FunctionPlaybackWindow.narrow .fp-main { layout: vertical; }
    FunctionPlaybackWindow.narrow .fp-right { width: 1fr; height: 12; }
    FunctionPlaybackWindow.narrow .fp-result, FunctionPlaybackWindow.narrow .fp-result-rule { display: none; }
    FunctionPlaybackWindow.narrow VRule { display: none; }
    FunctionPlaybackWindow.narrow .fp-hrule { display: block; }
    """

    def __init__(self, project: Path, trace: ftr.FunctionTrace, scenario: dict, *, folder: Path | None = None,
                 traced: bool = True, number: int = 0) -> None:
        self.project, self.trace, self.scenario, self.folder, self.traced = project, trace, scenario, folder, traced
        func = trace.function
        self.qualified = f"{func.get('module')}:{func.get('name')}" if func.get("module") else str(func.get("name") or "?")
        super().__init__(_('Mock Simulation: {name}').format(name=self.qualified), number=number)
        where = func.get("file")
        self.file = (project / where) if isinstance(where, str) and not Path(where).is_absolute() else (Path(where) if where else None)
        try:
            text = self.file.read_text(encoding="utf-8") if self.file is not None else ""
        except (OSError, UnicodeDecodeError):
            text = ""
        current = fs.sha256(self.file) if self.file is not None and self.file.is_file() else None
        self.changed = current is None or current != func.get("sha256")  # the file now is not the one that ran
        self.code = EditorView(text, read_only=True, path=self.file)
        self.code.add_class("fp-code")
        self.bar = Static("", classes="fp-bar")
        self.info = Static("", classes="fp-info")
        self.verdict = Static("", classes="fp-result")
        self.playback = ftr.LinePlayback(trace)
        self.view: ftr.LineView | None = None

    def compose_content(self) -> ComposeResult:
        with Horizontal(classes="fp-main"):
            yield self.code
            yield VRule()
            yield HRule(classes="fp-hrule")
            with Vertical(classes="fp-right"):
                yield self.bar
                yield HRule()
                with VerticalScroll():
                    yield self.info
                yield HRule(classes="fp-result-rule")
                yield self.verdict

    def on_mount(self) -> None:
        self.call_after_refresh(lambda: self.set_class(self.size.width < 100, "narrow"))
        self.call_after_refresh(self.refresh_view)
        self.call_after_refresh(self.code.focus)

    def on_resize(self, event: events.Resize) -> None:
        narrow = event.size.width < 100
        if narrow != self.has_class("narrow"):
            self.set_class(narrow, "narrow")
            self.refresh_view()  # the result moves into the panel's text (narrow) or below it

    def hint(self) -> str:
        return self.HINT

    # ------------------------------------------------------------ moving
    def on_key(self, event: events.Key) -> None:
        moves = {"f7": ("line", 1), "shift+f7": ("line", -1), "f8": ("depth", 1), "shift+f8": ("depth", -1),
                 "f4": ("cursor", 0), "ctrl+home": ("first", 0), "ctrl+end": ("last", 0), "x": ("context", 0),
                 "s": ("save", 0)}
        if event.key in moves:
            event.stop()
            event.prevent_default()
            self.playback_key(*moves[event.key])

    def playback_key(self, what: str, step: int) -> None:
        playback = self.playback
        if what == "line":
            playback.next(step)
        elif what == "depth":
            playback.next_same_depth(step)
        elif what == "first":
            playback.first()
        elif what == "last":
            playback.last()
        elif what == "cursor":
            if not self.goto_cursor_line():
                return
        elif what == "context":
            self.app.show_function_sim_context(self)  # type: ignore[attr-defined]
            return
        elif what == "save":
            self.app.save_function_sim_scenario(self)  # type: ignore[attr-defined]
            return
        self.refresh_view()

    def goto_cursor_line(self) -> bool:
        """F4: the next event on the cursor's line (after the current one, else the first)."""
        line = self.code.cursor_location[0] + 1
        events_ = self.playback.events
        order = list(range(self.playback.cursor + 1, len(events_))) + list(range(0, self.playback.cursor + 1))
        for i in order:
            if events_[i].get("line") == line and int(events_[i].get("depth") or 0) >= 0:
                return self.playback.go(i)
        self.app.notify(_('Line {line} did not run in this simulation').format(line=line), timeout=3)
        return False

    # ------------------------------------------------------------ painting
    def refresh_view(self) -> None:
        if not self.is_mounted:
            return
        self.view = self.playback.view()
        row = self.view.line - 1 if self.view is not None and not self.changed else None
        self.code.set_debug_marks(set(), row)
        if row is not None:
            self.code.move_cursor((row, 0))
            self.code.scroll_cursor_visible(center=True)
        self.show_bar()
        self.info.update(self.describe())
        self.show_result()
        frame = self.frame
        if isinstance(frame, IndicatorFrame):
            frame.set_indicator(_('line {n}/{total}').format(n=self.playback.cursor + 1, total=len(self.playback))
                                if len(self.playback) else _('no lines'))

    def pin_words(self) -> tuple[str, bool]:
        if not self.trace.pinned:
            return _('NOT pinned to a source version'), False
        return _('pinned {sha}').format(sha=_short(self.trace.function.get("sha256"))), True

    def show_bar(self) -> None:
        bar = Text()
        bar.append(_('MOCK SIMULATION') + " ", style=Style(bold=True))
        if len(self.playback):
            event = self.playback.event or {}
            bar.append(_('line {line} · event {n}/{total}').format(line=event.get("line"), n=self.playback.cursor + 1,
                                                                 total=len(self.playback)))
        else:
            bar.append(_('no PHP lines recorded'))
        bar.append("\n")
        bar.append(_('Real PHP ran; only the declared dependencies were replaced. Not a sandbox.') + "\n",
                   style=_style("diag.warning"))
        words, pinned = self.pin_words()
        bar.append(words, style=None if pinned else _style("diag.warning"))
        if self.trace.result.get("tripwire"):
            bar.append(" · " + _('tripwire on'))
        if self.changed:
            bar.append("\n" + _('The file changed since this run: its lines are not marked'), style=_style("diag.error"))
        self.bar.update(bar)

    def describe(self) -> Text:
        dim, key_style = _style("div.comment"), _style("json.key")
        text = Text()
        view = self.view
        result = self.trace.result
        if self.has_class("narrow"):  # no room below: the result first
            text.append_text(self.result_text())

        def head(words: str) -> None:
            text.append("\n" + words + "\n", style=dim)

        def pairs(values: dict, limit: int = 30) -> None:
            for name, value in list(values.items())[:limit]:
                text.append(f"  {name}", style=key_style)
                text.append(f" = {_json(value, 120)}\n")
            if len(values) > limit:
                text.append("  ...\n", style=dim)

        if view is None:
            if not self.traced:
                text.append(_('Run without the line trace: only its result is here.') + "\n")
            elif result.get("status") in ("stale", "missing"):
                text.append(_('The Function was not called.') + "\n")
            else:
                text.append(_('No line of the Function ran.') + "\n")
        else:
            event = view.event
            text.append(f"#{event.get('seq', '?')} ", style=dim)
            text.append(_('line {line}').format(line=view.line), style=key_style)
            text.append(" · " + _('depth {n}').format(n=view.depth) + (_(' (in a closure)') if view.depth else ""))
            if event.get("repeat"):
                text.append(" · " + _('{n} more statement(s) on it').format(n=event["repeat"]))
            text.append("\n")
            text.append(_('The state before the line runs.') + "\n", style=dim)
            changed = event.get("locals") or {}
            if isinstance(changed, dict) and (changed.get("set") or changed.get("unset")):
                head(_('Changed by the lines before'))
                pairs({k: v for k, v in (changed.get("set") or {}).items()})
                for name in changed.get("unset") or []:
                    text.append(f"  - {name}\n")
            after = event.get("after_call") or {}
            if isinstance(after, dict) and (after.get("set") or after.get("unset")):
                head(_('Changed by a double this line calls (after it)'))
                pairs(after.get("set") or {})
            head(_('Locals'))
            pairs(view.locals) if view.locals else text.append("  " + _('(none)') + "\n", style=dim)
            head(_('Context so far ({n} key(s)) · X shows it').format(n=len(view.context)))
            pairs(view.context, 12)
            if view.cut:
                text.append("  " + _('cut by the trace\'s bounds: {names}').format(names=", ".join(view.cut[:6])) + "\n", style=dim)
        calls = result.get("calls") or []
        head(_('Double calls ({n})').format(n=len(calls)))
        for call in calls[:30]:
            if isinstance(call, dict):
                text.append(f"  {call.get('double')} #{call.get('call')}: {call.get('outcome')} {_json(call.get('args'), 60)}\n")
        if not calls:
            text.append("  " + _('(none)') + "\n", style=dim)
        logs = result.get("logs") or []
        if logs:
            head(_('Logger ({n})').format(n=len(logs)))
            for log in logs[:20]:
                if isinstance(log, dict):
                    text.append(f"  {log.get('level')}: {log.get('message')}\n")
        output = str(result.get("stdout") or "")
        head(_('Output ({n} bytes{cut})').format(n=len(output.encode()), cut=_(', {n} cut').format(n=result.get("stdout_cut"))
                                                 if result.get("stdout_cut") else ""))
        text.append(("  " + output[:800].replace("\n", "\n  ").rstrip() + "\n") if output else "  " + _('(nothing)') + "\n")
        return text

    def checks(self) -> list[tuple[bool, str]]:
        result = self.trace.result
        shown = SimpleNamespace(ok=result.get("status") == "returned", returned=result.get("return"), after=result.get("after"))
        return ft.check(shown, fs.expectation(self.scenario))  # type: ignore[arg-type]

    def show_result(self) -> None:
        self.verdict.update(self.result_text())

    def result_text(self) -> Text:
        result = self.trace.result
        status = str(result.get("status") or "")
        bad = _style("diag.error")
        text = Text()
        text.append(STATUS_WORDS.get(status, status), style=Style(bold=True))
        if status == "returned":
            text.append(f" {_json(result.get('return'), 120)} ({result.get('return_type')})")
        text.append("\n")
        exc = result.get("exception") if isinstance(result.get("exception"), dict) else None
        if exc:
            where = f" · {Path(str(exc.get('file') or '')).name}:{exc.get('line')}" if exc.get("file") else ""
            text.append(f"{exc.get('class')}: {exc.get('message')}{where}\n", style=bad)
            if exc.get("missing_double"):
                text.append(_('A dependency with no double: add one to the scenario') + "\n", style=bad)
        error = result.get("error") if isinstance(result.get("error"), dict) else None
        if error:
            text.append(f"{error.get('message')} · {Path(str(error.get('file') or '')).name}:{error.get('line')}\n", style=bad)
        if result.get("message"):
            text.append(str(result.get("message")) + "\n", style=bad if status != "returned" else None)
        if self.trace.truncated:
            text.append(_('The trace stopped at limits.lines: the run did not finish') + "\n", style=bad)
        for ok, words in self.checks():
            text.append(("[OK] " if ok else "[!!] ") + words + "\n", style=None if ok else bad)
        return text

    def context_text(self) -> str:
        view = self.view
        head = [fs.LABEL, NOT_SANDBOX, ""]
        if view is None:
            after = self.trace.result.get("after")
            head.append(_('The context after the run (no PHP lines recorded).'))
            return "\n".join(head) + "\n\n" + json.dumps(after, indent=2, ensure_ascii=False) + "\n"
        head.append(_('The context before line {line} ran (event {n} of {total}), rebuilt from the trace{cut}.').format(
            line=view.line, n=self.playback.cursor + 1, total=len(self.playback),
            cut=_('; values marked $type were cut by its bounds') if view.cut else ""))
        return "\n".join(head) + "\n\n" + json.dumps(view.context, indent=2, ensure_ascii=False) + "\n"

    def scenario_to_save(self, expect: bool) -> dict:
        """The scenario that ran; with ``expect``, what it returned and the context keys it changed."""
        scenario = json.loads(json.dumps(self.scenario))
        if expect:
            result = self.trace.result
            before = result.get("before") if isinstance(result.get("before"), dict) else {}
            after = result.get("after") if isinstance(result.get("after"), dict) else {}
            wanted: dict = {}
            if result.get("status") == "returned":
                wanted["returns"] = result.get("return")
            changes = {k: v for k, v in after.items() if not str(k).startswith("_") and (k not in before or before[k] != v)}
            if changes:
                wanted["context"] = changes
            scenario["expect"] = wanted
        return scenario


# ---------------------------------------------------------------- the app's part
class FunctionSimulationMixin:
    """Function Mock Simulations (mixed into the Divide app)."""

    def function_playback_windows(self) -> list[FunctionPlaybackWindow]:
        return [w for w in self.windows() if isinstance(w, FunctionPlaybackWindow)]  # type: ignore[attr-defined]

    def wants_function_playback(self) -> bool:
        return isinstance(self.active_window(), FunctionPlaybackWindow)  # type: ignore[attr-defined]

    async def function_simulate_command(self) -> None:
        """Run > Mock Simulation of a Function: the Function under the cursor in the Functions window,
        else the active PHP file when it is one of the project's Functions."""
        from divide.run import flowfunctions as ff
        from divide.ui.flowfunctions import FunctionsWindow
        title = _('Mock Simulation')
        win = self.active_window()  # type: ignore[attr-defined]
        if isinstance(win, FunctionsWindow) and win.catalog is not None:
            row = win.selected()
            entry = win.catalog.entry(row.module, row.name) if row is not None and row.kind in ("function", "ref") else None
            if entry is not None:
                await self.simulate_function(win.source, entry.module, entry.name)
                return
        editor = self.active_editor()  # type: ignore[attr-defined]
        if editor is not None and editor.path is not None and editor.editor.lang == "php":
            catalog = ff.catalog(self.root, self.flow_functions(None), flows=[])  # type: ignore[attr-defined]
            for entry in catalog.root_functions + [f for m in catalog.modules for f in m.functions]:
                if ff._key(entry.path) == ff._key(editor.path):
                    await self.simulate_function(None, entry.module, entry.name)
                    return
        await self.run_dialog(information(title, _(  # type: ignore[attr-defined]
            'Choose a Function: in the Functions window (Run > Flow functions), on a Step of the Flow '
            'Designer (Shift+T), or open its PHP file.')))

    def flow_simulate_function(self, source, module: str | None, name: str) -> None:
        self._flow_simulate_function(source, module, name)

    @work(group="funcsim", exclusive=True)
    async def _flow_simulate_function(self, source, module, name) -> None:
        await self.simulate_function(source, module, name)

    async def simulate_function(self, source, module: str | None, name: str) -> None:
        """The Mock Simulation dialog for ``module:name`` as ``source``'s Flow resolves it, then the run
        and its playback."""
        title = _('Mock Simulation')
        project = self.root  # type: ignore[attr-defined]
        if self.debugging:  # type: ignore[attr-defined]
            await self.run_dialog(information(title, _('A program is being debugged: Ctrl+F2 ends it first.')))  # type: ignore[attr-defined]
            return
        if not shutil.which("php"):
            await self.run_dialog(information(title, _('php was not found in the PATH.')))  # type: ignore[attr-defined]
            return
        functions = self.flow_functions(source)  # type: ignore[attr-defined]
        if module and (problem := fm.module_problem(module, name)):
            await self.run_dialog(information(title, problem))  # type: ignore[attr-defined]
            return
        file = functions.find(name, module, project)
        qualified = f"{module}:{name}" if module else name
        if file is None:
            await self.run_dialog(information(title, _('{name}: no such Function file').format(name=qualified)))  # type: ignore[attr-defined]
            return
        file = file.resolve()
        for other in self.editor_windows():  # type: ignore[attr-defined]  # PHP runs what is on disk
            if other.dirty and other.path is not None and other.editor.lang == "php" and not await self.save(other):  # type: ignore[attr-defined]
                return
        dialog = FunctionSimulationDialog(project, module, name, file, last=last_input(project, module, name),
                                          scenarios=fs.list_scenarios(project, module, name),
                                          replay=last_run(project, qualified))
        if await self.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        if dialog.replay and dialog.last_replay is not None:
            self.open_function_run(dialog.last_replay)
            return
        if not fs.trusted(project):
            box = MessageBox(title, fs.TRUST_TEXT, [(_('~A~llow in this project'), CM_FS_ALLOW, "allow"),
                                                    (_('Cancel'), Command.CANCEL, "cancel")], width=66)
            if await self.run_dialog(box) != CM_FS_ALLOW:  # type: ignore[attr-defined]
                return
            fs.trust(project)
        remember_input(project, module, name, dialog.entry())  # only after the opt-in, and only the preferences
        trace = dialog.trace
        if trace:
            from divide.run.dbgp import xdebug_ini
            if await xdebug_ini(extension=config.load().get("xdebug")) is None:
                box = MessageBox(title, _('The line trace needs Xdebug, and this PHP has none (install it, or set its '
                                          'extension file in Options). Simulate without the line trace? Only the result '
                                          'is shown then, no lines; the PHP runs for real all the same.'),
                                 [(_('~W~ithout the line trace'), CM_FS_UNTRACED, "untraced"), (_('Cancel'), Command.CANCEL, "cancel")],
                                 width=66)
                if await self.run_dialog(box) != CM_FS_UNTRACED:  # type: ignore[attr-defined]
                    return
                trace = False
        scenario = dialog.scenario
        while True:
            request = fs.request_for(project, scenario, functions)
            sim = await self._run_function_sim(request, trace=trace, tripwire=dialog.tripwire)
            if sim is None:
                return
            if sim.status != "stale":
                break
            box = MessageBox(title, _('{name} changed since the scenario was pinned ({old}; the file is {new} now): it was '
                                      'not run. Re-pin the scenario to the file as it is and simulate it?').format(
                name=qualified, old=_short(scenario["function"].get("sha256")), new=_short(sim.sha256 or fs.sha256(file))),
                [(_('~R~e-pin and simulate'), Command.YES, "repin"), (_('Cancel'), Command.CANCEL, "cancel")], width=66)
            if await self.run_dialog(box) != Command.YES:  # type: ignore[attr-defined]
                return
            scenario = json.loads(json.dumps(scenario))
            scenario["function"]["sha256"] = fs.sha256(file)
        folder = None
        if trace:
            try:
                folder = ftr.save_run(sim, active={w.folder for w in self.function_playback_windows() if w.folder})
            except OSError as exc:
                self.notify(str(exc), severity="error", timeout=5)  # type: ignore[attr-defined]
        self.open_function_playback(project, ftr.parse_trace(ftr.document(sim)), scenario, folder=folder, traced=trace)

    async def _run_function_sim(self, request: fs.SimRequest, *, trace: bool, tripwire: bool) -> fs.Simulation | None:
        from divide.run.script import size_text
        box = ProgressDialog(_('Mock Simulation'), [
            (_('Function'), request.qualified),
            (_('Line trace'), _('yes (Xdebug)') if trace else _('no')),
            (_('Time limit'), f"{fs.limit(request.scenario, 'seconds')} s"),
            (_('Output'), size_text(b"")),
        ], width=60)

        def progress(out: bytes, err: bytes) -> None:
            box.set(_('Output'), size_text(out + err))

        def verdict(sim: fs.Simulation) -> tuple[str, bool, list[tuple[str, str]]]:
            rows = [(_('Exit code'), str(sim.exit_code))]
            if trace:
                rows.append((_('Lines'), str(len(sim.events)) + (_(' (cut)') if sim.truncated else "")))
            return STATUS_WORDS.get(sim.status, sim.status), sim.ok, rows

        xdebug = config.load().get("xdebug")
        try:
            return await run_with_progress(self, box, fs.simulate(request, tripwire=tripwire, trace=trace,
                                                                  xdebug=xdebug if isinstance(xdebug, str) else None,
                                                                  on_data=None if trace else progress), verdict)
        except fs.SimulationError as exc:
            await self.run_dialog(information(_('Mock Simulation'), str(exc)))  # type: ignore[attr-defined]
            return None

    def open_function_run(self, folder: Path) -> None:
        try:
            trace, scenario = ftr.load_run(folder)
        except fs.SimulationError as exc:
            self.notify(str(exc), severity="error", timeout=5)  # type: ignore[attr-defined]
            return
        self.open_function_playback(self.root, trace, scenario, folder=folder)  # type: ignore[attr-defined]

    def open_function_playback(self, project: Path, trace: ftr.FunctionTrace, scenario: dict, *,
                               folder: Path | None = None, traced: bool = True) -> FunctionPlaybackWindow:
        win = FunctionPlaybackWindow(project, trace, scenario, folder=folder, traced=traced, number=self._free_number())  # type: ignore[attr-defined]
        self._insert(win)  # type: ignore[attr-defined]
        word = STATUS_WORDS.get(trace.status, trace.status)
        self.notify(_('Mock Simulation of {name}: {state}').format(name=win.qualified, state=word),  # type: ignore[attr-defined]
                    timeout=4, severity="information" if trace.status == "returned" else "error")
        return win

    def show_function_sim_context(self, win: FunctionPlaybackWindow) -> None:
        """X in the playback window: the context before the line, in the Output window (read-only)."""
        from divide.ui.windows import OutputWindow
        output = self.output_window()  # type: ignore[attr-defined]
        if output is None:
            output = OutputWindow(number=self._free_number())  # type: ignore[attr-defined]
            self.insert_window(output)  # type: ignore[attr-defined]
        output.show(win.file or win.project, win.context_text(),
                    _('MOCK SIMULATION · context · event {n}').format(n=win.playback.cursor + 1))
        self.raise_window(output)  # type: ignore[attr-defined]

    def save_function_sim_scenario(self, win: FunctionPlaybackWindow) -> None:
        self._save_function_sim_scenario(win)

    @work(group="funcsim", exclusive=True)
    async def _save_function_sim_scenario(self, win: FunctionPlaybackWindow) -> None:
        func = win.trace.function
        module, name = func.get("module") or None, str(func.get("name") or "")
        if fs.check_scenario(win.scenario):
            self.notify(_('This run has no scenario to save'), severity="error", timeout=4)  # type: ignore[attr-defined]
            return
        saved = fs.list_scenarios(win.project, module, name)
        dialog = SaveScenarioDialog(sorted(saved), returned=win.trace.status == "returned")
        if await self.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        path = fs.scenario_file(win.project, module, name, dialog.chosen)
        if dialog.chosen in saved and await self.run_dialog(confirm(  # type: ignore[attr-defined]
                _('Save scenario'), _('Replace the scenario {name} in {path}?').format(name=dialog.chosen, path=fm._shown(path, win.project)))) != Command.YES:
            return
        try:
            path = fs.save_scenario(win.project, dialog.chosen, win.scenario_to_save(dialog.expect))
        except (fs.SimulationError, OSError) as exc:
            await self.run_dialog(information(_('Save as scenario'), str(exc)))  # type: ignore[attr-defined]
            return
        pinned = _('pinned to {sha}').format(sha=_short((win.scenario.get("function") or {}).get("sha256"))) if win.trace.pinned \
            else _('not pinned to a source version')
        self.notify(_('Saved in {path} ({pinned})').format(path=fm._shown(path, win.project), pinned=pinned), timeout=4)  # type: ignore[attr-defined]
