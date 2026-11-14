"""Running and debugging PHP scripts in the IDE, the Turbo Pascal way.

``RunMixin`` is part of the app:

- Ctrl+F9 runs the PHP script under the progress box (Esc stops it); what it
  prints goes to the Output window, PHP's errors to the Messages window.
  Run > Parameters gives it its ``$argv``; Run > Run in terminal hands it the
  real terminal, for scripts that ask questions.
- The debugger (Xdebug): F7 trace into, F8 step over, Shift+F8 step out, F4 go
  to cursor, Ctrl+F9 run to the next breakpoint, Ctrl+F2 program reset,
  Ctrl+F8 toggle breakpoint, Ctrl+F7 add watch, Ctrl+F4 evaluate, Ctrl+F3
  call stack. The line about to run is the cyan bar; breakpoints are red.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from textual import events
from textual.app import ComposeResult
from textual_vision.list_box import ListBox

from divide import config
from divide.run.dbgp import DebugError, DebugSession, Location, xdebug_ini
from divide.run.script import ScriptMessage, ScriptResult, command, run_script, size_text, split_args
from divide.ui.dialogs import InputDialog, information
from divide.ui.progress import ProgressDialog, run_with_progress
from divide.ui.windows import MessageItem, _TVWindow

NO_XDEBUG = (
    "The debugger needs Xdebug, the PHP extension.\n\n"
    "Install it (Debian/Ubuntu: sudo apt install php-xdebug; elsewhere: pecl install xdebug) "
    "or give the path of xdebug.so in Options > Xdebug."
)
NOT_PAUSED = "Start the script in the debugger first (F7, F8 or F4) and stop at a line."
DEBUG_HINT = "F7 trace · F8 step · F4 to cursor · Ctrl+F9 run · Ctrl+F2 reset"


class PickList(ListBox):
    DEFAULT_CSS = """
    PickList { background: $panel; }
    PickList > .list-viewer--normal { color: $text; background: $panel; }
    PickList > .list-viewer--focused { color: $foreground; background: $background; }
    """
    can_focus = True

    def select_item(self, item: int) -> None:
        super().select_item(item)
        window = self.parent.parent if self.parent is not None else None
        if hasattr(window, "activate"):
            window.activate(item)  # type: ignore[union-attr]

    def on_click(self, event) -> None:
        if event.chain >= 2:
            self.select_item(self.focused)


class _ListWindow(_TVWindow):
    def __init__(self, title: str, number: int = 0) -> None:
        super().__init__(title, number=number)
        self.list = PickList([])
        self.lines: list[str] = []

    def compose_content(self) -> ComposeResult:
        yield self.list

    def show(self, lines: list[str]) -> None:
        if lines == self.lines:
            return
        keep = self.list.focused if self.lines else 0
        self.lines = lines or ["(empty)"]
        self.list.set_list(self.lines)
        if keep:
            self.list.focus_item(min(keep, len(self.lines) - 1))

    def activate(self, index: int) -> None:
        pass


class WatchesWindow(_ListWindow):
    """The watch expressions, then the variables of the frame. Ins adds, Del removes."""

    def __init__(self, number: int = 0) -> None:
        super().__init__("Watches", number=number)
        self.rows: list[int | None] = []  # line -> index of its watch

    def on_key(self, event: events.Key) -> None:
        app = self.app
        if event.key == "insert":
            event.stop()
            app.run_worker(app.add_watch(), group="command")  # type: ignore[attr-defined]
        elif event.key == "delete":
            event.stop()
            focused = self.list.focused
            if 0 <= focused < len(self.rows) and self.rows[focused] is not None:
                app.run_worker(app.remove_watch(self.rows[focused]), group="command")  # type: ignore[attr-defined]


class CallStackWindow(_ListWindow):
    """Where the script is: the innermost call first. Enter shows a frame."""

    def __init__(self, number: int = 0) -> None:
        super().__init__("Call stack", number=number)

    def activate(self, index: int) -> None:
        self.app.run_worker(self.app.select_frame(index), group="command")  # type: ignore[attr-defined]


def message_items(messages: list[ScriptMessage], text_of) -> list[MessageItem]:
    """PHP's errors as Messages lines that jump to their place."""
    items = []
    for m in messages:
        if m.file is None or m.line is None:
            items.append(MessageItem(m.text))
            continue
        start = end = None
        text = text_of(m.file)
        if text is not None:
            lines = text.split("\n")
            if m.line <= len(lines):
                start = sum(len(line) + 1 for line in lines[: m.line - 1])
                end = start + len(lines[m.line - 1])
        items.append(MessageItem(f"{m.file.name}({m.line}): {m.text}", m.file if start is not None else None, start, end))
    return items


class RunMixin:
    """PHP scripts: run, parameters, terminal and the debugger (mixed into the Divide app)."""

    def _run_init(self) -> None:
        self.last_script: Path | None = None
        self.run_messages: list[MessageItem] = []
        self.session: DebugSession | None = None
        self._debug_starting = False
        self.debug_frame = 0
        self.breakpoints: dict[Path, set[int]] = {}  # file -> 1-based lines
        self._bp_ids: dict[tuple[Path, int], str] = {}  # in the running session
        self.watches: list[str] = []

    # ---------------------------------------------------------- targets
    @property
    def debugging(self) -> bool:
        return self.session is not None and self.session.running

    @property
    def paused(self) -> bool:
        return self.session is not None and self.session.state == "break"

    def wants_run(self) -> bool:
        """Ctrl+F9 runs a script (rather than render a template)."""
        if self.debugging:
            return True
        win = self.active_editor()
        return win is not None and win.editor.lang == "php"

    def debug_keys_active(self) -> bool:
        """F7 / F8 / F4 belong to the debugger in PHP (elsewhere F7 still selects all)."""
        return self.wants_run()

    def run_arguments(self, script: Path) -> str:
        saved = config.load().get("run_args")
        return saved.get(str(script), "") if isinstance(saved, dict) else ""

    async def _script_to_run(self, title: str) -> Path | None:
        """The active PHP script (else the last one run), saved; None after telling why not."""
        win = self.active_editor()
        script: Path | None = None
        if win is not None and win.editor.lang == "php":
            if win.path is None:
                await self.run_dialog(information(title, "Save the script first (F2): PHP runs files."))
                return None
            script = win.path
        script = script or self.last_script
        if script is None:
            await self.run_dialog(information(title, "Open a PHP script (.php) to run it."))
            return None
        if not shutil.which("php"):
            await self.run_dialog(information(title, "php was not found in the PATH."))
            return None
        for other in self.editor_windows():  # PHP runs what is on disk
            if other.dirty and other.path is not None and other.editor.lang == "php" and not await self.save(other):
                return None
        return script

    def _relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    # -------------------------------------------------------------- run
    async def run_script_command(self) -> None:
        """Ctrl+F9 on a PHP script: run it (in the debugger: go on to the next breakpoint)."""
        if self.debugging:
            await self.debug_resume("run")
            return
        if self.breakpoints and await xdebug_ini(extension=config.load().get("xdebug")) is not None:
            await self.debug_resume("run")  # as in Turbo Pascal: Ctrl+F9 stops at the breakpoints
            return
        script = await self._script_to_run("Run")
        if script is None:
            return
        args = self.run_arguments(script)
        dialog = ProgressDialog("Running", [
            ("Script", self._relative(script)),
            ("Parameters", args or "(none)"),
            ("Output", size_text(b"")),
        ])

        def progress(out: bytes, err: bytes) -> None:
            dialog.set("Output", size_text(out))
            if err:
                dialog.set("Errors", size_text(err))

        def verdict(result: ScriptResult) -> tuple[str, bool, list[tuple[str, str]]]:
            errors = sum(m.level == "error" for m in result.messages)
            warnings = len(result.messages) - errors
            rows = [("Exit code", str(result.exit_code)), ("Messages", f"{errors} error(s), {warnings} warning(s)")]
            if result.stopped:
                return "Stopped", False, rows
            if errors or result.exit_code:
                return "Errors" if errors else f"Exit code {result.exit_code}", False, rows
            return ("Warnings" if warnings else "Success"), not warnings, rows

        job = run_script(script, split_args(args), on_data=progress)
        result = await run_with_progress(self, dialog, job, verdict)
        if result is None:
            return
        state = "stopped" if result.stopped else f"exit code {result.exit_code}"
        summary = f"{script.name} · {state} · {result.seconds:.2f}s · {size_text(result.output)}"
        self.show_script_result(script, result.output, result.errors, result.messages, summary)

    def show_script_result(self, script: Path, output: str, errors: str, messages: list[ScriptMessage], summary: str) -> None:
        """What a script printed in the Output window, PHP's errors in the Messages window."""
        from divide.ui.windows import OutputWindow

        self.last_script = script
        self.run_messages = [MessageItem(f"── run of {script.name}: {summary.split(' · ', 1)[-1]} ──"),
                             *message_items(messages, self._text_of)]
        text = output + (f"\n── stderr ──\n{errors}" if errors.strip() else "")
        output_win = self.output_window()
        first = output_win is None
        if output_win is None:
            output_win = OutputWindow(number=self._free_number())
            self.insert_window(output_win)
        output_win.show(script, text, summary)
        messages_win = self.messages_window()
        if messages and messages_win is None:
            messages_win = self._open_messages_window(layout=False)
        self.refresh_messages()
        if first:
            self._render_layout(script, output_win, messages_win if messages else None)
        self.raise_window(output_win)
        if messages and messages_win is not None:
            self.raise_window(messages_win)
        self.update_status()

    def run_items(self, path: Path | None) -> list[MessageItem]:
        """The last run's messages, for the Messages window of ``path`` (or of nothing)."""
        if self.run_messages and (path is None or path == self.last_script):
            return self.run_messages
        return []

    async def run_parameters(self) -> None:
        """Run > Parameters: the script's ``$argv`` (remembered per script)."""
        win = self.active_editor()
        script = win.path if win is not None and win.editor.lang == "php" and win.path else self.last_script
        if script is None:
            await self.run_dialog(information("Parameters", "Open a PHP script (.php) first."))
            return
        dialog = InputDialog("Program parameters", f"~P~arameters of {script.name}", self.run_arguments(script),
                             hint="As in a shell: quotes keep spaces. Ctrl+F9 and the debugger pass them.",
                             allow_empty=True)
        await self.run_dialog(dialog)
        if dialog.value is None:  # cancelled
            return
        settings = config.load()
        saved = settings.get("run_args") if isinstance(settings.get("run_args"), dict) else {}
        if dialog.value:
            saved[str(script)] = dialog.value
        else:
            saved.pop(str(script), None)
        settings["run_args"] = saved
        config.save(settings)

    async def run_in_terminal(self) -> None:
        """Run > Run in terminal: the script gets the real terminal (it may read the keyboard)."""
        script = await self._script_to_run("Run in terminal")
        if script is None:
            return
        argv = command(script, split_args(self.run_arguments(script)))
        try:
            with self.suspend():
                print(f"\n$ php {self._relative(script)} {self.run_arguments(script)}".rstrip(), flush=True)
                code = subprocess.run(argv, cwd=script.parent).returncode
                try:
                    input(f"\n[divide] {script.name} ended with exit code {code}. Press Enter to return.")
                except EOFError:
                    pass
        except Exception as exc:  # SuspendNotSupported (no real terminal)
            await self.run_dialog(information("Run in terminal", f"This terminal cannot be handed over: {exc}"))

    # --------------------------------------------------------- debugger
    async def debug_start(self) -> bool:
        if self._debug_starting:
            return False
        script = await self._script_to_run("Debug")
        if script is None:
            return False
        self._debug_starting = True
        try:
            ini = await xdebug_ini(extension=config.load().get("xdebug"))
            if ini is None:
                await self.run_dialog(information("Debug", NO_XDEBUG))
                return False
            session = DebugSession(script, split_args(self.run_arguments(script)), ini=ini,
                                   on_data=lambda: self._debug_output(create=True))
            try:
                with self.busy(f"Starting {script.name} in the debugger…"):
                    await session.start()
            except DebugError as exc:
                await self.run_dialog(information("Debug", str(exc)))
                return False
            self.session, self.last_script, self._bp_ids = session, script, {}
            return True
        finally:
            self._debug_starting = False

    async def _sync_breakpoints(self) -> None:
        session = self.session
        if session is None or not session._writer:
            return
        wanted = {(path, line) for path, lines in self.breakpoints.items() for line in lines}
        for key in list(self._bp_ids):
            if key not in wanted:
                await session.remove_breakpoint(self._bp_ids.pop(key))
        for path, line in sorted(wanted - set(self._bp_ids)):
            ident = await session.set_breakpoint(path, line)
            if ident:
                self._bp_ids[(path, line)] = ident

    async def debug_resume(self, how: str) -> None:
        """``run``, ``step_into``, ``step_over``, ``step_out`` or ``cursor`` (F4)."""
        if self.session is not None and self.session.state == "running":
            self.notify("The script is running: Ctrl+F2 stops it", timeout=2)
            return
        target = None
        if how == "cursor":
            win = self.active_editor()
            if win is None or win.path is None or win.editor.lang != "php":
                self.notify("Put the cursor on a line of a PHP script", timeout=2)
                return
            target = (win.path, win.editor.cursor_location[0] + 1)
        if not self.debugging and not await self.debug_start():
            return
        session = self.session
        assert session is not None
        location: Location | None = None
        try:
            await self._sync_breakpoints()
            if target is not None:
                await session.set_breakpoint(*target, temporary=True)
                how = "run"
            label = "Running" if how == "run" else "Stepping"
            with self.busy(f"{label} {session.script.name}… (Ctrl+F2 stops)"):
                location = await session.resume(how)
        except DebugError:
            await session.stop()
        if location is None or not session.running:
            await self._debug_ended()
        else:
            self.debug_frame = 0
            await self._debug_paused(location)

    async def _debug_paused(self, location: Location) -> None:
        if location.file is not None:
            win = self.open_file(location.file)
            if win is not None:
                win.editor.move_cursor((location.line - 1, 0), center=True)
                win.editor.focus()
        self._debug_output(create=True)
        self.refresh_debug_marks()
        await self.refresh_debug_windows()
        self.update_status()

    async def _debug_ended(self, reset: bool = False) -> None:
        session = self.session
        self.session = None
        self._bp_ids = {}
        self.refresh_debug_marks()
        await self.refresh_debug_windows()
        if session is None:
            return
        state = "program reset" if reset else f"exit code {session.exit_code}"
        summary = f"{session.script.name} · {state} · {size_text(session.output)}"
        self.show_script_result(session.script, session.output, session.errors, session.messages, summary)
        self.notify(f"{session.script.name}: {state}", timeout=2)

    async def debug_reset(self) -> None:
        """Ctrl+F2: end the script being debugged."""
        if self.session is None:
            self.notify("No program is being debugged", timeout=1.5)
            return
        await self.session.stop()
        await self._debug_ended(reset=True)

    def _debug_output(self, *, create: bool = False) -> None:
        """While debugging, the Output window follows what the script printed
        (``create``: open it, beside the script, once there is something)."""
        from divide.ui.windows import OutputWindow

        session = self.session
        if session is None:
            return
        win = self.output_window()
        if win is None:
            if not create or not session.output:
                return
            win = OutputWindow(number=self._free_number())
            self.insert_window(win)
            self._render_layout(session.script, win, None)
            if (source := self.window_for(session.script)) is not None:
                self.raise_window(source)
        win.show(session.script, session.output, f"{session.script.name} · debugging · {size_text(session.output)}")

    def debug_hint(self) -> str | None:
        session = self.session
        if session is None:
            return None
        if session.state == "running":
            return f"Running {session.script.name} · Ctrl+F2 reset"
        where = session.location
        place = f"{where.file.name}:{where.line}" if where and where.file else "?"
        return f"Paused at {place} · {DEBUG_HINT}"

    def refresh_debug_marks(self) -> None:
        location = self.session.location if self.paused and self.session is not None else None
        for win in self.editor_windows():
            if win.path is None:
                continue
            rows = {line - 1 for line in self.breakpoints.get(win.path, ())}
            here = location.line - 1 if location is not None and location.file == win.path else None
            win.editor.set_debug_marks(rows, here)

    # ------------------------------------------------------ breakpoints
    async def toggle_breakpoint(self) -> None:
        """Ctrl+F8 on the cursor's line."""
        win = self.active_editor()
        if win is None or win.editor.lang != "php" or win.path is None:
            self.notify("Breakpoints go on the lines of a saved PHP script", timeout=2)
            return
        line = win.editor.cursor_location[0] + 1
        lines = self.breakpoints.setdefault(win.path, set())
        lines.symmetric_difference_update({line})
        if not lines:
            del self.breakpoints[win.path]
        self.refresh_debug_marks()
        if self.paused:
            await self._sync_breakpoints()

    # ---------------------------------------------- watches, evaluate
    def _word_at_cursor(self) -> str:
        win = self.active_editor()
        if win is None:
            return ""
        ed = win.editor
        selected = ed.selected_text
        if selected and "\n" not in selected:
            return selected
        row, col = ed.cursor_location
        line = ed.document.get_line(row)
        start = col
        while start > 0 and (line[start - 1].isalnum() or line[start - 1] in "_$"):
            start -= 1
        end = col
        while end < len(line) and (line[end].isalnum() or line[end] == "_"):
            end += 1
        return line[start:end]

    async def evaluate(self) -> None:
        """Ctrl+F4: what PHP says an expression is, where the script stopped."""
        if not self.paused or self.session is None:
            await self.run_dialog(information("Evaluate", NOT_PAUSED))
            return
        dialog = InputDialog("Evaluate", "~E~xpression", self._word_at_cursor(), hint="Any PHP expression: $total * 2, count($items)")
        await self.run_dialog(dialog)
        if not dialog.value:
            return
        try:
            value = await self.session.evaluate(dialog.value, self.debug_frame)
            lines = value.lines(depth=2)
            text = "\n".join(lines[:20] + (["…"] if len(lines) > 20 else []))
        except DebugError as exc:
            text = f"{dialog.value}: {exc}"
        await self.run_dialog(information("Evaluate", text))

    async def add_watch(self) -> None:
        """Ctrl+F7: an expression the Watches window shows at every stop."""
        dialog = InputDialog("Add watch", "~W~atch expression", self._word_at_cursor())
        await self.run_dialog(dialog)
        if not dialog.value:
            return
        self.watches.append(dialog.value)
        self.show_watches()
        await self.refresh_debug_windows()

    async def remove_watch(self, index: int) -> None:
        if 0 <= index < len(self.watches):
            del self.watches[index]
            await self.refresh_debug_windows()

    # ----------------------------------------------- watches and stack
    def watches_window(self) -> WatchesWindow | None:
        return next((w for w in self.windows() if isinstance(w, WatchesWindow)), None)

    def stack_window(self) -> CallStackWindow | None:
        return next((w for w in self.windows() if isinstance(w, CallStackWindow)), None)

    def _bottom_window(self, window: _TVWindow, *, right: bool) -> None:
        """Watches bottom left, Call stack bottom right; the editors end where they start."""
        desktop = self.desktop
        width, height = (desktop.size.width or 80), (desktop.size.height or 24)
        half = width // 2
        top = max(0, height - 8)
        window.styles.width = width - half if right else half
        window.styles.height = min(8, height)
        window.styles.offset = (half if right else 0, top)
        for other in self.windows():
            if other.zoomed or isinstance(other, (_ListWindow,)) or type(other).__name__ in ("MessagesWindow", "ProjectWindow"):
                continue
            y = int(other.styles.offset.y.value) if other.styles.offset.y else 0
            if y + (other.size.height or height) > top and top - y >= 5:
                other.styles.height = top - y
        self.insert_window(window)

    def show_watches(self) -> None:
        window = self.watches_window()
        if window is None:
            window = WatchesWindow(number=self._free_number())
            self._bottom_window(window, right=False)
            self.run_worker(self.refresh_debug_windows(), group="debug-view")
        self.raise_window(window)

    def show_call_stack(self) -> None:
        window = self.stack_window()
        if window is None:
            window = CallStackWindow(number=self._free_number())
            self._bottom_window(window, right=True)
            self.run_worker(self.refresh_debug_windows(), group="debug-view")
        self.raise_window(window)

    async def refresh_debug_windows(self) -> None:
        watches, stack = self.watches_window(), self.stack_window()
        session = self.session if self.paused else None
        if watches is not None:
            lines: list[str] = []
            rows: list[int | None] = []
            for index, expression in enumerate(self.watches):
                if session is None:
                    found = [f"{expression}: (not running)"]
                else:
                    try:
                        found = (await session.evaluate(expression, self.debug_frame)).lines(depth=1)
                    except DebugError as exc:
                        found = [f"{expression}: {exc}"]
                lines += found
                rows += [index] * len(found)
            if session is not None:
                lines.append("── local variables ──")
                rows.append(None)
                try:
                    for var in await session.variables(self.debug_frame):
                        found = var.lines(depth=1)
                        lines += found
                        rows += [None] * len(found)
                except DebugError:
                    pass
            if not lines:
                lines, rows = ["(Ins adds a watch; variables show while the debugger is paused)"], [None]
            watches.rows = rows
            watches.show(lines)
        if stack is not None:
            frames = []
            if session is not None:
                try:
                    frames = await session.stack()
                except DebugError:
                    frames = []
            self._frames = frames
            stack.show([
                f"{'►' if f.level == self.debug_frame else ' '} {f.where}  {f.file.name if f.file else '?'}:{f.line}"
                for f in frames
            ] or ["(not running)"])

    async def select_frame(self, index: int) -> None:
        """Enter on a call: show its line; Watches and Evaluate look from there."""
        frames = getattr(self, "_frames", [])
        if not self.paused or not 0 <= index < len(frames):
            return
        frame = frames[index]
        self.debug_frame = frame.level
        if frame.file is not None:
            win = self.open_file(frame.file)
            if win is not None:
                win.editor.move_cursor((frame.line - 1, 0), center=True)
        await self.refresh_debug_windows()

    # ------------------------------------------------------- options
    async def choose_xdebug(self) -> None:
        """Options > Xdebug: the xdebug.so to load when php.ini does not load it."""
        current = config.load().get("xdebug") or ""
        loaded = await xdebug_ini()
        hint = "php.ini loads Xdebug already: leave it empty" if loaded == [] else "Empty: only an Xdebug that php.ini loads"
        dialog = InputDialog("Xdebug", "~P~ath of xdebug.so", current, hint=hint, browse=("*.so", Path("/usr/lib/php")),
                             allow_empty=True)
        await self.run_dialog(dialog)
        if dialog.value is None:
            return
        if dialog.value and not Path(dialog.value).expanduser().is_file():
            await self.run_dialog(information("Xdebug", f"{dialog.value} is not a file."))
            return
        config.set_value("xdebug", dialog.value or None)
