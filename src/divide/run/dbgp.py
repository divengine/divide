"""Debug PHP with Xdebug over DBGp (UI-independent).

divide listens on a free local port and starts ``php`` with Xdebug in debug
mode pointed at it; Xdebug connects back and divide drives it with DBGp
commands (https://xdebug.org/docs/dbgp): breakpoints, run, step into / over /
out, the call stack, the variables of a frame and ``eval``.

Engine packets are ``<length>\\0<xml>\\0``; commands are one line ending in
``\\0``, with their data (an expression) in base64 after ``--``.
"""

from __future__ import annotations

import asyncio
import base64
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from divide.run.script import ERROR_INI, LIMIT, ScriptMessage, php_messages

NS = {"d": "urn:debugger_protocol_v1", "x": "https://xdebug.org/dbgp/xdebug"}
CONNECT_TIMEOUT = 10.0
REPLY_TIMEOUT = 30.0


class DebugError(RuntimeError):
    """Debugging cannot start or the connection broke."""


@dataclass(frozen=True)
class Location:
    file: Path | None
    line: int  # 1-based


@dataclass(frozen=True)
class Frame:
    level: int
    where: str  # function, or {main}
    file: Path | None
    line: int


@dataclass(frozen=True)
class Variable:
    name: str
    type: str
    value: str  # scalars as PHP shows them; "array(3)", "Shop" for compound values
    children: tuple["Variable", ...] = ()

    def lines(self, indent: int = 0, depth: int = 2) -> list[str]:
        """``$name = value`` and, indented, the children Xdebug sent."""
        out = [f"{'  ' * indent}{self.name} = {self.value}"]
        if depth > 0:
            for child in self.children:
                out.extend(child.lines(indent + 1, depth - 1))
        return out


def file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def uri_path(uri: str | None) -> Path | None:
    if not uri:
        return None
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None  # eval'd code: dbgp://1
    return Path(unquote(parsed.path))


def _text(node: ET.Element) -> str:
    raw = node.text or ""
    if node.get("encoding") == "base64":
        return base64.b64decode(raw).decode("utf-8", "replace")
    return raw


def variable(node: ET.Element) -> Variable:
    """A DBGp ``<property>`` as a Variable (with the children Xdebug included)."""
    kind = node.get("type", "?")
    name = node.get("name") or node.get("fullname") or "?"
    children = tuple(variable(c) for c in node.findall("d:property", NS))
    count = node.get("numchildren")
    match kind:
        case "string":
            value = repr(_text(node))
            if value.startswith('"'):  # PHP quotes: always single
                value = "'" + value[1:-1].replace("'", "\\'") + "'"
        case "array":
            value = f"array({count or len(children)})"
        case "object":
            value = node.get("classname") or "object"
        case "null":
            value = "null"
        case "uninitialized":
            value = "(not set)"
        case "bool":
            value = "true" if _text(node) == "1" else "false"
        case _:
            value = _text(node)
    return Variable(name, kind, value, children)


def packets(buffer: bytearray) -> list[bytes]:
    """Complete engine packets taken out of ``buffer`` (the rest stays)."""
    found = []
    while True:
        zero = buffer.find(b"\0")
        if zero < 0:
            break
        size = int(buffer[:zero] or b"0")
        end = zero + 1 + size
        if len(buffer) < end + 1:
            break
        found.append(bytes(buffer[zero + 1 : end]))
        del buffer[: end + 1]
    return found


async def xdebug_ini(php: str | None = None, extension: str | None = None) -> list[str] | None:
    """PHP options that load Xdebug: none when php.ini already does, the
    configured ``xdebug.so`` otherwise; None when there is no Xdebug."""
    php = php or shutil.which("php")
    if not php:
        return None
    proc = await asyncio.create_subprocess_exec(
        php, "-m", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    out, _ = await proc.communicate()
    if "xdebug" in out.decode("utf-8", "replace").lower().split():
        return []
    if extension and Path(extension).expanduser().is_file():
        return ["-d", f"zend_extension={Path(extension).expanduser()}"]
    return None


class DebugSession:
    """One debugged run of a PHP script."""

    def __init__(
        self,
        script: Path,
        args: list[str] | None = None,
        *,
        cwd: Path | None = None,
        php: str | None = None,
        ini: list[str] | None = None,
        on_data: Callable[[], None] | None = None,
    ) -> None:
        self.script = script
        self.args = args or []
        self.cwd = cwd or script.parent
        self.php = php or shutil.which("php")
        self.ini = ini or []
        self.on_data = on_data
        self.state = "new"  # starting, break, stopping, stopped
        self.location: Location | None = None
        self.exit_code: int | None = None
        self._out, self._err = bytearray(), bytearray()
        self._proc: asyncio.subprocess.Process | None = None
        self._server: asyncio.Server | None = None
        self._connected: asyncio.Future[tuple[asyncio.StreamReader, asyncio.StreamWriter]] | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._buffer = bytearray()
        self._ready: list[bytes] = []  # packets read, not yet taken
        self._tx = 0
        self._lock = asyncio.Lock()
        self._pipes: list[asyncio.Task] = []

    # ------------------------------------------------------------ output
    @property
    def output(self) -> str:
        return self._out.decode("utf-8", "replace")

    @property
    def errors(self) -> str:
        return self._err.decode("utf-8", "replace")

    @property
    def messages(self) -> list[ScriptMessage]:
        return php_messages(self.errors)

    @property
    def running(self) -> bool:
        return self.state in ("starting", "break", "running")

    async def _pipe(self, stream: asyncio.StreamReader, sink: bytearray) -> None:
        while chunk := await stream.read(65536):
            if len(sink) < LIMIT:
                sink.extend(chunk[: LIMIT - len(sink)])
            if self.on_data is not None:
                self.on_data()

    # ------------------------------------------------------------- start
    async def start(self, timeout: float = CONNECT_TIMEOUT) -> None:
        """Start PHP and wait for Xdebug to connect (the script waits on its first line)."""
        if not self.php:
            raise DebugError("php not found in PATH")
        loop = asyncio.get_running_loop()
        self._connected = loop.create_future()

        def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            if self._connected is not None and not self._connected.done():
                self._connected.set_result((reader, writer))
            else:
                writer.close()  # a second request (a child php): not ours

        self._server = await asyncio.start_server(accept, "127.0.0.1", 0)
        port = self._server.sockets[0].getsockname()[1]
        argv = [
            self.php, *ERROR_INI, *self.ini,
            "-d", "xdebug.mode=debug", "-d", "xdebug.start_with_request=yes",
            "-d", "xdebug.client_host=127.0.0.1", "-d", f"xdebug.client_port={port}",
            "-d", "xdebug.log_level=0",
            str(self.script), *self.args,
        ]
        self._proc = await asyncio.create_subprocess_exec(
            *argv, cwd=str(self.cwd), stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        self._pipes = [asyncio.create_task(self._pipe(self._proc.stdout, self._out)),  # type: ignore[arg-type]
                       asyncio.create_task(self._pipe(self._proc.stderr, self._err))]  # type: ignore[arg-type]
        exited = asyncio.ensure_future(self._proc.wait())
        done, _ = await asyncio.wait({self._connected, exited}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        if self._connected not in done:
            exited.cancel()
            await self._shutdown()
            if not done:
                raise DebugError(f"Xdebug did not connect in {timeout:.0f}s")
            raise DebugError("PHP ended before Xdebug connected: is Xdebug loaded?\n" + self.errors.strip())
        exited.cancel()
        self._reader, self._writer = self._connected.result()
        init = await self._packet()
        if init.tag != f"{{{NS['d']}}}init":
            raise DebugError("Xdebug sent no init packet")
        self.state = "starting"
        for name, value in (("max_depth", "1"), ("max_children", "100"), ("max_data", "2048")):
            await self.command("feature_set", "-n", name, "-v", value)

    async def _packet(self) -> ET.Element:
        assert self._reader is not None
        while not self._ready:
            chunk = await self._reader.read(65536)
            if not chunk:
                raise DebugError("Xdebug closed the connection")
            self._buffer.extend(chunk)
            self._ready.extend(packets(self._buffer))
        return ET.fromstring(self._ready.pop(0))

    async def command(self, name: str, *args: str, data: str | None = None, timeout: float = REPLY_TIMEOUT) -> ET.Element:
        """Send one DBGp command and return its ``<response>``."""
        if self._writer is None:
            raise DebugError("not connected")
        async with self._lock:
            self._tx += 1
            tx = str(self._tx)
            line = " ".join([name, "-i", tx, *args])
            if data is not None:
                line += " -- " + base64.b64encode(data.encode()).decode()
            self._writer.write(line.encode() + b"\0")
            await self._writer.drain()
            while True:
                reply = await asyncio.wait_for(self._packet(), timeout)
                if reply.tag == f"{{{NS['d']}}}response" and reply.get("transaction_id") == tx:
                    return reply

    @staticmethod
    def _error(reply: ET.Element) -> str | None:
        error = reply.find("d:error", NS)
        if error is None:
            return None
        message = error.find("d:message", NS)
        return (message.text if message is not None else None) or f"DBGp error {error.get('code')}"

    # ------------------------------------------------------- breakpoints
    async def set_breakpoint(self, file: Path, line: int, *, temporary: bool = False) -> str | None:
        args = ["-t", "line", "-f", file_uri(file), "-n", str(line)]
        if temporary:
            args += ["-r", "1"]
        reply = await self.command("breakpoint_set", *args)
        return reply.get("id")

    async def remove_breakpoint(self, ident: str) -> None:
        await self.command("breakpoint_remove", "-d", ident)

    # ---------------------------------------------------------- stepping
    async def resume(self, how: str = "run") -> Location | None:
        """``run``, ``step_into``, ``step_over`` or ``step_out``; where it stopped,
        None when the script ended."""
        if self._writer is None:
            return None
        if self.state == "starting" and how in ("step_over", "step_out"):
            how = "step_into"  # from the start Xdebug would run on: stop on the first line
        self.state = "running"
        reply = await self.command(how, timeout=None)  # type: ignore[arg-type]
        self.state = reply.get("status", "stopped")
        if self.state != "break":
            await self._finish()
            return None
        message = reply.find("x:message", NS)
        if message is not None and message.get("lineno"):
            self.location = Location(uri_path(message.get("filename")), int(message.get("lineno", "0")))
        else:
            frames = await self.stack()
            self.location = Location(frames[0].file, frames[0].line) if frames else None
        return self.location

    async def stack(self) -> list[Frame]:
        reply = await self.command("stack_get")
        return [
            Frame(int(f.get("level", "0")), f.get("where", ""), uri_path(f.get("filename")), int(f.get("lineno", "0")))
            for f in reply.findall("d:stack", NS)
        ]

    async def variables(self, depth: int = 0) -> list[Variable]:
        """The local variables of frame ``depth`` (0: where it stopped)."""
        reply = await self.command("context_get", "-d", str(depth), "-c", "0")
        return [variable(p) for p in reply.findall("d:property", NS)]

    async def evaluate(self, expression: str, depth: int = 0) -> Variable:
        """PHP's value of ``expression`` where the script stopped; DebugError says why not."""
        reply = await self.command("eval", "-d", str(depth), data=expression)
        if (problem := self._error(reply)) is not None:
            raise DebugError(problem)
        prop = reply.find("d:property", NS)
        if prop is None:
            return Variable(expression, "null", "null")
        found = variable(prop)
        return Variable(expression, found.type, found.value, found.children)

    # -------------------------------------------------------------- stop
    async def stop(self) -> None:
        """Program reset: end the script now."""
        if self.state == "running" and self._proc is not None and self._proc.returncode is None:
            self._proc.kill()  # busy in PHP: Xdebug would not read a command before the next break
        elif self._writer is not None and self.state != "stopped":
            try:
                await asyncio.wait_for(self.command("stop"), 2)
            except (DebugError, TimeoutError, OSError):
                pass
        await self._shutdown()

    async def _finish(self) -> None:
        """The script ran to its end: let PHP exit and collect what it printed."""
        if self._writer is not None:
            try:
                self._writer.write(f"run -i {self._tx + 1}".encode() + b"\0")  # leave "stopping"
                await self._writer.drain()
            except OSError:
                pass
        await self._shutdown(wait=5.0)

    async def _shutdown(self, wait: float = 2.0) -> None:
        self.state = "stopped"
        self.location = None
        if self._writer is not None:  # PHP waits for the connection to close
            self._writer.close()
            self._writer = None
        if self._proc is not None:
            if self._proc.returncode is None:
                try:
                    await asyncio.wait_for(self._proc.wait(), wait)
                except TimeoutError:
                    self._proc.kill()
                    await self._proc.wait()
            self.exit_code = self._proc.returncode
        if self._pipes:
            await asyncio.gather(*self._pipes, return_exceptions=True)
            self._pipes = []
        if self._server is not None:
            self._server.close()
            self._server = None
