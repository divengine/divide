"""Run > Web server: ``php -S`` for the project, and its requests in the debugger.

``WebMixin`` is part of the app. The server runs under Xdebug when there is
one: every request connects to divide and runs on to the first breakpoint,
where it pauses as a script does (F7, F8, Watches, Call stack...; the
browser waits). F7 / F8 / F4 with no request paused make the next request
stop on its first line (or at the cursor). Ctrl+F9 on a page the server
serves opens it in the browser. The "Web server" window shows the server's
log; PHP's errors in it go to the Messages window.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.cluster import CheckBoxes
from textual_vision.constants import Command
from textual_vision.input_line import InputLine
from textual_vision.label import Label

from divide import config
from divide.run.dbgp import DebugError, xdebug_ini
from divide.run.server import DEFAULT_ADDRESS, ServerError, WebServer, check_address
from divide.ui.dialogs import MessageBox, _Dialog, browse_into, information
from divide.ui.runner import message_items
from divide.editor.theme import OUTPUT
from divide.ui.windows import OUTPUT_CSS, EditorView, MessageItem, _TVWindow

CM_BROWSE_ROOT = Command.USER + 102
CM_BROWSE_ROUTER = Command.USER + 103
LOG_LINES = 500  # shown in the window


class WebServerDialog(_Dialog):
    """Address, document root and router of ``php -S``."""

    DEFAULT_CSS = """
    WebServerDialog { width: 66; height: 14; }
    WebServerDialog InputLine { width: 1fr; }
    WebServerDialog CheckBoxes { width: 1fr; margin-top: 1; }
    WebServerDialog .dlg-hint { color: $text-muted; background: $surface; height: 1; }
    """

    def __init__(self, root: Path, settings: dict, *, debugger: bool) -> None:
        super().__init__(title="Web server")
        self.project = root
        self.address_input = InputLine(max_len=200)
        self.address_input.data = settings.get("address") or DEFAULT_ADDRESS
        self.root_input = InputLine(max_len=1024)
        self.root_input.data = settings.get("root") or str(root)
        self.router_input = InputLine(max_len=1024)
        self.router_input.data = settings.get("router") or ""
        self.flags = CheckBoxes(["~O~pen in the browser"])
        self.flags.value = 1 if settings.get("browser", True) else 0
        self.hint = (
            "Xdebug found: requests stop at the breakpoints" if debugger
            else "No Xdebug: it serves, but requests cannot be debugged"
        )
        self.address = ""
        self.root: Path = root
        self.router: Path | None = None
        self.browser = True

    def compose_content(self) -> ComposeResult:
        yield Label("~A~ddress (host:port)", link=self.address_input)
        yield self.address_input
        yield Label("~D~ocument root", link=self.root_input)
        yield self.root_input
        yield Label("Router ~s~cript (optional: every request goes to it)", link=self.router_input)
        yield self.router_input
        yield self.flags
        yield Static(self.hint, classes="dlg-hint", markup=False)
        with Horizontal(classes="dlg-buttons"):
            yield Button("~S~tart", Command.OK, is_default=True, id="ok")
            yield Button("~R~oot...", CM_BROWSE_ROOT, id="browse-root")
            yield Button("Ro~u~ter...", CM_BROWSE_ROUTER, id="browse-router")
            yield Button("Cancel", Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self.address_input.select_all)

    def on_command_message(self, message) -> None:
        if message.command in (CM_BROWSE_ROOT, CM_BROWSE_ROUTER):
            message.stop()
            message.prevent_default()
            self.run_worker(self._browse(message.command), exclusive=True)

    async def _browse(self, command: int) -> None:
        if command == CM_BROWSE_ROOT:
            line, ok = self.root_input, await browse_into(
                self, self.root_input, "Document root", "*", self.project, folders=True)
        else:
            line, ok = self.router_input, await browse_into(
                self, self.router_input, "Router script", "*.php", Path(self.root_input.data or self.project))
        if ok:
            line.tv_select_self()
            line.focus()

    def _path(self, text: str) -> Path:
        path = Path(text.strip()).expanduser()
        return (path if path.is_absolute() else self.project / path).resolve()

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        problem = check_address(self.address_input.data)
        root = self._path(self.root_input.data or ".")
        router = self._path(self.router_input.data) if self.router_input.data.strip() else None
        if problem is None and not root.is_dir():
            problem = f"No such folder: {root}"
        if problem is None and router is not None and not router.is_file():
            problem = f"No such file: {router}"
        if problem is not None:
            self.app.notify(problem, severity="error")
            return False
        self.address, self.root, self.router = self.address_input.data.strip(), root, router
        self.browser = bool(self.flags.value & 1)
        return True


class ServerLogWindow(_TVWindow):
    """What ``php -S`` logs: the requests and PHP's errors (read only; white on black, like Output)."""

    DEFAULT_CSS = OUTPUT_CSS.replace("{name}", "ServerLogWindow")

    def __init__(self, number: int = 0) -> None:
        super().__init__("Web server", number=number)
        self.view = EditorView("", read_only=True, kind=OUTPUT)

    def compose_content(self) -> ComposeResult:
        yield self.view

    def show(self, server: WebServer) -> None:
        state = "serving" if server.running else "stopped"
        self.title = f"Web server: {server.url} ({state})"
        lines = server.log.rstrip("\n").split("\n")[-LOG_LINES:]
        text = "\n".join(lines)
        if text != self.view.text:
            self.view.load_text(text)
            self.view.move_cursor((len(lines) - 1, len(lines[-1])))  # the end: no bracket to match


class WebMixin:
    """The project's web server (mixed into the Divide app, beside RunMixin)."""

    def _web_init(self) -> None:
        self.web: WebServer | None = None
        self.web_next: tuple[str, tuple[Path, int] | None] | None = None  # what the next request does
        self._web_dirty = False
        self._web_timer = None

    @property
    def serving(self) -> bool:
        return self.web is not None and self.web.running

    def web_serves(self, path: Path | None) -> bool:
        return self.serving and path is not None and self.web.serves(path)  # type: ignore[union-attr]

    def _web_settings(self) -> dict:
        saved = config.load().get("web")
        here = saved.get(str(self.root)) if isinstance(saved, dict) else None
        return here if isinstance(here, dict) else {}

    def _save_web_settings(self, values: dict) -> None:
        settings = config.load()
        saved = settings.get("web") if isinstance(settings.get("web"), dict) else {}
        saved[str(self.root)] = values
        settings["web"] = saved
        config.save(settings)

    # ---------------------------------------------------------- command
    async def web_server_command(self) -> None:
        """Run > Web server: start it (a dialog), or open / stop the running one."""
        server = self.web
        if server is not None and server.running:
            box = MessageBox(
                "Web server",
                f"Serving {server.url}\nfrom {server.root}" + (f"\nthrough {server.router.name}" if server.router else ""),
                [("~O~pen in browser", Command.YES, "open"), ("~S~top server", Command.NO, "stop"),
                 ("Cancel", Command.CANCEL, "cancel")],
                width=60,
            )
            answer = await self.run_dialog(box)
            if answer == Command.YES:
                self.open_url(server.url)
            elif answer == Command.NO:
                await self.web_stop()
            return
        ini = await xdebug_ini(extension=config.load().get("xdebug"))
        dialog = WebServerDialog(self.root, self._web_settings(), debugger=ini is not None)
        if await self.run_dialog(dialog) != Command.OK:
            return
        self._save_web_settings({
            "address": dialog.address, "root": str(dialog.root),
            "router": str(dialog.router) if dialog.router else "", "browser": dialog.browser,
        })
        await self.web_start(dialog.address, dialog.root, dialog.router, ini=ini, browser=dialog.browser)

    async def web_start(self, address: str, root: Path, router: Path | None = None, *,
                        ini: list[str] | None = None, browser: bool = False) -> bool:
        if self.web is not None:
            await self.web_stop()
        server = WebServer(address, root, router, ini=ini, on_log=self._web_logged)
        try:
            with self.busy(f"Starting php -S {address}..."):
                await server.start()
        except ServerError as exc:
            await self.run_dialog(information("Web server", str(exc)))
            return False
        self.web = server
        self.web_next = None
        editor = self.active_editor()
        self.show_server_log()
        if editor is not None:  # the log opens below; the page stays where the keys go
            self.raise_window(editor)
        self._web_timer = self.set_interval(0.3, self._web_tick, name="web-log")
        if server.debugging:
            self.run_worker(self._serve_requests(server), group="web", exit_on_error=False)
        self.notify(f"Serving {server.url}" + ("" if server.debugging else " (no Xdebug: not debugged)"), timeout=3)
        if browser:
            self.open_url(server.url)
        self.update_status()
        return True

    async def web_stop(self) -> None:
        server, self.web = self.web, None
        self.web_next = None
        if server is None:
            return
        self.workers.cancel_group(self, "web")
        if self._web_timer is not None:
            self._web_timer.stop()
            self._web_timer = None
        session = self.session
        if session is not None and session.request is not None:
            await session.stop()
            await self._debug_ended(reset=True)
        await server.stop()
        window = self.server_log_window()
        if window is not None:
            window.show(server)
        self.refresh_messages()
        self.notify(f"Web server {server.address} stopped", timeout=2)
        self.update_status()

    # -------------------------------------------------------- requests
    async def _serve_requests(self, server: WebServer) -> None:
        """Each request runs on to a breakpoint; there it becomes the debugged session."""
        while server.running:
            try:
                session = await server.next_request()
            except DebugError:
                continue
            while self.session is not None:  # one at a time (a script in the debugger first)
                await self.session.closed.wait()
            how, target = self.web_next or ("run", None)
            self.web_next = None
            self.update_status()
            try:
                await self.sync_breakpoints(session)
                if target is not None:
                    await session.set_breakpoint(*target, temporary=True)
                location = await session.resume(how)
            except (DebugError, OSError):
                await session.stop()
                continue
            if location is None:
                continue  # it ran through
            self.session, self.last_script, self.debug_frame = session, session.script, 0
            self.notify(f"{session.request}: paused", timeout=2)
            await self._debug_paused(location)
            await session.closed.wait()

    def arm_next_request(self, how: str, target: tuple[Path, int] | None) -> None:
        """F7 / F8 / F4 with no request paused: the next request stops."""
        self.web_next = ("run" if target else "step_into", target)
        where = f"at line {target[1]} of {target[0].name}" if target else "on its first line"
        self.notify(f"The next request to {self.web.url} stops {where}", timeout=3)  # type: ignore[union-attr]
        self.update_status()

    def open_page(self, path: Path) -> None:
        """Ctrl+F9 on a page the server serves: request it, in the browser."""
        url = self.web.url_of(path)  # type: ignore[union-attr]
        self.open_url(url)
        self.notify(f"Opening {url}", timeout=2)

    def web_hint(self) -> str | None:
        if not self.serving:
            return None
        server = self.web
        assert server is not None
        if not server.debugging:
            return f"Serving {server.url} · not debugged (no Xdebug)"
        if self.web_next is not None:
            return f"Serving {server.url} · the next request stops"
        return f"Serving {server.url} · requests stop at breakpoints · F8 stops the next one"

    # ------------------------------------------------------------- log
    def server_log_window(self) -> ServerLogWindow | None:
        return next((w for w in self.windows() if isinstance(w, ServerLogWindow)), None)

    def show_server_log(self) -> None:
        if self.web is None:
            return
        window = self.server_log_window()
        if window is None:
            window = ServerLogWindow(number=self._free_number())
            self._bottom_window(window, side="full")
        window.show(self.web)
        self.raise_window(window)

    def _web_logged(self) -> None:
        self._web_dirty = True

    def _web_tick(self) -> None:
        if not self._web_dirty or self.web is None:
            return
        self._web_dirty = False
        window = self.server_log_window()
        if window is not None:
            window.show(self.web)
        if self.messages_window() is not None:
            self.refresh_messages()

    def web_items(self) -> list[MessageItem]:
        """The server's PHP errors, for the Messages window."""
        if self.web is None:
            return []
        messages = self.web.messages
        if not messages:
            return []
        return [MessageItem(f"── web server {self.web.address} ──"), *message_items(messages, self._text_of)]
