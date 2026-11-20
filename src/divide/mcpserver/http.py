"""divide's MCP server over Streamable HTTP, inside the IDE (standard library only).

One endpoint, ``POST /mcp``; each POST carries one JSON-RPC message and gets
one JSON answer (``application/json``: no SSE stream is ever opened, which
both eras allow). GET and DELETE get 405: there are no sessions and no
server-to-client stream.

Threads, all owned by :class:`HttpServer` and gone after :meth:`HttpServer.stop`:

- the listener (``http.server.ThreadingHTTPServer``), one short-lived thread
  per connection;
- one asyncio loop, where every tool call runs (the same coroutines as on
  stdio). A connection's thread hands its request to the loop and waits;
  if the client closes the connection meanwhile, the call is cancelled and
  PHP stops (closing the connection is how a client cancels on HTTP).

Textual's loop never waits on any of this: :meth:`start` binds and returns,
:meth:`stop` is meant to run in a worker thread (``asyncio.to_thread``).

Protection: the server binds to loopback by default. Host and Origin are
checked (a web page cannot reach it through DNS rebinding, and since CORS is
never answered, a browser cannot post JSON to it). Off loopback a bearer
token is required. Bodies, connections, concurrent calls and their time are
bounded. Nothing secret is logged (no headers, no arguments).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import errno
import hmac
import ipaddress
import os
import secrets
import select
import socket
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from divide import config
from divide.mcpserver.protocol import INVALID_REQUEST, Reply, Request, Server, dumps, error_body, parse

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PATH = "/mcp"
MAX_BODY = 16 * 1024 * 1024  # bytes of one request (a template and its data of up to 4M characters each)
MAX_CONNECTIONS = 32
MAX_REQUEST_SECONDS = 300.0  # no call outlives this, whatever its own timeout
IDLE_SECONDS = 30.0  # a kept-alive connection with nothing to say is closed
LOG_LINES = 200
LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}


class StartError(RuntimeError):
    """The server could not start: the port is taken, the host is not this machine's..."""


def is_loopback(host: str) -> bool:
    host = host.strip().strip("[]")
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_host(host: str) -> str | None:
    """Why ``host`` cannot be served, or None."""
    host = host.strip()
    if not host or any(c.isspace() for c in host) or "/" in host:
        return "the host is an address of this machine, as 127.0.0.1"
    return None


def split_host(value: str) -> tuple[str, str] | None:
    """A Host header as (lower-case name, port): ``name:port``, ``[::1]:port`` or a bare name."""
    value = value.strip()
    if not value:
        return None
    if value.startswith("["):
        end = value.find("]")
        if end < 0:
            return None
        name, rest = value[1:end], value[end + 1:]
        if rest and not rest.startswith(":"):
            return None
        port = rest[1:]
    else:
        name, _sep, port = value.partition(":")
    return name.lower(), port


def url_of(host: str, port: int) -> str:
    shown = host.strip().strip("[]")
    if ":" in shown:
        shown = f"[{shown}]"
    return f"http://{shown}:{port}{PATH}"


# ---------------------------------------------------------------- token
def token_path() -> Path:
    """Where the bearer token lives (beside config.json, readable by the user alone)."""
    return config.config_path().parent / "mcp-token"


def load_token(*, create: bool = False, renew: bool = False) -> str | None:
    path = token_path()
    if not renew:
        try:
            token = path.read_text(encoding="ascii").strip()
            if len(token) >= 32:
                return token
        except (OSError, UnicodeDecodeError):
            pass
    if not (create or renew):
        return None
    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".new")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(token + "\n")
    os.replace(tmp, path)
    return token


# ---------------------------------------------------------------- the server
@dataclass
class Logged:
    when: float
    text: str


class _Listener(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 16
    allow_reuse_address = sys.platform != "win32"  # on Windows it would let two servers share the port

    def __init__(self, address: tuple, family: int, owner: HttpServer) -> None:
        self.address_family = family
        self.owner = owner
        self.open: set[socket.socket] = set()
        self.lock = threading.Lock()
        super().__init__(address, _Handler)

    def server_bind(self) -> None:
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)  # type: ignore[attr-defined]
        if self.address_family == socket.AF_INET6:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        socket.socket.bind(self.socket, self.server_address)  # HTTPServer.server_bind would look up a name
        self.server_address = self.socket.getsockname()

    def process_request(self, request, client_address) -> None:
        with self.lock:
            full = len(self.open) >= MAX_CONNECTIONS
            if not full:
                self.open.add(request)
        if full:
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nRetry-After: 1\r\nContent-Length: 0\r\n"
                                b"Connection: close\r\n\r\n")
            except OSError:
                pass
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def shutdown_request(self, request) -> None:
        with self.lock:
            self.open.discard(request)
        super().shutdown_request(request)

    def handle_error(self, request, client_address) -> None:  # a client that went away mid-answer
        self.owner._note(f"connection error: {sys.exc_info()[1]}")

    def close_connections(self) -> None:
        with self.lock:
            open_now = list(self.open)
        for request in open_now:
            try:
                request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "divide-mcp"
    sys_version = ""
    timeout = IDLE_SECONDS
    server: _Listener

    def log_message(self, format: str, *args: Any) -> None:  # nothing on stderr, nothing of the request's
        pass

    # ---------------------------------------------------------- answers
    def _send(self, status: int, body: dict | None = None, headers: dict[str, str] | None = None, *,
              close: bool = False) -> None:
        data = dumps(body) if body is not None else b""
        self.send_response(status)
        if body is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        if close:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        if data:
            self.wfile.write(data)

    def _refuse(self, status: int, text: str, headers: dict[str, str] | None = None, *, close: bool = False) -> None:
        self.server.owner._note(f"{self.command} {status}: {text}")
        self._send(status, error_body(None, INVALID_REQUEST, text), headers, close=close)

    def do_GET(self) -> None:
        self._no_method()

    do_DELETE = do_PUT = do_PATCH = do_OPTIONS = do_HEAD = do_GET  # type: ignore[assignment]

    def _no_method(self) -> None:
        if urlsplit(self.path).path != PATH:
            self._send(404, None)
            return
        self._send(405, None, {"Allow": "POST"})

    # ---------------------------------------------------------- checks
    def _host_ok(self) -> bool:
        owner = self.server.owner
        host = split_host(self.headers.get("Host") or "")
        if host is None:
            return False
        if not owner.loopback:
            return True  # a token guards it; a reverse proxy may give any name
        name, port = host
        return (name in LOOPBACK_NAMES or name == owner.host.strip("[]").lower()) and port == str(owner.port)

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        try:
            host = urlsplit(origin).hostname
        except ValueError:
            return False
        return host is not None and is_loopback(host)

    def _authorized(self) -> bool:
        token = self.server.owner.token
        if token is None:
            return True
        given = self.headers.get("Authorization", "")
        scheme, _sep, value = given.partition(" ")
        return scheme.lower() == "bearer" and hmac.compare_digest(value.strip().encode(), token.encode())

    # ---------------------------------------------------------- POST
    def do_POST(self) -> None:
        owner = self.server.owner
        if urlsplit(self.path).path != PATH:
            self._send(404, None, close=True)
            return
        if not self._host_ok():
            self._refuse(403, "Forbidden: the Host header does not name this server", close=True)
            return
        if not self._origin_ok():
            self._refuse(403, "Forbidden: requests from web pages are refused (Origin)", close=True)
            return
        if not self._authorized():
            self._refuse(401, "Unauthorized: a bearer token is required", {"WWW-Authenticate": 'Bearer realm="divide"'},
                         close=True)
            return
        kind = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if kind != "application/json":
            self._refuse(415, "Unsupported Media Type: the body is application/json", close=True)
            return
        accept = self.headers.get("Accept")
        if accept is not None and not any(a.split(";")[0].strip() in ("application/json", "application/*", "*/*")
                                          for a in accept.split(",")):
            self._refuse(406, "Not Acceptable: the answer is application/json", close=True)
            return
        if self.headers.get("Transfer-Encoding"):
            self._refuse(411, "Length Required: send Content-Length (no chunked bodies)", close=True)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._refuse(411, "Length Required", close=True)
            return
        if not 0 <= length <= MAX_BODY:
            self._refuse(413, f"Payload Too Large: up to {MAX_BODY:,} bytes", close=True)
            return
        try:
            raw = self.rfile.read(length)
        except (OSError, TimeoutError):
            self.close_connection = True
            return
        if len(raw) < length:
            self.close_connection = True
            return
        message = parse(raw)
        if isinstance(message, Reply):
            owner._note(f"POST 400: {message.body['error']['message']}")  # type: ignore[index]
            self._send(message.status, message.body)
            return
        headers = {name.lower(): value for name, value in self.headers.items()}
        started = time.monotonic()
        reply = owner._run(Request(message, headers=headers, scope=id(self.connection)), self.connection)
        if reply is None:  # the client left, or the server stopped: nobody to answer
            self.close_connection = True
            return
        owner._served(message, reply, time.monotonic() - started)
        try:
            self._send(reply.status, reply.body)
        except OSError:
            self.close_connection = True


class HttpServer:
    """divide's MCP server for the project at ``root``, on ``host:port``, while divide runs."""

    def __init__(self, root: Path, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *,
                 token: str | None = None) -> None:
        self.root = Path(root)
        self.host = host.strip() or DEFAULT_HOST
        self.port = port
        self.loopback = is_loopback(self.host)
        if not self.loopback and not token:
            raise StartError("off this machine's loopback the server needs a token")
        self.token = token
        self.state = "stopped"  # starting, running, stopping, stopped, failed
        self.error: str | None = None
        self.requests = 0
        self.log: deque[Logged] = deque(maxlen=LOG_LINES)
        self.mcp: Server | None = None
        self._listener: _Listener | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._threads: list[threading.Thread] = []
        self._pending: set[concurrent.futures.Future] = set()
        self._lock = threading.Lock()

    # ---------------------------------------------------------- state
    @property
    def url(self) -> str:
        return url_of(self.host, self.port)

    @property
    def running(self) -> bool:
        return self.state == "running"

    @property
    def active(self) -> int:
        return len(self._pending)

    @property
    def clients(self) -> dict[str, str]:
        return dict(self.mcp.clients) if self.mcp is not None else {}

    def alive(self) -> bool:
        """Running, with its threads: False after a stop or once something killed them."""
        return self.running and all(t.is_alive() for t in self._threads)

    def _note(self, text: str) -> None:
        self.log.append(Logged(time.time(), text))

    def _served(self, message: dict, reply: Reply, seconds: float) -> None:
        self.requests += 1
        method = message.get("method", "?")
        name = (message.get("params") or {}).get("name") if method == "tools/call" else None
        what = f"{method} {name}" if isinstance(name, str) else str(method)
        failed = reply.body is not None and "error" in reply.body
        tool_error = reply.body is not None and (reply.body.get("result") or {}).get("isError")
        outcome = "error" if failed else ("tool error" if tool_error else "ok")
        self._note(f"{what} [{reply.era} {reply.version or ''}] {reply.status} {outcome} {seconds:.2f}s")

    # ---------------------------------------------------------- start, stop
    def start(self) -> None:
        """Bind and serve; StartError says why it could not. Returns at once (the work is in threads)."""
        if self.state in ("running", "starting"):
            return
        self.state, self.error = "starting", None
        try:
            infos = socket.getaddrinfo(self.host.strip("[]"), self.port, type=socket.SOCK_STREAM,
                                       flags=socket.AI_NUMERICSERV)
        except (OSError, UnicodeError) as exc:
            self._failed(f"{self.host} is not an address of this machine ({exc})")
        infos.sort(key=lambda info: info[0] != socket.AF_INET)  # localhost: 127.0.0.1 before ::1
        family, _type, _proto, _name, address = infos[0]
        try:
            self.mcp = Server(self.root, log=self._note)
        except OSError as exc:
            self._failed(f"the project folder cannot be served: {exc}")
        try:
            listener = _Listener(address, family, self)
        except OSError as exc:
            if exc.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1)) or getattr(exc, "winerror", None) == 10048:
                self._failed(f"port {self.port} is in use: another program (or another divide) listens on it")
            if exc.errno in (errno.EACCES, getattr(errno, "WSAEACCES", -1)):
                self._failed(f"port {self.port} needs rights this user lacks (choose one above 1024)")
            if exc.errno == errno.EADDRNOTAVAIL:
                self._failed(f"{self.host} is not an address of this machine")
            self._failed(f"cannot listen on {self.host}:{self.port}: {exc.strerror or exc}")
        self._listener = listener
        self.port = listener.server_address[1]  # port 0: the one the system gave
        loop = asyncio.new_event_loop()
        self._loop = loop
        ready = threading.Event()
        self._threads = [
            threading.Thread(target=self._run_loop, args=(loop, ready), name="mcp-loop", daemon=True),
            threading.Thread(target=self._serve, args=(listener,), name="mcp-http", daemon=True),
        ]
        self._threads[0].start()
        ready.wait(5)
        self._threads[1].start()
        self.state = "running"
        self._note(f"serving {self.root} at {self.url}")

    def _failed(self, text: str) -> None:
        self.state, self.error = "failed", text
        self._note(f"could not start: {text}")
        raise StartError(text)

    def _run_loop(self, loop: asyncio.AbstractEventLoop, ready: threading.Event) -> None:
        asyncio.set_event_loop(loop)
        loop.call_soon(ready.set)
        try:
            loop.run_forever()
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()

    def _serve(self, listener: _Listener) -> None:
        try:
            listener.serve_forever(poll_interval=0.25)
        except Exception as exc:  # the listener died: say so, the IDE shows it
            self.error = f"the server stopped: {type(exc).__name__}: {exc}"
            self.state = "failed"
            self._note(self.error)

    def stop(self, timeout: float = 5.0) -> None:
        """Stop serving: calls in progress are cancelled (their PHP stops), connections close, the threads end.
        Blocks up to about ``timeout`` seconds: run it off Textual's loop."""
        if self.state in ("stopped",) or self._listener is None:
            self.state = "stopped" if self.state != "failed" else self.state
            return
        failed = self.state == "failed"
        self.state = "stopping"
        listener, loop = self._listener, self._loop
        if self._threads and self._threads[1].is_alive():
            listener.shutdown()  # serve_forever returns (within its poll interval)
        listener.server_close()
        with self._lock:
            pending = list(self._pending)
        for future in pending:
            future.cancel()  # the coroutine is cancelled in the loop: PHP is killed there
        listener.close_connections()
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(loop.stop)
        deadline = time.monotonic() + timeout
        for thread in self._threads:
            thread.join(max(0.1, deadline - time.monotonic()))
        self._listener, self._loop, self._threads = None, None, []
        self.state = "failed" if failed else "stopped"
        self._note("stopped")

    # ---------------------------------------------------------- requests
    def _run(self, request: Request, connection: socket.socket) -> Reply | None:
        """``request`` answered in the loop; None when the client closed the connection (the call is
        cancelled), the server stopped, or the call ran past MAX_REQUEST_SECONDS."""
        loop, mcp = self._loop, self.mcp
        if loop is None or mcp is None or self.state != "running":
            return None
        try:
            future = asyncio.run_coroutine_threadsafe(mcp.handle(request), loop)
        except RuntimeError:  # the loop is closing
            return None
        with self._lock:
            self._pending.add(future)
        try:
            deadline = time.monotonic() + MAX_REQUEST_SECONDS
            while True:
                try:
                    return future.result(timeout=0.2)
                except concurrent.futures.TimeoutError:
                    pass
                except concurrent.futures.CancelledError:
                    return None
                if _gone(connection) or time.monotonic() > deadline or self.state != "running":
                    future.cancel()
                    if time.monotonic() > deadline:
                        self._note(f"{request.message.get('method')}: stopped after {MAX_REQUEST_SECONDS:.0f}s")
                    else:
                        self._note(f"{request.message.get('method')}: the client left, the call is cancelled")
                    return None
        finally:
            with self._lock:
                self._pending.discard(future)


def _gone(connection: socket.socket) -> bool:
    """The client closed ``connection`` (what it may still have sent is left unread)."""
    try:
        readable, _w, _x = select.select([connection], [], [], 0)
        if not readable:
            return False
        return connection.recv(1, socket.MSG_PEEK) == b""
    except (OSError, ValueError):
        return True
