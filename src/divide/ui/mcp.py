"""Options > MCP server: divide's MCP server over HTTP, started and stopped from the IDE.

``McpMixin`` is part of the app. The server (:class:`divide.mcpserver.http.HttpServer`)
serves the open folder on ``http://127.0.0.1:8765/mcp`` by default; the dialog
starts, stops and configures it, shows its state, its address, why it could
not start and what it served. It never starts unless asked (or "Start with
divide" is checked); it stops when divide ends, and follows the project when
another folder opens. Starting and stopping run in a worker thread: Textual's
loop never waits for them.

Host, port and the two choices are kept in config.json ("mcp"); the token is
not: it lives in its own file (mcp-token, readable by the user alone), is
never shown, and is copied to the clipboard only with the client setup.
"""

from __future__ import annotations

from divide.i18n import _

import asyncio
import json

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.cluster import CheckBoxes
from textual_vision.constants import Command
from textual_vision.input_line import InputLine
from textual_vision.label import Label

from divide import config
from divide.mcpserver.http import (DEFAULT_HOST, DEFAULT_PORT, HttpServer, StartError, check_host, is_loopback,
                                   load_token, token_path, url_of)
from divide.ui.dialogs import _Dialog, shown_path

CM_MCP_START = Command.USER + 200
CM_MCP_STOP = Command.USER + 201
CM_MCP_COPY = Command.USER + 202
AUTOSTART, TOKEN = 1, 2  # the dialog's check boxes
WATCH = 1.0  # seconds between looks at a running server


def mcp_settings() -> dict:
    saved = config.load().get("mcp")
    saved = saved if isinstance(saved, dict) else {}
    port = saved.get("port")
    return {
        "host": saved.get("host") if isinstance(saved.get("host"), str) and saved.get("host") else DEFAULT_HOST,
        "port": port if isinstance(port, int) and 0 < port < 65536 else DEFAULT_PORT,
        "autostart": saved.get("autostart") is True,
        "token": saved.get("token") is True,
    }


def save_mcp_settings(values: dict) -> None:
    settings = config.load()
    settings["mcp"] = {key: values[key] for key in ("host", "port", "autostart", "token")}
    config.save(settings)


def client_setup(url: str, token: str | None) -> str:
    """The configuration most MCP clients take for an HTTP server (``mcpServers``)."""
    entry: dict = {"type": "http", "url": url}
    if token:
        entry["headers"] = {"Authorization": f"Bearer {token}"}
    return json.dumps({"mcpServers": {"divide": entry}}, indent=2)


class McpServerDialog(_Dialog):
    """State, address and settings of divide's MCP server; Start, Stop and Copy act at once."""

    DEFAULT_CSS = """
    McpServerDialog { width: 80; height: 17; }
    McpServerDialog .mcp-state { height: 4; color: $text; background: $surface; }
    McpServerDialog .mcp-fields { height: 2; margin-top: 1; }
    McpServerDialog .mcp-host { width: 1fr; height: 2; margin-right: 2; }
    McpServerDialog .mcp-port { width: 12; height: 2; }
    McpServerDialog InputLine { width: 1fr; }
    McpServerDialog CheckBoxes { width: 1fr; margin-top: 1; }
    McpServerDialog .dlg-hint { color: $text-muted; background: $surface; height: 2; }
    """

    def __init__(self, settings: dict) -> None:
        super().__init__(title=_('MCP server'))
        self.state = Static("", classes="mcp-state", markup=False)
        self.host_input = InputLine(max_len=200)
        self.host_input.data = settings["host"]
        self.port_input = InputLine(max_len=5)
        self.port_input.data = str(settings["port"])
        self.flags = CheckBoxes([_('Start ~w~ith divide'), _('Require a ~t~oken (always on a network address)')])
        self.flags.value = (AUTOSTART if settings["autostart"] else 0) | (TOKEN if settings["token"] else 0)
        self.hint = Static("", classes="dlg-hint", markup=False)
        self.start_button = Button(_('~S~tart'), CM_MCP_START, is_default=True, id="start")
        self.stop_button = Button(_('St~o~p'), CM_MCP_STOP, id="stop")
        self._timer = None
        self._done = False
        self.shown = ""  # the state as the dialog shows it

    def compose_content(self) -> ComposeResult:
        yield self.state
        with Horizontal(classes="mcp-fields"):
            with Vertical(classes="mcp-host"):
                yield Label(_('~H~ost'), link=self.host_input)
                yield self.host_input
            with Vertical(classes="mcp-port"):
                yield Label(_('~P~ort'), link=self.port_input)
                yield self.port_input
        yield self.flags
        yield self.hint
        with Horizontal(classes="dlg-buttons"):
            yield self.start_button
            yield self.stop_button
            yield Button(_('~C~opy client setup'), CM_MCP_COPY, id="copy")
            yield Button(_('Close'), Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self.show_state)
        self._timer = self.set_interval(0.5, self.show_state)

    # ---------------------------------------------------------- values
    def values(self) -> dict | None:
        """The settings as typed, or None (and why, in a notification)."""
        host = self.host_input.data.strip()
        problem = check_host(host)
        port_text = self.port_input.data.strip()
        if problem is None and not (port_text.isdigit() and 0 < int(port_text) < 65536):
            problem = _('The port is a number from 1 to 65535 (8765 by default).')
        if problem is not None:
            self.app.notify(problem, severity="error")
            return None
        return {"host": host, "port": int(port_text), "autostart": bool(self.flags.value & AUTOSTART),
                "token": bool(self.flags.value & TOKEN) or not is_loopback(host)}

    # ---------------------------------------------------------- state
    def show_state(self) -> None:
        if not self.is_mounted or self._done or getattr(self, "_closing", False):
            return
        app = self.app
        server: HttpServer | None = app.mcp_server  # type: ignore[attr-defined]
        lines: list[str] = []
        if app.mcp_busy:  # type: ignore[attr-defined]
            lines.append(_('Working...'))
        elif server is not None and server.running:
            lines.append(_('Running: {url}').format(url=server.url))
        elif server is not None and server.state == "failed":
            lines.append(_('Not running: {error}').format(error=server.error or "?"))
        else:
            lines.append(_('Stopped'))
        folder = app.folder  # type: ignore[attr-defined]
        if server is not None and server.running:
            lines.append(_('Project: {path}').format(path=shown_path(server.root)))
            clients = ", ".join(f"{name} {version}".strip() for name, version in server.clients.items()) or _('none yet')
            lines.append(_('Requests: {count} ({active} running) · clients: {clients}').format(
                count=server.requests, active=server.active, clients=clients))
            if server.token is not None:
                lines.append(_('A token is required (kept in {path})').format(path=shown_path(token_path())))
        elif folder is None:
            lines.append(_('Open a project folder first (File > Open folder): the server serves it.'))
        else:
            lines.append(_('Project: {path}').format(path=shown_path(folder)))
        self.shown = "\n".join(lines[:4])
        self.state.update(self.shown)
        running = server is not None and server.running
        self.start_button.text = _('~R~estart') if running else _('~S~tart')
        self.stop_button.disabled = not running
        host = self.host_input.data.strip()
        if host and not is_loopback(host):
            hint = _('Reachable from the network: a token is required, and the traffic is not encrypted. '
                     'Put a TLS reverse proxy in front, or use an SSH tunnel to 127.0.0.1.')
        else:
            hint = _('Only this machine can connect. Rendering runs the project\'s PHP: start it only on projects you trust.')
        self.hint.update(hint)

    # ---------------------------------------------------------- commands
    def on_command_message(self, message) -> None:
        if message.command in (CM_MCP_START, CM_MCP_STOP, CM_MCP_COPY):
            message.stop()
            message.prevent_default()
            self.run_worker(self._act(message.command), exclusive=True, group="mcp-dialog")

    async def _act(self, command: int) -> None:
        app = self.app
        if command == CM_MCP_STOP:
            await app.mcp_stop()  # type: ignore[attr-defined]
        elif command == CM_MCP_START:
            values = self.values()
            if values is None:
                return
            save_mcp_settings(values)
            await app.mcp_start(values)  # type: ignore[attr-defined]
        else:
            app.mcp_copy_setup()  # type: ignore[attr-defined]
        self.show_state()

    def end_modal(self, command: Command) -> None:
        values = self.values()  # Close keeps what was typed when it is right
        if values is not None:
            save_mcp_settings(values)
        self._done = True
        if self._timer is not None:
            self._timer.stop()
        super().end_modal(command)


class McpMixin:
    """divide's MCP server over HTTP (mixed into the Divide app)."""

    def _mcp_init(self) -> None:
        self.mcp_server: HttpServer | None = None
        self.mcp_busy = False
        self._mcp_lock = asyncio.Lock()
        self._mcp_watch = None

    async def mcp_command(self) -> None:
        """Options > MCP server."""
        await self.run_dialog(McpServerDialog(mcp_settings()))  # type: ignore[attr-defined]

    def mcp_autostart(self) -> None:
        if mcp_settings()["autostart"] and self.folder is not None:  # type: ignore[attr-defined]
            self.run_worker(self.mcp_start(), group="mcp", exit_on_error=False)  # type: ignore[attr-defined]

    async def mcp_start(self, values: dict | None = None) -> bool:
        """(Re)start the server on the open folder with ``values`` (the saved settings by default)."""
        values = values or mcp_settings()
        async with self._mcp_lock:
            self.mcp_busy = True
            try:
                return await self._mcp_start(values)
            finally:
                self.mcp_busy = False

    async def _mcp_start(self, values: dict) -> bool:
        folder = self.folder  # type: ignore[attr-defined]
        if folder is None:
            self.notify(_('Open a project folder first: the MCP server serves it'), severity="error")  # type: ignore[attr-defined]
            return False
        await self._mcp_halt()
        need_token = values["token"] or not is_loopback(values["host"])
        try:
            token = await asyncio.to_thread(load_token, create=True) if need_token else None
            server = HttpServer(folder, values["host"], values["port"], token=token)
        except (OSError, StartError) as exc:
            self.notify(_('MCP server: {error}').format(error=exc), severity="error")  # type: ignore[attr-defined]
            return False
        self.mcp_server = server
        try:
            await asyncio.to_thread(server.start)
        except StartError as exc:
            self.notify(_('The MCP server could not start: {error}').format(error=exc), severity="error", timeout=6)  # type: ignore[attr-defined]
            return False
        self._mcp_watch = self.set_interval(WATCH, self._mcp_check, name="mcp-watch")  # type: ignore[attr-defined]
        self.notify(_('MCP server: {url}').format(url=server.url), timeout=3)  # type: ignore[attr-defined]
        return True

    async def mcp_stop(self) -> None:
        async with self._mcp_lock:
            self.mcp_busy = True
            try:
                server = self.mcp_server
                await self._mcp_halt()
                if server is not None:
                    self.notify(_('MCP server stopped'), timeout=2)  # type: ignore[attr-defined]
            finally:
                self.mcp_busy = False

    async def _mcp_halt(self) -> None:
        if self._mcp_watch is not None:
            self._mcp_watch.stop()
            self._mcp_watch = None
        server, self.mcp_server = self.mcp_server, None
        if server is not None:
            await asyncio.to_thread(server.stop)

    def mcp_stop_now(self) -> None:
        """divide ends: the server goes with it (its threads would anyway: they are daemons)."""
        server, self.mcp_server = self.mcp_server, None
        if server is not None:
            server.stop(timeout=2)

    def _mcp_check(self) -> None:
        """A running server that died on its own (its listener failed): say so."""
        server = self.mcp_server
        if server is None or self.mcp_busy or server.alive():
            return
        if self._mcp_watch is not None:
            self._mcp_watch.stop()
            self._mcp_watch = None
        if server.state != "failed":
            server.state, server.error = "failed", _('the server stopped on its own')
        self.notify(_('The MCP server stopped: {error}').format(error=server.error), severity="error", timeout=8)  # type: ignore[attr-defined]
        self.run_worker(asyncio.to_thread(server.stop), group="mcp", exit_on_error=False)  # type: ignore[attr-defined]

    async def mcp_follow_folder(self, was_running: bool) -> None:
        """Another folder is the project: a server that ran serves it now."""
        if was_running and self.folder is not None:  # type: ignore[attr-defined]
            if await self.mcp_start():
                self.notify(_('The MCP server now serves {name}').format(name=self.folder.name), timeout=3)  # type: ignore[attr-defined]

    def mcp_copy_setup(self) -> None:
        server = self.mcp_server
        values = mcp_settings()
        if server is not None and server.running:
            url, token = server.url, server.token
        else:
            need = values["token"] or not is_loopback(values["host"])
            url, token = url_of(values["host"], values["port"]), (load_token(create=True) if need else None)
        self.copy_to_clipboard(client_setup(url, token))  # type: ignore[attr-defined]
        if token:
            self.notify(_('Copied: the client setup for {url}, with the token (keep it private)').format(url=url), timeout=4)  # type: ignore[attr-defined]
        else:
            self.notify(_('Copied: the client setup for {url}').format(url=url), timeout=3)  # type: ignore[attr-defined]

