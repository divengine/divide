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


async def _call_bridge(request: dict, *, cwd: Path, php: str | None, timeout: float) -> dict:
    php = php or shutil.which("php")
    if not php:
        raise RenderError("php not found in PATH")
    proc = await asyncio.create_subprocess_exec(
        php,
        str(BRIDGE),
        cwd=str(cwd),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(json.dumps(request).encode()), timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise RenderError(f"php took longer than {timeout:.0f}s and was stopped") from None
    except asyncio.CancelledError:  # stopped from the progress box
        proc.kill()
        await asyncio.shield(proc.wait())
        raise
    try:
        reply = json.loads(out.decode("utf-8", "replace"))
    except ValueError:
        detail = (err or out).decode("utf-8", "replace").strip()[:500]
        raise RenderError(f"php bridge failed (exit {proc.returncode}): {detail}") from None
    return reply if isinstance(reply, dict) else {}


@dataclass(frozen=True)
class IncludeTarget:
    """Where Div takes an include: ``path`` is the include without its data part."""

    path: str
    file: Path | None


async def resolve_includes(
    engine: Path,
    template: Path,
    includes: list[str],
    *,
    cwd: Path,
    history: list[Path] | None = None,
    separator: str | None = None,
    php: str | None = None,
    timeout: float = 10.0,
) -> dict[str, IncludeTarget]:
    """Ask Div (``getTplPath``, with the template's path) where each include leads.

    ``cwd`` must be the one renders use: Div tries paths relative to it first.
    """
    request: dict = {
        "engine": str(engine), "op": "resolve", "path": str(template),
        "includes": includes, "history": [str(h) for h in history or []],
    }
    if separator is not None:
        request["separator"] = separator
    reply = await _call_bridge(request, cwd=cwd, php=php, timeout=timeout)
    out: dict[str, IncludeTarget] = {}
    for raw, item in (reply.get("resolved") or {}).items():
        if isinstance(item, dict):
            file = item.get("file")
            out[raw] = IncludeTarget(str(item.get("path", raw)), (cwd / file).resolve() if file else None)
    return out


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
    request = {"engine": str(engine), "path": str(template), "code": code, "data": data}
    started = time.monotonic()
    reply = await _call_bridge(request, cwd=cwd, php=php, timeout=timeout)
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


@dataclass(frozen=True)
class DialectVerdict:
    """What Div says about a dialect.

    ``reason`` is Div's complaint (``isValidCurrentDialect()``), None when valid.
    ``translated``: the sample as Div read it back into its default dialect
    (``translateFrom()``), when a sample was given; ``readable`` tells whether it
    is exactly the expected template.
    """

    reason: str | None
    readable: bool | None = None
    translated: str | None = None
    version: str | None = None

    @property
    def valid(self) -> bool:
        return self.reason is None


async def check_dialect(
    engine: Path,
    tags: dict[str, str],
    *,
    cwd: Path,
    sample: str | None = None,
    expected: str | None = None,
    php: str | None = None,
    timeout: float = 10.0,
) -> DialectVerdict:
    """Ask Div whether ``tags`` (DIV_TAG_* overrides) make a valid dialect and, with
    ``sample`` (a template in that dialect) and ``expected`` (the same template in
    Div's default dialect), whether Div reads the sample back as expected."""
    request = {"engine": str(engine), "op": "dialect_validate", "tags": tags}
    reply = await _call_bridge(request, cwd=cwd, php=php, timeout=timeout)
    valid = reply.get("valid")
    version = reply.get("version")
    if valid is not True:
        return DialectVerdict(str(valid or "Div gave no answer"), version=version)
    if sample is None or expected is None:
        return DialectVerdict(None, version=version)
    try:
        translated = await translate_template(engine, sample, tags, {}, cwd=cwd, php=php, timeout=timeout)
    except RenderError:
        return DialectVerdict(None, None, version=version)
    return DialectVerdict(None, translated == expected, translated, version=version)


async def translate_template(
    engine: Path,
    code: str,
    source: dict[str, str] | str,
    target: dict[str, str] | str,
    *,
    cwd: Path,
    php: str | None = None,
    timeout: float = 20.0,
) -> str:
    """Div's own ``translate()``: ``code`` written in ``source`` rewritten in ``target``.

    Dialects are DIV_TAG_* overrides, or a dialect file's text (Div decodes it);
    empty means Div's default dialect.
    """
    request = {"engine": str(engine), "op": "translate", "from": source, "to": target, "code": code}
    reply = await _call_bridge(request, cwd=cwd, php=php, timeout=timeout)
    translated = reply.get("translated")
    if not isinstance(translated, str):
        problems = [m.get("text", "") for m in reply.get("messages", []) if m.get("level") in ("FATAL", "PHP")]
        raise RenderError(problems[0] if problems else "Div did not translate the template")
    return translated


@dataclass(frozen=True)
class DialectFile:
    """A dialect as Div loads it: the file Div finds and the tags Div decodes."""

    file: Path | None
    tags: dict[str, str] | None
    problem: str | None = None  # "not found", or why Div could not decode it


async def load_dialect(
    engine: Path,
    *,
    cwd: Path,
    template: Path | None = None,
    ref: str | None = None,
    file: Path | None = None,
    history: list[Path] | None = None,
    code: str | None = None,
    php: str | None = None,
    timeout: float = 10.0,
) -> DialectFile:
    """Load a dialect the way Div does for ``@_DIALECT = ref`` in ``template``
    (``prepareDialect()``: ``getTplPath()``, ``getFileContents()``, ``jsonDecode()``),
    or decode a given dialect ``file`` (or the text ``code``) with Div's ``jsonDecode()``."""
    request: dict = {"engine": str(engine), "op": "dialect_load"}
    if code is not None:
        request["code"] = code
    elif ref is not None:
        request.update(path=str(template or ""), ref=ref, history=[str(h) for h in history or []])
    else:
        request["file"] = str(file or "")
    reply = await _call_bridge(request, cwd=cwd, php=php, timeout=timeout)
    found = reply.get("file")
    tags = reply.get("tags")
    return DialectFile(
        (cwd / found).resolve() if found else None,
        {str(k): str(v) for k, v in tags.items()} if isinstance(tags, dict) else None,
        reply.get("problem"),
    )
