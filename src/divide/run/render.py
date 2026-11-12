"""Render Div templates through PHP (UI-independent).

Div is PHP, so rendering runs ``php bridge.php`` with a JSON request on stdin
(engine, template path, template source, data) and reads a JSON reply. The
template source comes from the editor, so unsaved changes are rendered; its
real path is passed too, so relative includes resolve as in production.

Engine lookup (first hit wins): the ``DIVIDE_DIV_PHP`` environment variable,
the configured path, then ``vendor/autoload.php`` (with
``vendor/divengine/div``) walking up from the template and the project root.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from divide.lang.div.dialect import lenient_json
from divide.lang.divjson import references

BRIDGE = Path(__file__).with_name("bridge.php")
ENV_ENGINE = "DIVIDE_DIV_PHP"
DATA_EXT = ".json"  # DIV_DEFAULT_DATA_FILE_EXT
TIMEOUT = 20.0

# Levels from the bridge: Div's WARNING / FATAL, PHP notices, deprecations.
SERIOUS = {"FATAL", "WARNING", "PHP", "DATA"}


@dataclass
class RenderMessage:
    level: str
    text: str


@dataclass
class RenderResult:
    output: str = ""
    messages: list[RenderMessage] = field(default_factory=list)
    fatal: bool = False
    version: str | None = None
    seconds: float = 0.0

    @property
    def serious(self) -> list[RenderMessage]:
        return [m for m in self.messages if m.level in SERIOUS]


class RenderError(RuntimeError):
    """Rendering could not run at all (no PHP, no Div, broken bridge)."""


def _engine_ok(path: Path) -> bool:
    return path.is_file() and path.suffix == ".php"


def find_engine(start_dirs: list[Path], configured: str | None = None) -> Path | None:
    """Locate Div: an ``autoload.php`` of a composer install or a ``div.php``."""
    for candidate in (os.environ.get(ENV_ENGINE), configured):
        if candidate:
            path = Path(candidate).expanduser()
            if _engine_ok(path):
                return path.resolve()
    seen: set[Path] = set()
    for start in start_dirs:
        for folder in [start, *start.parents]:
            if folder in seen:
                break
            seen.add(folder)
            autoload = folder / "vendor" / "autoload.php"
            if autoload.is_file() and (folder / "vendor" / "divengine" / "div").is_dir():
                return autoload.resolve()
    return None


def default_data_file(template: Path) -> Path:
    """Div's own convention: ``page.tpl`` takes its data from ``page.json``."""
    return template.with_suffix(DATA_EXT)


_STRING_OR_COMMENT = re.compile(r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|//[^\n]*|/\*.*?\*/""", re.DOTALL)


def strip_comments(text: str) -> str:
    """Drop ``//`` and ``/* */`` comments outside strings."""
    return _STRING_OR_COMMENT.sub(lambda m: "" if m.group().startswith("/") else m.group(), text)


def check_data(text: str) -> str | None:
    """Quick editor-side check of data JSON (Div's own parser has the last word at render time)."""
    stripped = strip_comments(text).strip()
    if not stripped:
        return None
    try:
        value = lenient_json(stripped)
    except ValueError as exc:
        return f"data is not valid JSON ({exc}); Div will render without data"
    if not isinstance(value, (dict, list)):
        return "data must be a JSON object; Div will render without data"
    return None


async def render(
    engine: Path,
    template: Path,
    code: str,
    data: str | None,
    *,
    cwd: Path,
    php: str | None = None,
    timeout: float = TIMEOUT,
) -> RenderResult:
    """Render ``code`` (the source of ``template``) with ``data`` (JSON text)."""
    php = php or shutil.which("php")
    if not php:
        raise RenderError("php not found in PATH")
    request = json.dumps({"engine": str(engine), "path": str(template), "code": code, "data": data})
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        php,
        str(BRIDGE),
        cwd=str(cwd),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(request.encode()), timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise RenderError(f"rendering took longer than {timeout:.0f}s and was stopped") from None
    try:
        reply = json.loads(out.decode("utf-8", "replace"))
    except ValueError:
        detail = (err or out).decode("utf-8", "replace").strip()[:500]
        raise RenderError(f"php bridge failed (exit {proc.returncode}): {detail}") from None
    result = RenderResult(
        output=reply.get("output") or "",
        messages=[RenderMessage(m.get("level", "?"), m.get("text", "")) for m in reply.get("messages", [])],
        fatal=bool(reply.get("fatal")),
        version=reply.get("version"),
        seconds=time.monotonic() - started,
    )
    if data and (refs := references(data)):
        names = ", ".join("$" + r for r in dict.fromkeys(refs))
        result.messages.append(
            RenderMessage(
                "NOTE",
                f"the data uses {names}: Div decodes a data file before any variable exists, "
                "so these come out empty (they work in {= var: {...} =} inside templates)",
            )
        )
    return result
