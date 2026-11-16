"""PHP's built-in web server, ``php -S``, with Xdebug on every request (UI-independent).

``WebServer`` starts ``php -S address -t root [router]`` and keeps what it logs
(the requests and PHP's errors). With Xdebug, divide listens on a local port
and each request that runs PHP connects to it: ``next_request`` hands that
connection over as a ``DebugSession``, which the IDE runs on to the next
breakpoint (the request waits there, the browser with it).

The server has one worker: while a request is paused, the next ones wait.
"""

from __future__ import annotations

from divide.i18n import _

import asyncio
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from divide.run.dbgp import DebugError, DebugSession
from divide.run.script import _HEAD, LIMIT, ScriptMessage, php_messages
from divide.run import children

DEFAULT_ADDRESS = "127.0.0.1:8000"
START_TIMEOUT = 5.0
_STAMP = re.compile(r"^\[[^\]]*\] ")  # "[Sat Nov 14 14:53:54 2026] "
REQUEST = "$_SERVER['REQUEST_METHOD'] . ' ' . $_SERVER['REQUEST_URI']"


class ServerError(RuntimeError):
    """The server could not start (no PHP, the port is taken...)."""


def server_messages(log: str) -> list[ScriptMessage]:
    """PHP's errors in the server's log (its own lines, "Accepted", "[200]: GET /", are not)."""
    lines = []
    for raw in log.splitlines():
        if stamp := _STAMP.match(raw):
            rest = raw[stamp.end():]
            lines.append(rest if _HEAD.match(rest) else "")
        else:
            lines.append(raw)  # the rest of a message: a stack trace
    return php_messages("\n".join(lines))


def check_address(address: str) -> str | None:
    """Why ``host:port`` cannot be served, or None."""
    host, colon, port = address.strip().rpartition(":")
    if not colon or not host or not port.isdigit() or not 0 < int(port) < 65536:
        return _('The address is host:port, as in 127.0.0.1:8000 or localhost:8080.')
    return None


class WebServer:
    """One ``php -S``; ``ini`` loads Xdebug (None: serve without the debugger)."""

    def __init__(
        self,
        address: str,
        root: Path,
        router: Path | None = None,
        *,
        php: str | None = None,
        ini: list[str] | None = None,
        on_log: Callable[[], None] | None = None,
    ) -> None:
        self.address = address.strip()
        self.root = root
        self.router = router
        self.php = php or shutil.which("php")
        self.ini = ini
        self.on_log = on_log
        self._log = bytearray()
        self._proc: asyncio.subprocess.Process | None = None
        self._listener: asyncio.Server | None = None
        self._requests: asyncio.Queue[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = asyncio.Queue()
        self._pipes: list[asyncio.Task] = []

    @property
    def url(self) -> str:
        host, _, port = self.address.rpartition(":")
        host = "127.0.0.1" if host in ("0.0.0.0", "[::]") else host
        return f"http://{host}:{port}/"

    @property
    def debugging(self) -> bool:
        return self.ini is not None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    @property
    def log(self) -> str:
        return self._log.decode("utf-8", "replace")

    @property
    def messages(self) -> list[ScriptMessage]:
        return server_messages(self.log)

    def serves(self, path: Path) -> bool:
        """``path`` runs in this server (under the root, or the router's folder)."""
        folders = [self.root] + ([self.router.parent] if self.router else [])
        return any(path.is_relative_to(folder) for folder in folders)

    def url_of(self, path: Path) -> str:
        """The page of ``path`` (with a router, every URL goes to it: the root)."""
        if self.router is not None or not path.is_relative_to(self.root):
            return self.url
        relative = path.relative_to(self.root).as_posix()
        return self.url + ("" if relative == "index.php" else relative)

    async def _pipe(self, stream: asyncio.StreamReader) -> None:
        while chunk := await stream.read(65536):
            self._log.extend(chunk)
            if len(self._log) > LIMIT:  # a long-running server: keep the end
                cut = self._log.find(b"\n", len(self._log) - LIMIT)
                del self._log[: cut + 1 if cut >= 0 else len(self._log) - LIMIT]
            if self.on_log is not None:
                self.on_log()

    def command(self, port: int | None = None) -> list[str]:
        if not self.php:
            raise ServerError(_('php not found in PATH'))
        argv = [self.php, "-d", "log_errors=1"]
        if self.ini is not None and port is not None:
            argv += [
                *self.ini,
                "-d", "xdebug.mode=debug", "-d", "xdebug.start_with_request=yes",
                "-d", "xdebug.client_host=127.0.0.1", "-d", f"xdebug.client_port={port}",
                "-d", "xdebug.log_level=0",
            ]
        argv += ["-S", self.address, "-t", str(self.root)]
        if self.router is not None:
            argv.append(str(self.router))
        return argv

    async def start(self, timeout: float = START_TIMEOUT) -> None:
        """Start serving; ServerError with PHP's words when it cannot."""
        if (problem := check_address(self.address)) is not None:
            raise ServerError(problem)
        if not self.root.is_dir():
            raise ServerError(_('{root} is not a folder').format(root=self.root))
        if self.router is not None and not self.router.is_file():
            raise ServerError(_('{router} is not a file').format(router=self.router))
        port = None
        if self.ini is not None:
            self._listener = await asyncio.start_server(
                lambda reader, writer: self._requests.put_nowait((reader, writer)), "127.0.0.1", 0
            )
            port = self._listener.sockets[0].getsockname()[1]
        argv = self.command(port)
        self._proc = children.track(await asyncio.create_subprocess_exec(
            *argv, cwd=str(self.root), stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **children.options()
        ))
        self._pipes = [asyncio.create_task(self._pipe(self._proc.stdout)),  # type: ignore[arg-type]
                       asyncio.create_task(self._pipe(self._proc.stderr))]  # type: ignore[arg-type]
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while b") started" not in self._log:
            if self._proc.returncode is not None or loop.time() > deadline:
                await self.stop()
                said = self.log.strip() or _('php -S ended with exit code {returncode}').format(returncode=self._proc.returncode)
                raise ServerError(said if self._proc.returncode is not None else _('php -S did not start in {timeout:.0f}s').format(timeout=timeout))
            await asyncio.sleep(0.05)

    async def next_request(self) -> DebugSession:
        """The next request that runs PHP, paused before its first line;
        ``request`` says which ("GET /index.php?id=3")."""
        reader, writer = await self._requests.get()
        session = await DebugSession.attach(reader, writer)
        try:
            session.request = (await session.evaluate(REQUEST)).value.strip("'")
        except DebugError:
            session.request = session.script.name
        return session

    async def stop(self) -> None:
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        while not self._requests.empty():  # waiting requests go on without the debugger
            self._requests.get_nowait()[1].close()
        if self._proc is not None and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), 2)
            except TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        if self._pipes:
            await asyncio.gather(*self._pipes, return_exceptions=True)
            self._pipes = []
