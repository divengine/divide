"""Test Function: one Runner Function run (or debugged) with a JSON context.

From the Functions window (Ctrl+F9 on a Function), the Flow Designer (T on a Step) or the Step
dialog (Function... > Test...). The dialog takes the context (typed, or as a tree or JSON with
Edit...), an optional named scenario (saved in the project only with Save), what the return and
the context after should hold, and a time limit. **Run** calls the Function in a PHP process of its
own (:mod:`divide.run.functest`) and shows the report in Output, a failure's place in Messages;
**Debug** runs the same call under the debugger (breakpoints, F7 / F8, watches), stopping at the
Function's first line when it has no breakpoint of its own.

The Function is the project's real PHP code: the dialog and the report say so.
"""

from __future__ import annotations

from divide.i18n import _

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.constants import Command
from textual_vision.input_line import InputLine
from textual_vision.label import Label

from divide import config, themes
from divide.run import flowmodel as fm
from divide.run import functest as ft
from divide.run.script import ScriptMessage, size_text
from divide.ui.dialogs import _Dialog, confirm, information
from divide.ui.history import HistoryInput
from divide.ui.progress import ProgressDialog, run_with_progress

CM_TEST_DEBUG = Command.USER + 224
CM_TEST_EDIT = Command.USER + 225
CM_TEST_SAVE = Command.USER + 226
WARNING = _('Runs the real PHP code of the project: it may write files, use a database or the network. '
            'Not a sandbox: only for code you trust.')


class FunctionTestDialog(_Dialog):
    """The input of a Function test; Run or Debug."""

    DEFAULT_CSS = """
    FunctionTestDialog { width: 78; height: 22; }
    FunctionTestDialog InputLine { width: 1fr; }
    FunctionTestDialog .ft-about { height: 1; color: $text; background: $surface; }
    FunctionTestDialog .ft-warning { height: 2; margin-top: 1; }
    """

    def __init__(self, request: ft.TestRequest, *, last: ft.Scenario, scenarios: dict[str, ft.Scenario],
                 timeout: float = ft.TIMEOUT) -> None:
        super().__init__(title=_('Test Function {name}').format(name=request.qualified))
        self.request = request
        self.scenarios = scenarios
        self.context_input = InputLine(max_len=65536)
        self.context_input.data = last.context
        self.scenario_input = InputLine(max_len=64)
        self.return_input = InputLine(max_len=8192)
        self.return_input.data = last.returned
        self.expected_input = InputLine(max_len=65536)
        self.expected_input.data = last.expected
        self.timeout_input = InputLine(max_len=8)
        self.timeout_input.data = f"{timeout:g}"
        self.choice = "run"
        self.context: dict = {}
        self.expect = ft.Expectation()
        self.timeout = timeout

    def compose_content(self) -> ComposeResult:
        where = fm._shown(self.request.expected, self.request.project) if self.request.expected else _('(Runner\'s importer decides)')
        yield Static(_('{name} · {path}').format(name=self.request.qualified, path=where), classes="ft-about", markup=False)
        yield Label(_('Con~t~ext: a JSON object, passed by reference (Edit... as a tree or JSON)'), link=self.context_input)
        yield self.context_input
        yield Label(_('~S~cenario (optional; Save keeps it in .div/function-tests/)'), link=self.scenario_input)
        yield HistoryInput(self.scenario_input, "function-test-scenario", offer=lambda: sorted(self.scenarios))
        yield Label(_('Expected ret~u~rn (JSON, optional)'), link=self.return_input)
        yield self.return_input
        yield Label(_('Expected conte~x~t after: keys it must hold (JSON object, optional)'), link=self.expected_input)
        yield self.expected_input
        yield Label(_('Time ~l~imit, seconds'), link=self.timeout_input)
        yield self.timeout_input
        yield Static(Text(WARNING, style=themes.current().token_styles()["diag.warning"]), classes="ft-warning")
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('~R~un'), Command.OK, is_default=True, id="run")
            yield Button(_('~D~ebug'), CM_TEST_DEBUG, id="debug")
            yield Button(_('~E~dit...'), CM_TEST_EDIT, id="edit")
            yield Button(_('Sa~v~e'), CM_TEST_SAVE, id="save")
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(lambda: (self.context_input.tv_select_self(), self.context_input.select_all()))

    def on_input_line_changed(self, event) -> None:
        name = self.scenario_input.data.strip()  # a saved scenario chosen: its input in the fields
        if name in self.scenarios:
            chosen = self.scenarios[name]
            if (self.context_input.data, self.return_input.data, self.expected_input.data) != (chosen.context, chosen.returned, chosen.expected):
                self.context_input.data, self.return_input.data, self.expected_input.data = chosen.context, chosen.returned, chosen.expected

    def on_command_message(self, message) -> None:
        if message.command == CM_TEST_DEBUG:
            message.stop()
            message.prevent_default()
            self.choice = "debug"
            if self.valid(Command.OK):
                super().end_modal(Command.OK)
            else:
                self.choice = "run"
        elif message.command == CM_TEST_EDIT:
            message.stop()
            message.prevent_default()
            self.run_worker(self._edit(), exclusive=True)
        elif message.command == CM_TEST_SAVE:
            message.stop()
            message.prevent_default()
            self.run_worker(self._save(), exclusive=True)

    def scenario(self) -> ft.Scenario:
        return ft.Scenario(self.context_input.data.strip(), self.return_input.data.strip(), self.expected_input.data.strip())

    async def _edit(self) -> None:
        """The context as a tree or as JSON (the Step dialog's context editor), back in the field."""
        from divide.ui.flowcontext import ContextDialog
        try:
            value = ft.parse_context(self.context_input.data)
        except ft.TestError as exc:
            self.app.notify(str(exc), severity="error", timeout=5)
            return
        dialog = ContextDialog(_('Context'), value)
        if await self.app.run_dialog(dialog) == Command.OK and dialog.result is not None:  # type: ignore[attr-defined]
            self.context_input.data = json.dumps(dialog.result, ensure_ascii=False)

    async def _save(self) -> None:
        name = self.scenario_input.data.strip()
        if problem := ft.scenario_problem(name):
            self.app.notify(problem, severity="error", timeout=5)
            return
        req = self.request
        path = ft.scenario_file(req.project, req.module, req.name)
        if name in self.scenarios and await self.app.run_dialog(confirm(  # type: ignore[attr-defined]
                _('Save scenario'), _('Replace the scenario {name} in {path}?').format(name=name, path=fm._shown(path, req.project)))) != Command.YES:
            return
        try:
            ft.save_scenario(req.project, req.module, req.name, name, self.scenario())
        except (ft.TestError, OSError) as exc:
            self.app.notify(str(exc), severity="error", timeout=6)
            return
        self.scenarios[name] = self.scenario()
        self.app.notify(_('Saved in {path}').format(path=fm._shown(path, req.project)), timeout=3)

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        try:
            self.context = ft.parse_context(self.context_input.data)
            self.expect = ft.parse_expectation(self.return_input.data, self.expected_input.data)
        except ft.TestError as exc:
            self.app.notify(str(exc), severity="error", timeout=6)
            return False
        try:
            self.timeout = float(self.timeout_input.data.strip() or ft.TIMEOUT)
        except ValueError:
            self.timeout = -1
        if not 0 < self.timeout <= 3600:
            self.app.notify(_('The time limit is a number of seconds, up to 3600'), severity="error", timeout=5)
            return False
        return True


def _last_key(project: Path, module: str | None, name: str) -> str:
    return f"{project}|{module or ''}:{name}"


def last_input(project: Path, module: str | None, name: str) -> ft.Scenario:
    saved = config.load().get("function_tests")
    entry = saved.get(_last_key(project, module, name)) if isinstance(saved, dict) else None
    if not isinstance(entry, dict):
        return ft.Scenario()
    return ft.Scenario(str(entry.get("context", "")), str(entry.get("return", "")), str(entry.get("expected", "")))


def remember_input(project: Path, module: str | None, name: str, scenario: ft.Scenario) -> None:
    """The last input of a Function, in the user's own settings (never in the project)."""
    settings = config.load()
    saved = settings.get("function_tests") if isinstance(settings.get("function_tests"), dict) else {}
    saved[_last_key(project, module, name)] = {"context": scenario.context, "return": scenario.returned, "expected": scenario.expected}
    settings["function_tests"] = saved
    config.save(settings)


class FunctionTestMixin:
    """Test Function and Debug Function (mixed into the Divide app)."""

    def _functest_init(self) -> None:
        self._function_debug = None  # (request, work folder, result file, role, expectation) while one is debugged
        self.function_items: list = []  # the last Function test's messages: shown whatever file is active

    def wants_function_test(self) -> bool:
        from divide.ui.flowfunctions import FunctionsWindow
        win = self.active_window()  # type: ignore[attr-defined]
        if not isinstance(win, FunctionsWindow):
            return False
        row = win.selected()
        return row is not None and row.kind in ("function", "ref")

    async def function_test_command(self) -> None:
        """Ctrl+F9 in the Functions window: test the Function under the cursor."""
        from divide.ui.flowfunctions import FunctionsWindow
        win = self.active_window()  # type: ignore[attr-defined]
        if not isinstance(win, FunctionsWindow) or win.catalog is None:
            return
        row = win.selected()
        entry = win.catalog.entry(row.module, row.name) if row is not None else None
        if entry is None:
            return
        role = row.ref.key if row.ref is not None else (entry.roles[0] if len(entry.roles) == 1 else None)
        await self.test_function(win.source, entry.module, entry.name, role)

    def flow_test_function(self, source, module: str | None, name: str, role: str | None) -> None:
        self._flow_test_function(source, module, name, role)

    @work(group="functest", exclusive=True)
    async def _flow_test_function(self, source, module, name, role) -> None:
        await self.test_function(source, module, name, role)

    async def test_function(self, source, module: str | None, name: str, role: str | None) -> None:
        """The Test Function dialog for ``module:name`` as ``source``'s Flow resolves it, then the run or the debug session."""
        project = self.root  # type: ignore[attr-defined]
        if self.debugging:  # type: ignore[attr-defined]
            await self.run_dialog(information(_('Test Function'), _('A program is being debugged: Ctrl+F2 ends it first.')))  # type: ignore[attr-defined]
            return
        if not shutil.which("php"):
            await self.run_dialog(information(_('Test Function'), _('php was not found in the PATH.')))  # type: ignore[attr-defined]
            return
        functions = self.flow_functions(source)  # type: ignore[attr-defined]
        try:
            request = ft.request_for(project, functions, module, name, {})
        except ft.TestError as exc:
            await self.run_dialog(information(_('Test Function'), str(exc)))  # type: ignore[attr-defined]
            return
        for other in self.editor_windows():  # type: ignore[attr-defined]  # PHP runs what is on disk
            if other.dirty and other.path is not None and other.editor.lang == "php" and not await self.save(other):  # type: ignore[attr-defined]
                return
        dialog = FunctionTestDialog(request, last=last_input(project, request.module, request.name),
                                    scenarios=ft.load_scenarios(project, request.module, request.name))
        if await self.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        remember_input(project, request.module, request.name, dialog.scenario())
        request = ft.TestRequest(**{**request.__dict__, "context": dialog.context})
        if dialog.choice == "debug":
            await self.debug_function(request, role, dialog.expect)
            return
        box = ProgressDialog(_('Testing Function'), [
            (_('Function'), request.qualified),
            (_('Time limit'), f"{dialog.timeout:g} s"),
            (_('Output'), size_text(b"")),
        ], width=60)

        def progress(out: bytes, err: bytes) -> None:
            box.set(_('Output'), size_text(out + err))

        def verdict(result: ft.TestResult) -> tuple[str, bool, list[tuple[str, str]]]:
            checks = ft.check(result, dialog.expect)
            ok = result.ok and all(c for c, _t in checks)
            word = ft.summary(result).split(" · ")[1]
            if result.ok and checks:
                word = _('expectations hold') if ok else _('an expectation fails')
            return word, ok, [(_('Exit code'), str(result.exit_code))]

        try:
            result = await run_with_progress(self, box, ft.run_test(request, timeout=dialog.timeout, on_data=progress), verdict)
        except ft.TestError as exc:
            await self.run_dialog(information(_('Test Function'), str(exc)))  # type: ignore[attr-defined]
            return
        if result is None:
            return
        self.show_function_result(result, ft.check(result, dialog.expect), role)

    def show_function_result(self, result: ft.TestResult, checks: list[tuple[bool, str]], role: str | None) -> None:
        """The report in Output; the exception's or fatal error's place, and PHP's messages, in Messages."""
        messages = list(result.messages)
        where = result.location()
        if where is not None:
            what = result.exception or result.error or {}
            head = f"{what.get('class')}: {what.get('message')}" if result.exception else str(what.get("message"))
            if not any(m.file == where[0] and m.line == where[1] for m in messages):
                messages.insert(0, ScriptMessage("error", head, where[0], where[1]))
        for ok, text in checks:
            if not ok:
                messages.append(ScriptMessage("error", _('Expectation fails: {what}').format(what=text)))
        target = Path(result.resolved["file"]) if result.resolved and result.resolved.get("file") else result.request.expected
        from divide.ui.runner import message_items
        from divide.ui.windows import MessageItem
        self.function_items = ([MessageItem(_('── test of {name}: {state} ──').format(
            name=result.request.qualified, state=ft.summary(result).split(" · ", 1)[1]))] + message_items(messages, self._text_of)  # type: ignore[attr-defined]
            if messages else [])
        self.show_script_result(target or result.request.project, ft.report(result, checks, role=role), "", [],  # type: ignore[attr-defined]
                                ft.summary(result))
        if self.function_items:
            if self.messages_window() is None:  # type: ignore[attr-defined]
                self._open_messages_window(layout=False)  # type: ignore[attr-defined]
            self.refresh_messages()  # type: ignore[attr-defined]

    # ---------------------------------------------------------- debugging
    async def debug_function(self, request: ft.TestRequest, role: str | None, expect: ft.Expectation) -> None:
        """The same call under the debugger: breakpoints in the Function and what it calls; with
        none in the Function's file, a stop at its first line."""
        from divide.run.dbgp import DebugError, DebugSession, xdebug_ini
        from divide.ui.runner import NO_XDEBUG

        ini = await xdebug_ini(extension=config.load().get("xdebug"))
        if ini is None:
            await self.run_dialog(information(_('Debug Function'), NO_XDEBUG))  # type: ignore[attr-defined]
            return
        work_dir, result_file, args = ft.debug_request(request)
        session = DebugSession(ft.HARNESS, args, cwd=request.project, ini=ini + ft.limits(),
                               on_data=lambda: self._debug_output(create=True))  # type: ignore[attr-defined]
        try:
            with self.busy(_('Starting {name} in the debugger...').format(name=request.qualified)):  # type: ignore[attr-defined]
                await session.start()
        except DebugError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            await self.run_dialog(information(_('Debug Function'), str(exc)))  # type: ignore[attr-defined]
            return
        self.session = session  # type: ignore[attr-defined]
        self._function_debug = (request, work_dir, result_file, role, expect)
        file = request.expected
        stop_in = file is None or not self.breakpoints.get(file)  # type: ignore[attr-defined]
        location = None
        try:
            await self.sync_breakpoints(session)  # type: ignore[attr-defined]
            if stop_in:  # none of the user's in the Function: stop at the call and step into it
                await session.set_breakpoint(ft.HARNESS, ft.call_line(), temporary=True)
            with self.busy(_('Running {name}... (Ctrl+F2 stops)').format(name=request.qualified)):  # type: ignore[attr-defined]
                location = await session.resume("run")
                if stop_in and location is not None and location.file == ft.HARNESS and location.line == ft.call_line():
                    location = await session.resume("step_into")
        except (DebugError, OSError):
            await session.stop()
        if location is None or not session.running:
            await self._debug_ended()  # type: ignore[attr-defined]
        else:
            self.debug_frame = 0  # type: ignore[attr-defined]
            await self._debug_paused(location)  # type: ignore[attr-defined]

    def function_debug_ended(self, session, reset: bool) -> bool:
        """A debugged Function test ended: its report (True), instead of a script's."""
        pending = self._function_debug
        if pending is None or session is None or session.script != ft.HARNESS:
            return False
        self._function_debug = None
        request, work_dir, result_file, role, expect = pending
        script = SimpleNamespace(exit_code=session.exit_code, seconds=0.0, output=session.output, errors=session.errors,
                                 stopped=reset)
        try:
            result = ft.read_result(request, result_file, script, "stopped" if reset else None)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
        self.show_function_result(result, ft.check(result, expect), role)
        return True
