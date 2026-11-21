"""Run > Run (Ctrl+F9) on a Runner Flow: run it, pause, resume, through Runner's own command line.

``FlowMixin`` is part of the app. On a YAML Flow (a ``blocks`` root), Ctrl+F9
opens the Run Flow dialog: the initial context (a JSON file, or JSON typed
there), the function root (``--root``) and the file the context is saved to
(``--save-context``, by default one per Flow under the project's ``.div/runner/``,
kept out of Git), remembered per Flow. **Run** starts the Flow, **Resume**
continues the paused run saved in that file. The run goes on in a progress
box (Esc stops PHP); the Output window shows how it ended (done, paused,
error, not saved, stopped), Runner's log, the resulting context and what
the Flow printed; Runner's diagnostics and PHP's errors go to Messages.

What divide decides, and nothing more: which file is run, with which
context, saved where; that a paused run is never restarted, nor its saved
context replaced, without the user saying so; that a stopped run leaves
the saved context as it was. Runner runs the Flow (:mod:`divide.run.flow`).
"""

from __future__ import annotations

from divide.i18n import _

import json
import shutil
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.constants import Command
from textual_vision.input_line import InputLine
from textual_vision.label import Label

from divide import config
from divide.run.flow import (FlowRun, Runner, Saved, check_context_file, check_context_text, default_checkpoint, find_runner,
                             is_managed, prepare_checkpoint, read_saved, run_flow)
from divide.run.script import ScriptError, ScriptMessage, size_text
from divide.ui.dialogs import _Dialog, browse_into, confirm, information
from divide.ui.progress import ProgressDialog, run_with_progress
from divide.ui.windows import MessageItem

CM_FLOW_RESUME = Command.USER + 204
CM_FLOW_BROWSE = Command.USER + 205
HIDDEN_KEYS = ("_runner_logs",)  # shown apart, as the log

VERDICTS = {  # state -> (verdict word, ok)
    "done": (_("Done"), True),
    "paused": (_("Paused"), True),
    "error": (_("Error"), False),
    "invocation": (_("Not run"), False),
    "unsaved": (_("Context not saved"), False),
    "crashed": (_("PHP ended"), False),
    "cancelled": (_("Stopped"), False),
}


def flow_settings(flow: Path) -> dict:
    saved = config.load().get("flows")
    here = saved.get(str(flow)) if isinstance(saved, dict) else None
    here = here if isinstance(here, dict) else {}
    return {"context": str(here.get("context") or ""), "root": str(here.get("root") or ""),
            "save": str(here.get("save") or "")}


def save_flow_settings(flow: Path, values: dict) -> None:
    settings = config.load()
    saved = settings.get("flows") if isinstance(settings.get("flows"), dict) else {}
    saved[str(flow)] = {key: values[key] for key in ("context", "root", "save")}
    settings["flows"] = saved
    config.save(settings)


def default_save(flow: Path, project: Path) -> str:
    """``flows/order.yml`` -> ``.div/runner/flows/order.yml.context.json`` (relative to the project)."""
    target = default_checkpoint(flow, project)
    try:
        return target.relative_to(project).as_posix()
    except ValueError:
        return str(target)


def saved_text(saved: Saved | None, managed: bool = True) -> str:
    """The context file's state, as the dialog says it."""
    if saved is None:
        return _('Not saved: a paused run cannot be resumed.')
    if not saved.exists:
        return _('Nothing saved yet: Run saves the context there.')
    if saved.problem is not None:
        return _('The file there {problem}: Resume cannot use it.').format(problem=saved.problem)
    if saved.state == "paused":
        where = f"{saved.block}.{saved.step}" if saved.block and saved.step else (saved.block or "?")
        calls = _(' (inside {n} call(s))').format(n=saved.calls) if saved.calls else ""
        return _('Paused at {where}{calls}: Resume continues there.').format(where=where, calls=calls)
    if saved.state in ("done", "error") and managed:
        return _('The last run ended {state}: Run replaces it when it ends.').format(state=saved.state)
    if saved.state in ("done", "error"):
        return _('The last run ended {state}: Run asks before replacing a file of yours.').format(state=saved.state)
    return _('The file there is not a context saved by Runner.')


class FlowDialog(_Dialog):
    """The initial context, function root and saved context of a Flow; Run or Resume."""

    DEFAULT_CSS = """
    FlowDialog { width: 78; height: 16; }
    FlowDialog InputLine { width: 1fr; }
    FlowDialog .flow-about { color: $text; background: $surface; height: 1; }
    FlowDialog .flow-saved { color: $text; background: $surface; height: 2; margin-top: 1; }
    """

    def __init__(self, flow: Path, project: Path, runner: Runner, settings: dict) -> None:
        super().__init__(title=_('Run Flow'))
        self.flow, self.project, self.runner = flow, project, runner
        self.context_input = InputLine(max_len=4096)
        self.context_input.data = settings["context"]
        self.root_input = InputLine(max_len=1024)
        self.root_input.data = settings["root"]
        self.save_input = InputLine(max_len=1024)
        self.save_input.data = settings["save"] or default_save(flow, project)
        self.saved_line = Static("", classes="flow-saved", markup=False)
        self.run_button = Button(_('~R~un'), Command.OK, id="run")
        self.resume_button = Button(_('Res~u~me'), CM_FLOW_RESUME, id="resume")
        self._browse_for: InputLine = self.context_input
        self.choice: str | None = None  # "run" | "resume"
        self.values: dict = {}

    def compose_content(self) -> ComposeResult:
        shown = self._rel(self.flow)
        yield Static(_('Flow {flow} · Runner {version}').format(flow=shown, version=self.runner.version or "?"),
                     classes="flow-about", markup=False)
        yield Label(_('~I~nitial context: a JSON file, or a JSON object typed here (optional)'), link=self.context_input)
        yield self.context_input
        yield Label(_('~F~unction root, --root (optional; relative to the project)'), link=self.root_input)
        yield self.root_input
        yield Label(_('~S~ave context to, --save-context (empty: not saved)'), link=self.save_input)
        yield self.save_input
        yield self.saved_line
        with Horizontal(classes="dlg-buttons"):
            yield self.run_button
            yield self.resume_button
            yield Button(_('~B~rowse...'), CM_FLOW_BROWSE, id="browse")
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.show_saved()
        self.call_after_refresh(self.context_input.select_all)

    def _rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.project).as_posix()
        except ValueError:
            return str(path)

    def path_of(self, text: str) -> Path | None:
        text = text.strip()
        if not text:
            return None
        path = Path(text).expanduser()
        return (path if path.is_absolute() else self.project / path).resolve()

    def saved(self) -> Saved | None:
        target = self.path_of(self.save_input.data)
        return read_saved(target) if target is not None else None

    def show_saved(self) -> None:
        saved = self.saved()
        self.saved_line.update(_('Saved context: ') + saved_text(saved, saved is None or is_managed(saved.path, self.project)))
        resumable = saved is not None and saved.resumable
        self.resume_button.disabled = not resumable
        self.resume_button.is_default = resumable
        self.run_button.is_default = not resumable

    def on_input_line_changed(self, event) -> None:  # the save file typed: its state follows
        self.show_saved()

    def on_descendant_focus(self, event) -> None:
        if isinstance(event.widget, InputLine):
            self._browse_for = event.widget

    def on_command_message(self, message) -> None:
        if message.command == CM_FLOW_BROWSE:
            message.stop()
            message.prevent_default()
            self.run_worker(self._browse(), exclusive=True)
        elif message.command == CM_FLOW_RESUME:
            message.stop()
            message.prevent_default()
            if self._check("resume"):
                self.choice = "resume"
                super().end_modal(Command.OK)

    async def _browse(self) -> None:
        line = self._browse_for
        if line is self.root_input:
            ok = await browse_into(self, line, _('Function root'), "*", self.project, folders=True)
        elif line is self.save_input:
            target = self.path_of(line.data)
            start = target.parent if target is not None and target.parent.is_dir() else self.project
            ok = await browse_into(self, line, _('Save context to'), "*.json", start)
        else:
            ok = await browse_into(self, line, _('Initial context'), "*.json", self.project)
        if ok:
            self.show_saved()
            line.focus()

    def _check(self, choice: str) -> bool:
        problem = None
        context = self.context_input.data.strip()
        root = self.path_of(self.root_input.data)
        save = self.path_of(self.save_input.data)
        if choice == "run" and context:
            if context.startswith("{"):
                problem = check_context_text(context)
            else:
                path = self.path_of(context)
                problem = check_context_file(path) if path is not None else None
        if problem is None and root is not None and not root.is_dir():
            problem = _('The function root is not a folder: {path}').format(path=self._rel(root))
        if problem is None and save is not None and not save.parent.is_dir() and not is_managed(save, self.project):
            problem = _('No such folder for the saved context: {path}').format(path=self._rel(save.parent))
        if problem is None and choice == "resume":
            saved = read_saved(save) if save is not None else None
            if saved is None or not saved.resumable:
                problem = _('Nothing to resume: ') + saved_text(saved)
        if problem is not None:
            self.app.notify(problem, severity="error", timeout=6)
            return False
        self.values = {"context": self.context_input.data.strip(), "root": self.root_input.data.strip(),
                       "save": self.save_input.data.strip()}
        return True

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        if self.choice == "resume":
            return True
        if not self._check("run"):
            return False
        self.choice = "run"
        return True


class FlowMixin:
    """Runner Flows (mixed into the Divide app, beside RunMixin)."""

    def _flow_init(self) -> None:
        self.last_flow: Path | None = None
        self.flow_messages: list[MessageItem] = []

    def wants_flow(self) -> bool:
        """Ctrl+F9 runs a Flow: the active editor is a YAML Flow (and no PHP script is being debugged)."""
        if self.debugging:  # type: ignore[attr-defined]
            return False
        return self.flow_source() is not None  # type: ignore[attr-defined]

    async def flow_command(self) -> None:
        """Ctrl+F9 (or Run > Parameters) on a Flow (its code or its Flow window): the Run Flow dialog, then the run."""
        win = self.flow_source()  # type: ignore[attr-defined]
        if win.path is None:
            await self.run_dialog(information(_('Run Flow'), _('Save the Flow first (F2): Runner runs files.')))  # type: ignore[attr-defined]
            return
        if win.dirty and not await self.save(win):  # type: ignore[attr-defined]
            return
        flow = win.path.resolve()
        project = self.root  # type: ignore[attr-defined]
        if not shutil.which("php"):
            await self.run_dialog(information(_('Run Flow'), _('php was not found in the PATH: Runner is PHP.')))  # type: ignore[attr-defined]
            return
        runner = find_runner(project)
        if not runner.usable:
            await self.run_dialog(information(_('Run Flow'), runner.problem or ""))  # type: ignore[attr-defined]
            return
        dialog = FlowDialog(flow, project, runner, flow_settings(flow))
        if await self.run_dialog(dialog) != Command.OK or dialog.choice is None:  # type: ignore[attr-defined]
            return
        save_flow_settings(flow, dialog.values)
        save = dialog.path_of(dialog.values["save"])
        if dialog.choice == "run" and save is not None:
            saved = read_saved(save)
            finished = saved.problem is None and saved.state in ("done", "error")
            if saved.exists and not (finished and is_managed(save, project)):
                why = (_('{name} holds a paused run (Resume continues it).') if saved.resumable
                       else _('{name} holds a finished run, in a file you chose.') if finished
                       else _('{name} is not a context of a finished run.')).format(name=save.name)
                answer = await self.run_dialog(confirm(_('Run Flow'), why + " " + _(  # type: ignore[attr-defined]
                    'Start the Flow over? The file is replaced when the new run ends.')))
                if answer != Command.YES:
                    return
        await self.flow_run(flow, project, runner, dialog, save)

    async def flow_run(self, flow: Path, project: Path, runner: Runner, dialog: FlowDialog, save: Path | None) -> FlowRun | None:
        resume = dialog.choice == "resume"
        typed = dialog.values["context"] if not resume and dialog.values["context"].startswith("{") else None
        context = save if resume else (dialog.path_of(dialog.values["context"]) if dialog.values["context"] and typed is None else None)
        functions = dialog.path_of(dialog.values["root"])
        shown = (_('saved, {name}').format(name=save.name) if resume and save is not None
                 else _('typed') if typed is not None else (context.name if context is not None else _('(none)')))
        box = ProgressDialog(_('Resuming Flow') if resume else _('Running Flow'), [
            (_('Flow'), dialog._rel(flow)),
            (_('Context'), shown),
            (_('Save to'), dialog._rel(save) if save is not None else _('(not saved)')),
            (_('Printed'), size_text(b"")),
        ], width=60)

        def progress(out: bytes, err: bytes) -> None:
            box.set(_('Printed'), size_text(err))  # what the Flow printed and Runner said: stderr

        def verdict(run: FlowRun) -> tuple[str, bool, list[tuple[str, str]]]:
            word, ok = VERDICTS.get(run.state, (run.state, False))
            rows = [(_('Exit code'), str(run.exit_code))]
            if run.saved_to is not None:
                rows.append((_('Saved to'), run.saved_to.name))
            return word, ok, rows

        if save is not None:
            prepare_checkpoint(save, project)
        job = run_flow(runner, flow, cwd=project, context=context, context_text=typed, functions=functions,
                       save_to=save, resumed=resume, on_data=progress)
        try:
            run = await run_with_progress(self, box, job, verdict)
        except ScriptError as exc:
            await self.run_dialog(information(_('Run Flow'), str(exc)))  # type: ignore[attr-defined]
            return None
        if run is None:
            return None
        self.show_flow_result(run, project, save)
        return run

    # ---------------------------------------------------------- results
    def flow_report(self, run: FlowRun, project: Path, save: Path | None) -> str:
        """The Output window's text: how the run ended, Runner's log, the context, what the Flow printed."""
        def rel(path: Path) -> str:
            try:
                return path.relative_to(project).as_posix()
            except ValueError:
                return str(path)

        lines = [_('State: {state}').format(state=_state_line(run))]
        if run.result:
            lines.append(_('Result: {result}').format(result=run.result))
        error = (run.context or {}).get("_runner_error")
        if error:
            lines.append(_('Error: {error}').format(error=error))
        if run.state == "cancelled":
            lines.append(_('Stopped by you: PHP was killed; nothing was saved{kept}.').format(
                kept=_(', {name} is as it was').format(name=rel(save)) if save is not None and save.exists() else ""))
        elif run.saved_to is not None:
            lines.append(_('Context saved to {path}').format(path=rel(run.saved_to)))
        elif run.state in ("unsaved", "invocation", "crashed"):
            lines.append(_('Nothing was saved{kept}.').format(
                kept=_(', {name} is as it was').format(name=rel(save)) if save is not None and save.exists() else ""))
        elif save is None and run.state == "paused":
            lines.append(_('The context was not saved: give a file in Save context to resume this run.'))
        if run.state == "paused" and run.saved_to is not None:
            lines.append(_('Ctrl+F9, Resume: continues the Flow from the saved context.'))
        for diagnostic in run.diagnostics:
            lines.append("runner: " + diagnostic)
        if run.logs:
            lines += ["", _('── log ──')]
            for entry in run.logs:
                message = str(entry.get("message", "")).replace("[divengine.runner] ", "")
                lines.append(f"{str(entry.get('level', '')):<5} {message}")
        if run.context is not None:
            shown = {k: v for k, v in run.context.items() if k not in HIDDEN_KEYS}
            lines += ["", _('── context ──'), json.dumps(shown, indent=2, ensure_ascii=False)]
        if run.stderr.strip():
            lines += ["", _('── stderr ──'), run.stderr.rstrip()]
        return "\n".join(lines) + "\n"

    def show_flow_result(self, run: FlowRun, project: Path, save: Path | None) -> None:
        from divide.ui.runner import message_items
        from divide.ui.windows import OutputWindow

        self.last_flow = run.flow
        summary = f"{run.flow.name} · {_state_line(run)} · {run.seconds:.2f}s"
        problems = [ScriptMessage("error", d, run.flow) for d in run.diagnostics] + list(run.messages)
        self.flow_messages = ([MessageItem(_('── Flow {name}: {state} ──').format(name=run.flow.name, state=_state_line(run))),
                               *message_items(problems, self._text_of)] if problems else [])  # type: ignore[attr-defined]
        output = self.output_window()  # type: ignore[attr-defined]
        first = output is None
        if output is None:
            output = OutputWindow(number=self._free_number())  # type: ignore[attr-defined]
            self.insert_window(output)  # type: ignore[attr-defined]
        output.show(run.flow, self.flow_report(run, project, save), summary)
        messages = self.messages_window()  # type: ignore[attr-defined]
        if problems and messages is None:
            messages = self._open_messages_window(layout=False)  # type: ignore[attr-defined]
        self.refresh_messages()  # type: ignore[attr-defined]
        if first:
            self._render_layout(run.flow, output, messages if problems else None)  # type: ignore[attr-defined]
        self.raise_window(output)  # type: ignore[attr-defined]
        if problems and messages is not None:
            self.raise_window(messages)  # type: ignore[attr-defined]
        word, ok = VERDICTS.get(run.state, (run.state, False))
        hint = _(' · Ctrl+F9, Resume continues it') if run.state == "paused" and run.saved_to is not None else ""
        self.notify(f"{run.flow.name}: {word}{hint}", timeout=4, severity="information" if ok else "error")  # type: ignore[attr-defined]
        self.update_status()  # type: ignore[attr-defined]

    def flow_items(self, path: Path | None) -> list[MessageItem]:
        """The last Flow run's messages, for the Messages window of ``path`` (or of nothing)."""
        if self.flow_messages and (path is None or path == self.last_flow):
            return list(self.flow_messages)
        return []


def _state_line(run: FlowRun) -> str:
    if run.state == "paused" and run.context is not None:
        state = run.context.get("_flow_state")
        block = state.get("block") if isinstance(state, dict) else None
        step = run.context.get("_current_step_id")
        stack = run.context.get("_flow_stack")
        calls = len(stack) if isinstance(stack, list) else 0
        where = f"{block}.{step}" if block and step else (block or "?")
        inside = _(' (inside {n} call(s))').format(n=calls) if calls else ""
        return _('paused at {where}{inside}').format(where=where, inside=inside)
    words = {"done": _('done'), "error": _('error'), "invocation": _('not run (invocation error)'),
             "unsaved": _('ran, but the context was not saved'), "crashed": _('PHP ended (exit code {code})'),
             "cancelled": _('stopped')}
    return (_('resumed, ') if run.resumed and run.state != "cancelled" else "") + words.get(run.state, run.state).format(code=run.exit_code)
