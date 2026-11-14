"""Run PHP scripts (UI-independent).

``php script.php args`` in the script's folder, stdin closed, stdout and
stderr captured apart. PHP is told to print its errors to stderr as plain
text (``display_errors=stderr``, ``html_errors=0``) so they never mix with the
script's output and divide can read them back as messages with a location.
"""

from __future__ import annotations

import asyncio
import re
import shlex
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

LIMIT = 4 * 1024 * 1024  # bytes kept of each stream
ERROR_INI = ["-d", "display_errors=stderr", "-d", "html_errors=0", "-d", "log_errors=0"]

# "Warning: Undefined variable $x in /a/b.php on line 3" (the "PHP " prefix is the log format)
_HEAD = re.compile(
    r"^(?:PHP )?(Fatal error|Parse error|Warning|Notice|Deprecated|Recoverable fatal error"
    r"|Strict Standards|Core Warning|Compile Warning|User Error|User Warning|User Notice|User Deprecated):\s+(.*)$"
)
_WHERE = re.compile(r"\s+(?:thrown )?in (.+?)(?: on line |:)(\d+)\s*$")


@dataclass(frozen=True)
class ScriptMessage:
    level: str  # "error" | "warning"
    text: str
    file: Path | None = None
    line: int | None = None  # 1-based


@dataclass
class ScriptResult:
    output: str = ""
    errors: str = ""  # stderr as PHP printed it
    exit_code: int | None = None
    seconds: float = 0.0
    stopped: bool = False  # ended by the user
    messages: list[ScriptMessage] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return self.stopped or self.exit_code != 0 or any(m.level == "error" for m in self.messages)


class ScriptError(RuntimeError):
    """The script could not start (no PHP)."""


def php_messages(stderr: str) -> list[ScriptMessage]:
    """PHP's errors in ``stderr``; an uncaught exception's trace stays in its message."""
    found: list[ScriptMessage] = []
    block: list[str] = []

    def close() -> None:
        if not block:
            return
        head = _HEAD.match(block[0])
        assert head is not None
        kind, first = head.groups()
        text = "\n".join([first, *block[1:]]).rstrip()
        file = line = None
        for candidate in reversed(text.split("\n")):  # "thrown in ... on line N" ends a trace
            if m := _WHERE.search(candidate):
                file, line = Path(m.group(1)), int(m.group(2))
                break
        summary = text.split("\n")[0]
        if m := _WHERE.search(summary):
            summary = summary[: m.start()]
        level = "error" if "error" in kind.lower() else "warning"
        found.append(ScriptMessage(level, f"{kind}: {summary.strip()}", file, line))
        block.clear()

    for raw in stderr.splitlines():
        if _HEAD.match(raw):
            close()
            block.append(raw)
        elif block and raw.strip():
            block.append(raw)
        else:
            close()
    close()
    return found


def split_args(text: str) -> list[str]:
    """Run > Parameters as the shell would split them (bad quoting: split on spaces)."""
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def command(script: Path, args: list[str], *, php: str | None = None, ini: list[str] | None = None) -> list[str]:
    php = php or shutil.which("php")
    if not php:
        raise ScriptError("php not found in PATH")
    return [php, *ERROR_INI, *(ini or []), str(script), *args]


async def _read(stream: asyncio.StreamReader, sink: bytearray, on_data: Callable[[], None] | None) -> None:
    while chunk := await stream.read(65536):
        if len(sink) < LIMIT:
            sink.extend(chunk[: LIMIT - len(sink)])
        if on_data is not None:
            on_data()


def size_text(data: str | bytes) -> str:
    """``1,234 bytes, 40 lines``"""
    lines = data.count("\n" if isinstance(data, str) else b"\n")
    return f"{len(data):,} bytes, {lines:,} line{'s' if lines != 1 else ''}"


async def run_script(
    script: Path,
    args: list[str] | None = None,
    *,
    cwd: Path | None = None,
    php: str | None = None,
    ini: list[str] | None = None,
    on_data: Callable[[bytes, bytes], None] | None = None,
) -> ScriptResult:
    """Run ``script``; cancelling the task stops PHP (the result then says ``stopped``).

    ``on_data(stdout, stderr)`` sees what came so far, each time more comes."""
    argv = command(script, args or [], php=php, ini=ini)
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd or script.parent),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = bytearray(), bytearray()
    result = ScriptResult()
    seen = (lambda: on_data(bytes(out), bytes(err))) if on_data is not None else None
    try:
        await asyncio.gather(_read(proc.stdout, out, seen), _read(proc.stderr, err, seen))  # type: ignore[arg-type]
        result.exit_code = await proc.wait()
    except asyncio.CancelledError:
        result.stopped = True
        if proc.returncode is None:
            proc.kill()
        result.exit_code = await asyncio.shield(proc.wait())
    result.seconds = time.monotonic() - started
    result.output = out.decode("utf-8", "replace")
    result.errors = err.decode("utf-8", "replace")
    result.messages = php_messages(result.errors)
    return result
