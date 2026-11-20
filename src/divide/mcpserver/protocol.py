"""MCP's JSON-RPC for divide's tools, the same on every transport.

Both eras of the protocol are served (a dual-era server, as the 2026-07-28
revision calls it):

- **modern** (2026-07-28): stateless. Every request carries its protocol
  version in ``params._meta``; ``server/discover`` says what the server
  speaks; every result carries ``resultType`` and the server's identity.
- **legacy** (2024-11-05 to 2025-11-25): the ``initialize`` handshake, then
  ``tools/list`` and ``tools/call``. Over HTTP no session is kept: each POST
  stands alone, so a server stopped and started again from divide goes on
  serving the clients that knew it.

Only tools are served (no resources, prompts, logging or server-to-client
requests): the seven tools of :mod:`divide.mcpserver.tools`.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from divide import __version__
from divide.mcpserver import tools
from divide.mcpserver.tools import INSTRUCTIONS, Project, ToolError

MODERN = ("2026-07-28",)
LEGACY = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
SUPPORTED = MODERN + LEGACY
ASSUMED = "2025-03-26"  # an HTTP request without MCP-Protocol-Version (the transport's rule)

META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT = "io.modelcontextprotocol/clientInfo"
META_SERVER = "io.modelcontextprotocol/serverInfo"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
HEADER_MISMATCH = -32020
UNSUPPORTED_VERSION = -32022

MAX_CALLS = 4  # tool calls running at once (each may run PHP); the next ones wait
LIST_TTL_MS = 3_600_000  # the tools never change while the server runs

SERVER_INFO = {"name": "divide", "title": "divide", "version": __version__,
               "websiteUrl": "https://github.com/divengine/divide"}
CAPABILITIES = {"tools": {"listChanged": False}}


class RpcError(Exception):
    """A JSON-RPC error answer; ``status`` is the HTTP status it goes with."""

    def __init__(self, code: int, message: str, *, data: Any = None, status: int = 200) -> None:
        super().__init__(message)
        self.code, self.message, self.data, self.status = code, message, data, status


class Cancelled(RpcError):
    """The client cancelled the request with notifications/cancelled."""

    def __init__(self) -> None:
        super().__init__(INTERNAL_ERROR, "Request cancelled by the client")


@dataclass
class Reply:
    """What a message gets back: a JSON-RPC message (None for a notification) and an HTTP status."""

    body: dict[str, Any] | None
    status: int = 200
    era: str = "legacy"
    version: str | None = None
    cancelled: bool = False  # by notifications/cancelled: stdio sends nothing for it


@dataclass
class Call:
    """A request in progress, for cancellation and for the server's status."""

    ident: Any
    scope: Any
    method: str
    name: str | None
    task: asyncio.Task | None = None
    cancelled: bool = False


@dataclass
class Request:
    """A decoded JSON-RPC request and what the transport knows about it."""

    message: dict[str, Any]
    headers: Mapping[str, str] | None = None  # HTTP's (lower-case names); None on stdio
    scope: Any = None  # the connection, for a notifications/cancelled on stdio
    extra: dict[str, Any] = field(default_factory=dict)


def error_body(ident: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": ident, "error": err}


def unsupported(requested: Any) -> RpcError:
    return RpcError(UNSUPPORTED_VERSION, "Unsupported protocol version",
                    data={"supported": list(SUPPORTED), "requested": requested}, status=400)


def _decoded(value: str) -> str:
    """An ``Mcp-Name`` header's value, its ``=?base64?...?=`` form decoded."""
    if value.startswith("=?base64?") and value.endswith("?="):
        try:
            return base64.b64decode(value[9:-2], validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            raise RpcError(HEADER_MISMATCH, "Header mismatch: Mcp-Name is not valid base64", status=400) from None
    return value


class Server:
    """divide's MCP server for one project, whatever carries its messages."""

    def __init__(self, root: Path, *, log: Callable[[str], None] | None = None) -> None:
        self.project = Project(root)
        self.log = log or (lambda text: None)
        self.calls: list[Call] = []
        self._slots: asyncio.Semaphore | None = None
        self.clients: dict[str, str] = {}  # the clients that said who they are: name -> version

    # ---------------------------------------------------------- era
    def era(self, request: Request) -> tuple[str, str]:
        """``("modern" | "legacy", version)`` of ``request``, or the RpcError it gets."""
        message, headers = request.message, request.headers
        params = message.get("params")
        meta = params.get("_meta") if isinstance(params, dict) else None
        stated = meta.get(META_VERSION) if isinstance(meta, dict) else None
        header = headers.get("mcp-protocol-version") if headers is not None else None
        if message.get("method") == "initialize":
            return "legacy", LEGACY[0]
        if stated is not None:
            if stated in MODERN:
                if headers is not None:
                    self._check_headers(message, headers, stated)
                return "modern", stated
            if stated in LEGACY:
                return "legacy", stated
            raise unsupported(stated)
        if header is None:
            return "legacy", ASSUMED if headers is not None else LEGACY[0]
        if header in MODERN:
            raise RpcError(HEADER_MISMATCH, f"Header mismatch: MCP-Protocol-Version is {header} but the request's "
                                            f"_meta has no {META_VERSION}", status=400)
        if header in LEGACY:
            return "legacy", header
        raise unsupported(header)

    @staticmethod
    def _check_headers(message: dict[str, Any], headers: Mapping[str, str], version: str) -> None:
        def mismatch(text: str) -> RpcError:
            return RpcError(HEADER_MISMATCH, f"Header mismatch: {text}", status=400)

        header = headers.get("mcp-protocol-version")
        if header is None:
            raise mismatch("the MCP-Protocol-Version header is missing")
        if header != version:
            raise mismatch(f"MCP-Protocol-Version header value '{header}' does not match body value '{version}'")
        method = headers.get("mcp-method")
        if method is None:
            raise mismatch("the Mcp-Method header is missing")
        if method != message.get("method"):
            raise mismatch(f"Mcp-Method header value '{method}' does not match body value '{message.get('method')}'")
        if message.get("method") in ("tools/call", "resources/read", "prompts/get"):
            params = message.get("params") or {}
            body = params.get("name") if message["method"] != "resources/read" else params.get("uri")
            name = headers.get("mcp-name")
            if name is None:
                raise mismatch("the Mcp-Name header is missing")
            if _decoded(name) != body:
                raise mismatch(f"Mcp-Name header value '{name}' does not match body value '{body}'")

    # ---------------------------------------------------------- messages
    async def handle(self, request: Request) -> Reply:
        """The reply to one JSON-RPC message (already decoded, a JSON object)."""
        message = request.message
        ident = message.get("id")
        method = message.get("method")
        is_request = "id" in message
        if message.get("jsonrpc") != "2.0" or (method is None and not is_request):
            return Reply(error_body(ident, INVALID_REQUEST, "Invalid Request: not a JSON-RPC 2.0 message"), 400)
        if method is None:  # a response from the client: this server asks nothing
            return Reply(None, 202)
        if not isinstance(method, str) or (is_request and (ident is None or isinstance(ident, (bool, dict, list)))):
            return Reply(error_body(ident, INVALID_REQUEST, "Invalid Request: method or id"), 400)
        if not is_request:
            self._notified(message)
            return Reply(None, 202)
        try:
            era, version = self.era(request)
        except RpcError as exc:
            return Reply(error_body(ident, exc.code, exc.message, exc.data), exc.status)
        params = message.get("params")
        if params is not None and not isinstance(params, dict):
            return Reply(error_body(ident, INVALID_PARAMS, "Invalid params: an object"), 200, era, version)
        params = params or {}
        self._remember_client(params, era)
        try:
            result = await self._method(era, method, params, request)
        except RpcError as exc:
            status = exc.status if exc.code != METHOD_NOT_FOUND else (404 if era == "modern" and request.headers is not None else 200)
            return Reply(error_body(ident, exc.code, exc.message, exc.data), status, era, version,
                         cancelled=isinstance(exc, Cancelled))
        if era == "modern":
            result = {"resultType": "complete", **result, "_meta": {META_SERVER: SERVER_INFO}}
        return Reply({"jsonrpc": "2.0", "id": ident, "result": result}, 200, era, version)

    def _remember_client(self, params: dict[str, Any], era: str) -> None:
        info = params.get("clientInfo") if era == "legacy" else (params.get("_meta") or {}).get(META_CLIENT)
        if isinstance(info, dict) and isinstance(info.get("name"), str):
            if len(self.clients) < 32 or info["name"] in self.clients:
                self.clients[info["name"][:80]] = str(info.get("version", ""))[:40]

    async def _method(self, era: str, method: str, params: dict[str, Any], request: Request) -> dict[str, Any]:
        if method == "initialize":
            asked = params.get("protocolVersion")
            return {"protocolVersion": asked if asked in LEGACY else LEGACY[0], "capabilities": CAPABILITIES,
                    "serverInfo": SERVER_INFO, "instructions": INSTRUCTIONS}
        if method == "server/discover":
            if era != "modern":
                raise RpcError(METHOD_NOT_FOUND, "Method not found: server/discover (a 2026-07-28 request; "
                                                 f"this server supports {', '.join(SUPPORTED)})")
            return {"supportedVersions": list(SUPPORTED), "capabilities": CAPABILITIES, "instructions": INSTRUCTIONS,
                    "ttlMs": LIST_TTL_MS, "cacheScope": "private"}
        if method == "ping" and era == "legacy":
            return {}
        if method == "tools/list":
            listed: dict[str, Any] = {"tools": [tool.listing() for tool in tools.TOOLS]}
            if era == "modern":
                listed.update(ttlMs=LIST_TTL_MS, cacheScope="private")
            return listed
        if method == "tools/call":
            return await self._call_tool(params, request)
        raise RpcError(METHOD_NOT_FOUND, f"Method not found: {method}")

    async def _call_tool(self, params: dict[str, Any], request: Request) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str) or name not in tools.BY_NAME:
            raise RpcError(INVALID_PARAMS, f"Unknown tool: {name} (the tools: {', '.join(tools.BY_NAME)})")
        call = Call(request.message.get("id"), request.scope, "tools/call", name, asyncio.current_task())
        self.calls.append(call)
        if self._slots is None:
            self._slots = asyncio.Semaphore(MAX_CALLS)
        try:
            async with self._slots:
                answer = await tools.call(self.project, name, params.get("arguments"))
        except ToolError as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        except asyncio.CancelledError:
            if call.cancelled:  # by notifications/cancelled: the request ends here, unanswered
                if call.task is not None:
                    call.task.uncancel()
                raise Cancelled() from None
            raise
        except Exception as exc:  # a bug of divide's: said, not a crash of the server
            self.log(f"{name}: internal error: {type(exc).__name__}: {exc}")
            return {"content": [{"type": "text", "text": f"internal error in divide: {type(exc).__name__}: {exc}"}],
                    "isError": True}
        finally:
            self.calls.remove(call)
        return {"content": [{"type": "text", "text": json.dumps(answer, ensure_ascii=False)}], "structuredContent": answer}

    def _notified(self, message: dict[str, Any]) -> None:
        if message.get("method") != "notifications/cancelled":
            return
        params = message.get("params") or {}
        wanted = params.get("requestId") if isinstance(params, dict) else None
        if wanted is None:
            return
        self.cancel(wanted)

    def cancel(self, ident: Any, scope: Any = None) -> bool:
        """Cancel the call with the request id ``ident``: the one of ``scope`` (stdio), or the only one with
        that id (HTTP, where ids of different clients may repeat: an ambiguous one is left running)."""
        matching = [c for c in self.calls if c.ident == ident and (scope is None or c.scope == scope)]
        if len(matching) != 1 or matching[0].task is None:
            return False
        matching[0].cancelled = True
        matching[0].task.cancel()
        return True


def parse(raw: bytes) -> dict[str, Any] | Reply:
    """A request body or a stdio line as a JSON-RPC message, or the error Reply it gets."""
    try:
        message = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return Reply(error_body(None, PARSE_ERROR, "Parse error: not JSON (UTF-8)"), 400)
    if isinstance(message, list):
        return Reply(error_body(None, INVALID_REQUEST, "Invalid Request: one JSON-RPC message per request (no batches)"), 400)
    if not isinstance(message, dict):
        return Reply(error_body(None, INVALID_REQUEST, "Invalid Request: a JSON object"), 400)
    return message


def dumps(body: dict[str, Any]) -> bytes:
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
