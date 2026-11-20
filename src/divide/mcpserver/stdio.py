"""``divide --mcp PROJECT``: the MCP server over stdio, without the interface.

One JSON-RPC message per line: requests and notifications on stdin, replies
on stdout, anything else on stderr. Standard library only. stdout is kept
for the protocol: what writes to file descriptor 1 (a print, a library, a
process that inherits it) goes to stderr while the server runs. A request
cancelled with ``notifications/cancelled`` stops (PHP with it) and is not
answered. The server ends when stdin closes.
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from pathlib import Path
from typing import BinaryIO

from divide.mcpserver.protocol import (INVALID_REQUEST, Reply, Request, Server, dumps, error_body, parse)
from divide.run import children

MAX_LINE = 16 * 1024 * 1024  # bytes of one message


def _protocol_stdout() -> BinaryIO:
    """The real stdout, for the protocol alone; fd 1 becomes stderr."""
    sys.stdout.flush()
    out = os.fdopen(os.dup(1), "wb", buffering=0)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return out


def _reader(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue, source: BinaryIO) -> None:
    """Lines of stdin into ``queue`` (a thread: stdin cannot be awaited on every platform); None at its end."""
    try:
        while True:
            line = source.readline(MAX_LINE + 1)
            if not line:
                break
            if len(line) > MAX_LINE and not line.endswith(b"\n"):
                while (rest := source.readline(MAX_LINE)) and not rest.endswith(b"\n"):
                    pass
                line = b""  # too long: answered as an invalid request
            loop.call_soon_threadsafe(queue.put_nowait, line)
    except (OSError, ValueError):
        pass
    finally:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, None)
        except RuntimeError:  # the loop is gone
            pass


async def serve(root: Path, source: BinaryIO, out: BinaryIO) -> None:
    server = Server(root, log=lambda text: print(f"divide --mcp: {text}", file=sys.stderr, flush=True))
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    threading.Thread(target=_reader, args=(loop, queue, source), name="mcp-stdin", daemon=True).start()
    running: set[asyncio.Task] = set()

    def send(body: dict) -> None:
        out.write(dumps(body) + b"\n")
        out.flush()

    async def answer(message: dict) -> None:
        reply = await server.handle(Request(message))
        if reply.body is not None and not reply.cancelled:
            send(reply.body)

    while (line := await queue.get()) is not None:
        if not line.strip():
            if line == b"":  # a line too long
                send(error_body(None, INVALID_REQUEST, f"Invalid Request: a message of more than {MAX_LINE:,} bytes"))
            continue
        message = parse(line.strip())
        if isinstance(message, Reply):
            send(message.body)  # type: ignore[arg-type]
            continue
        if "id" not in message:  # notifications at once: a cancellation must not wait behind calls
            await server.handle(Request(message))
            continue
        task = asyncio.create_task(answer(message))
        running.add(task)
        task.add_done_callback(running.discard)
    for task in list(running):  # the client left: what it asked no longer matters
        task.cancel()
    await asyncio.gather(*running, return_exceptions=True)


def main(root: str | None) -> int:
    """``divide --mcp PROJECT``; errors on stderr (stdout is the protocol's)."""
    if root is None:
        print("divide --mcp: give the project's folder (divide --mcp /path/to/project)", file=sys.stderr)
        return 2
    path = Path(root).expanduser()
    if not path.is_dir():
        print(f"divide --mcp: {root} is not a folder", file=sys.stderr)
        return 2
    out = _protocol_stdout()
    try:
        asyncio.run(serve(path, sys.stdin.buffer, out))
    except KeyboardInterrupt:
        pass
    finally:
        children.kill_all()
    return 0
