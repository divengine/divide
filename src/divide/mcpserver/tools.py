"""The MCP server's tools: divide's design-time services for one project.

Every answer comes from the same code the IDE runs (:mod:`divide.run.workbench`,
:mod:`divide.run.render`, :mod:`divide.run.trace`, :mod:`divide.run.setup`); what
is Div's to decide is asked of Div through PHP, never redone in Python.

A tool is a coroutine taking the :class:`Project` and its arguments, already
checked against the tool's JSON Schema (:func:`arguments`); it answers a JSON
object or raises :class:`ToolError`, which the client gets as a tool error
(``isError``) the model can read and act on. Nothing here knows the transport.

Trust: a render runs the project's PHP through Div (its engine, the functions
and modifiers its setup allows). That is trusted code running, not a sandbox.
The tools take the trust decisions the user made in divide as they are: a
project's ``php`` settings not trusted in Options > Div setup stay left out,
and nothing here trusts them. Paths are confined to the project; outputs and
traces are bounded; nothing is written to the project.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from divide import __version__, config
from divide.lang.div.diagnostics import line_col
from divide.run import children, workbench
from divide.run import setup as div_setup
from divide.run.render import (ENV_ENGINE, TIMEOUT as RENDER_TIMEOUT, RenderError, RenderMessage, RenderResult,
                               check_dialect, check_setup, load_dialect, render)
from divide.run.trace import TIMEOUT as TRACE_TIMEOUT, Mutation, trace_render

MAX_INPUT = 4 * 1024 * 1024  # characters of a template or data file the server takes
MAX_OUTPUT = 200_000  # characters of output a call may ask for
DEFAULT_OUTPUT = 20_000
MAX_MESSAGES = 100
MAX_TIMEOUT = 120.0
MAX_PAGE = 200
EXCERPT = 400  # characters of a mutation's changed text in a page
KEPT_TRACES = 4

INSTRUCTIONS = """\
divide is an IDE for developing generators with the Divengine ecosystem; this server exposes its
design-time services for one project: the project's Div setup, the editor's checks of a template,
a render and the render trace through the real Div engine, with the project's design-time setup.
Paths are relative to the project. Rendering runs the project's PHP through Div (trusted code, not a
sandbox). The server works on files and on source/data you pass; it does not see divide's open
editors or unsaved buffers, and it never writes to the project."""

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}


class ToolError(Exception):
    """What a tool cannot do, said to the client (and to the model behind it)."""


class Project:
    """The project the server is confined to, and the traces it keeps for paging."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve(strict=True)
        self.traces: OrderedDict[str, dict[str, Any]] = OrderedDict()

    # ---------------------------------------------------------- paths
    def path(self, raw: str, *, what: str, must_exist: bool = True) -> Path:
        """``raw`` (relative to the project, or absolute) as a real path inside the project."""
        if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
            raise ToolError(f"{what}: give a path relative to the project")
        given = Path(raw.strip())
        real = (given if given.is_absolute() else self.root / given).resolve()  # symlinks followed
        if not real.is_relative_to(self.root):
            raise ToolError(f"{what}: {raw} is outside the project ({self.root.name}); only the project's files are served")
        if must_exist and not real.is_file():
            raise ToolError(f"{what}: no such file in the project: {self.rel(real)}")
        if not must_exist and not real.parent.is_dir():
            raise ToolError(f"{what}: no such folder in the project: {self.rel(real.parent)}")
        return real

    def rel(self, path: Path | None) -> str | None:
        """A path as the client sees it: relative to the project, ``~/`` for the user's, else as it is."""
        if path is None:
            return None
        path = Path(path)
        try:
            return path.resolve().relative_to(self.root).as_posix() or "."
        except (ValueError, OSError):
            pass
        try:
            return "~/" + path.resolve().relative_to(Path.home().resolve()).as_posix()
        except (ValueError, OSError, RuntimeError):
            return str(path)

    def read(self, path: Path, what: str) -> str:
        try:
            if path.stat().st_size > MAX_INPUT * 4:
                raise ToolError(f"{what}: {self.rel(path)} is too big for the server")
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ToolError(f"{what}: {self.rel(path)} is not UTF-8 text") from None
        except OSError as exc:
            raise ToolError(f"{what}: cannot read {self.rel(path)}: {exc.strerror or exc}") from None
        return _bounded_input(text, what)

    # ---------------------------------------------------------- engine
    def engine(self, folder: Path | None = None) -> Path:
        """The engine that renders the templates of ``folder`` (the project's root by default),
        as the IDE finds it; a clear error without one."""
        if not shutil.which("php"):
            raise ToolError("php not found in PATH: divide renders through PHP and Div")
        engine = workbench.engine_for(self.root, (folder or self.root) / "_")
        if engine is None:
            raise ToolError("Div was not found: install it in the project (composer require divengine/div), "
                            "set the setup's \"engine\" (.div/setup.json) or choose it in divide (Options > Div engine)")
        return engine

    def engine_origin(self, engine: Path | None) -> str | None:
        if engine is None:
            return None
        setup = div_setup.load(self.root)
        for origin, candidate in ((ENV_ENGINE, os.environ.get(ENV_ENGINE)), ("setup", setup.engine and str(setup.engine)),
                                  ("options", config.load().get("div_engine"))):
            if candidate and Path(candidate).expanduser().resolve() == engine:
                return origin
        return "vendor"


def _bounded_input(text: str, what: str) -> str:
    if len(text) > MAX_INPUT:
        raise ToolError(f"{what}: more than {MAX_INPUT:,} characters")
    return text


def _clip(text: str, limit: int) -> tuple[str, bool]:
    return (text, False) if len(text) <= limit else (text[:limit], True)


def _timeout(seconds: float | None, default: float) -> float:
    if seconds is None:
        return default
    if not 1 <= seconds <= MAX_TIMEOUT:
        raise ToolError(f"timeout_seconds: between 1 and {MAX_TIMEOUT:.0f}")
    return float(seconds)


def _limit(value: int, top: int, what: str) -> int:
    if not 1 <= value <= top:
        raise ToolError(f"{what}: between 1 and {top:,}")
    return value


# ---------------------------------------------------------------- shared shapes
def _position(project: Project, message: RenderMessage) -> dict[str, Any]:
    out: dict[str, Any] = {"level": message.level, "text": message.text}
    if message.path is not None:
        out["file"] = project.rel(message.path)
        try:
            text = Path(message.path).read_text(encoding="utf-8")
            out["line"], out["column"] = line_col(text, min(message.offset, len(text)))
        except (OSError, UnicodeDecodeError):
            pass
    return out


def _messages(project: Project, messages: list[RenderMessage]) -> dict[str, Any]:
    rows = [_position(project, m) for m in messages[:MAX_MESSAGES]]
    return {"messages": rows, "messages_omitted": max(0, len(messages) - MAX_MESSAGES)}


def _status(result: RenderResult) -> str:
    return "fatal" if result.fatal else ("warnings" if result.serious else "ok")


def _trust(project: Project) -> dict[str, Any] | None:
    untrusted = div_setup.load(project.root).untrusted
    if untrusted is None:
        return None
    return {"file": project.rel(untrusted.file), "allowed_functions": list(untrusted.functions),
            "modifiers": dict(untrusted.modifiers),
            "how": "the project's \"php\" settings are left out until the user trusts them in divide "
                   "(Options > Div setup); this server never trusts them"}


class Inputs:
    """A render's template, source, data file and data, taken the way the IDE takes them."""

    def __init__(self, project: Project, template: str, data_file: str | None, source: str | None,
                 data: str | None, use_data_file: bool) -> None:
        self.template = project.path(template, what="template", must_exist=source is None)
        self.source_given = source is not None
        self.code = _bounded_input(source, "source") if source is not None else project.read(self.template, "template")
        default = workbench.data_file(project.root, self.template)
        self.data_path = project.path(data_file if data_file is not None else str(default), what="data_file",
                                      must_exist=data_file is not None)
        if data is not None:
            self.data: str | None = _bounded_input(data, "data")
            self.data_from = "argument"
        elif use_data_file and self.data_path.is_file():
            self.data = project.read(self.data_path, "data_file")
            self.data_from = "file"
        else:
            self.data, self.data_from = None, "none"
        self.engine = project.engine(self.template.parent)

    def describe(self, project: Project) -> dict[str, Any]:
        return {"template": project.rel(self.template), "source": "argument" if self.source_given else "file",
                "data_file": project.rel(self.data_path) if self.data_from == "file" else None,
                "data": self.data_from, "engine": project.rel(self.engine)}


# ---------------------------------------------------------------- trace rows
def _excerpt(text: str, start: int, end: int) -> dict[str, Any]:
    piece, cut = _clip(text[start:end], EXCERPT)
    return {"start": start, "end": end, "text": piece, "clipped": cut}


def _row(index: int, m: Mutation) -> dict[str, Any]:
    row: dict[str, Any] = {"index": index, "kind": m.kind, "run": m.run, "engine": m.engine, "level": m.level,
                           "cycle": m.cycle, "label": m.label, "size": len(m.after)}
    if m.kind == "change":
        (b0, b1), (a0, a1) = m.changed()
        row.update(delta=m.delta, removed=_excerpt(m.before, b0, b1), inserted=_excerpt(m.after, a0, a1))
    elif m.kind == "start":
        row["context"] = m.context
        row["source"] = _excerpt(m.after, 0, len(m.after))
    return row


def _trace_summary(rows: list[Mutation]) -> dict[str, Any]:
    runs = [r for r in rows if r.kind == "start"]
    return {
        "mutations": len(rows),
        "changes": sum(r.kind == "change" for r in rows),
        "runs": len(runs),
        "max_level": max((r.level for r in rows), default=0),
        "fixed_points": [{"run": r.run, "level": r.level, "cycles": r.cycle} for r in rows if r.kind == "end"][:50],
    }


def _kept(project: Project, trace_id: str) -> list[Mutation]:
    kept = project.traces.get(trace_id)
    if kept is None:
        raise ToolError("unknown trace_id (the server keeps the last few traces): run div_trace again")
    return kept["rows"]


def _page(rows: list[Mutation], offset: int, limit: int, kind: str | None, run: int | None) -> dict[str, Any]:
    picked = [(i, m) for i, m in enumerate(rows) if (kind is None or m.kind == kind) and (run is None or m.run == run)]
    chunk = picked[offset:offset + limit]
    following = offset + limit
    return {"offset": offset, "total": len(picked), "mutations": [_row(i, m) for i, m in chunk],
            "next_offset": following if following < len(picked) else None}


async def _php_version(php: str) -> str | None:
    try:
        proc = children.track(await asyncio.create_subprocess_exec(
            php, "-r", "echo PHP_VERSION;", stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, **children.options()))
    except OSError:
        return None
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), 10)
    except (TimeoutError, asyncio.CancelledError):
        children.kill(proc)
        await proc.wait()
        raise
    return out.decode("utf-8", "replace").strip()[:40] or None


# ---------------------------------------------------------------- the tools
async def project_info(project: Project) -> dict[str, Any]:
    setup = div_setup.load(project.root)
    php = shutil.which("php")
    engine = workbench.find_div_engine(project.root, [project.root]) if php else None
    try:
        version = await _php_version(php) if php else None
    except TimeoutError:
        version = None
    info: dict[str, Any] = {
        "project": {"name": project.root.name, "root": str(project.root)},
        "divide": __version__,
        "php": {"found": bool(php), "version": version},
        "engine": {"path": project.rel(engine), "origin": project.engine_origin(engine)} if engine else None,
        "conventions": {
            "template_ext": setup.template_ext, "data_ext": setup.data_ext,
            "data_file": f"a template takes its data from the file beside it with the data extension "
                         f"(page{setup.template_ext} -> page{setup.data_ext})",
        },
        "setup": {
            "files": [project.rel(f) for f in setup.files],
            "constants": dict(setup.constants),
            "include_paths": list(setup.include_paths),
            "error_reporting": setup.error_reporting,
            "system_vars": list(setup.system_vars),
            "allowed_functions": list(setup.allowed_functions),
            "modifiers": dict(setup.modifiers),
            "globals": sorted(setup.globals),
            "request": {name: sorted(values) for name, values in setup.request.items()},
        },
        "dialect": ({"source": project.rel(setup.dialect_source), "tags": dict(setup.dialect_tags)}
                    if setup.dialect_tags else None),
        "problems": [_position(project, RenderMessage("SETUP", p.text, p.file, p.offset)) for p in setup.problems],
        "untrusted_php": _trust(project),
    }
    if engine is None:
        info["div"] = {"checked": False, "reason": "php not found in PATH" if not php else "Div was not found"}
        return info
    try:
        verdict = await check_setup(engine, cwd=project.root)
    except RenderError as exc:
        info["div"] = {"checked": False, "reason": str(exc)}
        return info
    info["div"] = {
        "checked": True, "version": verdict.version,
        "dialect": "valid" if verdict.dialect is None else verdict.dialect,
        "include_paths": verdict.include_paths, "functions": verdict.functions, "modifiers": verdict.modifiers,
        **_messages(project, verdict.messages),
    }
    return info


async def div_check(project: Project, template: str, source: str | None = None) -> dict[str, Any]:
    path = project.path(template, what="template", must_exist=source is None)
    text = _bounded_input(source, "source") if source is not None else project.read(path, "template")
    engine = workbench.engine_for(project.root, path)
    found = await workbench.check_template(project.root, path, text, engine=engine, describe=project.rel)
    rows = []
    for d in found.diagnostics:
        line, column = line_col(text, d.start)
        end_line, end_column = line_col(text, d.end)
        rows.append({"severity": d.severity, "message": d.message, "file": project.rel(path), "start": d.start,
                     "end": d.end, "line": line, "column": column, "end_line": end_line, "end_column": end_column,
                     "text": _clip(text[d.start:d.end], 200)[0]})
    dialect = found.dialect
    return {
        "template": project.rel(path),
        "errors": sum(d.severity == "error" for d in found.diagnostics),
        "warnings": sum(d.severity == "warning" for d in found.diagnostics),
        "diagnostics": rows[:500],
        "dialect": {"name": dialect.name, "source": project.rel(dialect.source) if dialect.source else None,
                    "error": dialect.error},
        "includes": {raw: project.rel(t.file) if t.file else None for raw, t in found.includes.items()},
        "div_consulted": found.div_asked,
        "note": None if found.div_asked else
                "Div could not be asked (no php or no Div): the dialect is divide's guess and includes are not checked",
    }


async def div_render(project: Project, template: str, data_file: str | None = None, source: str | None = None,
                     data: str | None = None, use_data_file: bool = True, max_output_chars: int = DEFAULT_OUTPUT,
                     timeout_seconds: float | None = None) -> dict[str, Any]:
    limit = _limit(max_output_chars, MAX_OUTPUT, "max_output_chars")
    inputs = Inputs(project, template, data_file, source, data, use_data_file)
    try:
        result = await render(inputs.engine, inputs.template, inputs.code, inputs.data, cwd=project.root,
                              timeout=_timeout(timeout_seconds, RENDER_TIMEOUT))
    except RenderError as exc:
        raise ToolError(str(exc)) from None
    output, cut = _clip(result.output, limit)
    return {"status": _status(result), **inputs.describe(project), "div": result.version,
            "seconds": round(result.seconds, 3), "output": output, "output_chars": len(result.output),
            "output_truncated": cut, **_messages(project, result.messages), "untrusted_php": _trust(project)}


async def div_trace(project: Project, template: str, data_file: str | None = None, source: str | None = None,
                    data: str | None = None, use_data_file: bool = True, limit: int = 50,
                    max_output_chars: int = DEFAULT_OUTPUT, timeout_seconds: float | None = None) -> dict[str, Any]:
    page = _limit(limit, MAX_PAGE, "limit")
    out_limit = _limit(max_output_chars, MAX_OUTPUT, "max_output_chars")
    inputs = Inputs(project, template, data_file, source, data, use_data_file)
    try:
        trace = await trace_render(inputs.engine, inputs.template, inputs.code, inputs.data, cwd=project.root,
                                   timeout=_timeout(timeout_seconds, TRACE_TIMEOUT))
    except RenderError as exc:
        raise ToolError(str(exc)) from None
    trace_id = uuid.uuid4().hex[:12]
    project.traces[trace_id] = {"rows": trace.mutations, "template": project.rel(inputs.template)}
    while len(project.traces) > KEPT_TRACES:
        project.traces.popitem(last=False)
    result = trace.result
    output, cut = _clip(result.output, out_limit)
    return {"trace_id": trace_id, "status": _status(result), **inputs.describe(project), "div": result.version,
            "seconds": round(result.seconds, 3), "summary": {**_trace_summary(trace.mutations), "events": trace.events,
                                                              "events_truncated": trace.truncated},
            "output": output, "output_chars": len(result.output), "output_truncated": cut,
            **_messages(project, result.messages), "untrusted_php": _trust(project),
            **_page(trace.mutations, 0, page, None, None)}


async def div_trace_page(project: Project, trace_id: str, offset: int = 0, limit: int = 50, kind: str | None = None,
                         run: int | None = None) -> dict[str, Any]:
    rows = _kept(project, trace_id)
    if offset < 0:
        raise ToolError("offset: 0 or more")
    if kind not in (None, "start", "change", "end"):
        raise ToolError("kind: start, change or end")
    return {"trace_id": trace_id, **_page(rows, offset, _limit(limit, MAX_PAGE, "limit"), kind, run)}


async def div_trace_mutation(project: Project, trace_id: str, index: int, max_chars: int = DEFAULT_OUTPUT) -> dict[str, Any]:
    rows = _kept(project, trace_id)
    if not 0 <= index < len(rows):
        raise ToolError(f"index: 0..{len(rows) - 1}")
    limit = _limit(max_chars, MAX_OUTPUT, "max_chars")
    m = rows[index]
    before, before_cut = _clip(m.before, limit)
    after, after_cut = _clip(m.after, limit)
    return {"trace_id": trace_id, **_row(index, m), "causes": [_clip(c, 300)[0] for c in m.causes[-20:]],
            "before": before, "before_truncated": before_cut, "after": after, "after_truncated": after_cut}


async def div_check_dialect(project: Project, dialect_file: str | None = None,
                            tags: dict[str, str] | None = None) -> dict[str, Any]:
    if dialect_file is not None and tags is not None:
        raise ToolError("give dialect_file or tags, not both")
    source: str | None = None
    if dialect_file is not None:
        path = project.path(dialect_file, what="dialect_file")
        engine = project.engine(path.parent)
        try:
            loaded = await load_dialect(engine, cwd=project.root, file=path)
        except RenderError as exc:
            raise ToolError(str(exc)) from None
        if loaded.tags is None:
            return {"valid": False, "reason": loaded.problem or "Div could not decode the dialect",
                    "source": project.rel(path), "tags": None}
        checked, source = loaded.tags, project.rel(path)
    elif tags is not None:
        if not all(k.startswith("DIV_TAG_") for k in tags):
            raise ToolError("tags: DIV_TAG_* names only")
        engine, checked, source = project.engine(), dict(tags), None
    else:
        setup = div_setup.load(project.root)
        if not setup.dialect_tags:
            return {"valid": True, "reason": None, "source": None, "tags": {},
                    "note": "the project has no dialect of its own: Div's default one"}
        engine, checked = project.engine(), dict(setup.dialect_tags)
        source = project.rel(setup.dialect_source) if setup.dialect_source else "setup"
    try:
        verdict = await check_dialect(engine, checked, cwd=project.root)
    except RenderError as exc:
        raise ToolError(str(exc)) from None
    return {"valid": verdict.valid, "reason": verdict.reason, "source": source, "tags": checked, "div": verdict.version}


# ---------------------------------------------------------------- schemas
def _string(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _optional(kind: str | dict[str, Any], description: str, default: Any = None) -> dict[str, Any]:
    schema = {"type": kind} if isinstance(kind, str) else dict(kind)
    return {"anyOf": [schema, {"type": "null"}], "default": default, "description": description}


TEMPLATE = _string("The template, relative to the project")
DATA_FILE = _optional("string", "The data file (default: the template's, by Div's convention)")
DATA = _optional("string", "The data as Div JSON text, instead of the data file")
USE_DATA_FILE = {"type": "boolean", "default": True, "description": "false: render without data when no data is given"}
OUTPUT_CHARS = {"type": "integer", "default": DEFAULT_OUTPUT, "description": f"Characters of output returned (1..{MAX_OUTPUT})"}
TRACE_ID = _string("A trace_id from div_trace")


def _timeout_schema(default: float) -> dict[str, Any]:
    return _optional("number", f"Stop PHP after this long (1..{MAX_TIMEOUT:.0f}; default {default:.0f})")


def _object(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = list(required)
    return schema


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    description: str
    input_schema: dict[str, Any]
    run: Callable[..., Awaitable[dict[str, Any]]]

    def listing(self) -> dict[str, Any]:
        """The tool as ``tools/list`` shows it."""
        return {"name": self.name, "title": self.title, "description": self.description,
                "inputSchema": self.input_schema, "annotations": {"title": self.title, **READ_ONLY}}


TOOLS: tuple[Tool, ...] = (
    Tool("project_info", "Project info",
         "The project divide serves: its folder, PHP, the Div engine that renders it, the design-time Div setup in "
         "effect (.div/setup.json and the user's ~/.div/setup.json), the project's dialect, the template and data "
         "conventions, what divide left out of the setup and how Div took the setup.",
         _object({}), project_info),
    Tool("div_check", "Check a template",
         "The checks divide's editor makes on a Div template (Alt+F8 in divide): unclosed blocks, tags Div would leave "
         "as text, broken JSON in template variables, a broken @_DIALECT and includes Div cannot resolve. The "
         "template's dialect and its includes are Div's answers (PHP runs for them).",
         _object({"template": TEMPLATE,
                  "source": _optional("string", "The template's text to check instead of the saved file")},
                 ("template",)), div_check),
    Tool("div_render", "Render a template",
         "Render a template through PHP and the real Div engine, with the project's design-time Div setup, as divide "
         "renders it (Ctrl+F9). Returns the output, Div's and PHP's messages and the status.",
         _object({"template": TEMPLATE, "data_file": DATA_FILE,
                  "source": _optional("string", "The template's text to render instead of the saved file; includes "
                                                "and the data file are still found from the template's path"),
                  "data": DATA, "use_data_file": USE_DATA_FILE, "max_output_chars": OUTPUT_CHARS,
                  "timeout_seconds": _timeout_schema(RENDER_TIMEOUT)}, ("template",)), div_render),
    Tool("div_trace", "Trace a render",
         "Render as div_render does, keeping every mutation Div made on its way to the fixed point (divide's render "
         "trace): each change with its causes (Div's own steps), its parse level, its sub-parse (run) and cycle. "
         "Returns a summary, the output and the first page of mutations; div_trace_page pages through the rest and "
         "div_trace_mutation shows one mutation's whole text, by the trace_id.",
         _object({"template": TEMPLATE, "data_file": DATA_FILE,
                  "source": _optional("string", "The template's text instead of the saved file"),
                  "data": DATA, "use_data_file": USE_DATA_FILE,
                  "limit": {"type": "integer", "default": 50, "description": f"Mutations in the first page (1..{MAX_PAGE})"},
                  "max_output_chars": OUTPUT_CHARS, "timeout_seconds": _timeout_schema(TRACE_TIMEOUT)},
                 ("template",)), div_trace),
    Tool("div_trace_page", "Page through a trace",
         "A page of a trace's mutations, optionally only one kind or one run (the server keeps the last few traces).",
         _object({"trace_id": TRACE_ID,
                  "offset": {"type": "integer", "default": 0, "description": "Index of the first mutation"},
                  "limit": {"type": "integer", "default": 50, "description": f"Mutations in the page (1..{MAX_PAGE})"},
                  "kind": _optional({"type": "string", "enum": ["start", "change", "end"]}, "Only this kind: start, change or end"),
                  "run": _optional("integer", "Only this parse: 1 the template, 2... its sub-parses")},
                 ("trace_id",)), div_trace_page),
    Tool("div_trace_mutation", "One mutation of a trace",
         "One mutation of a trace in full: the template's text before and after it, and Div's steps behind it.",
         _object({"trace_id": TRACE_ID, "index": {"type": "integer", "description": "The mutation's index"},
                  "max_chars": {"type": "integer", "default": DEFAULT_OUTPUT,
                                "description": f"Characters of each text returned (1..{MAX_OUTPUT})"}},
                 ("trace_id", "index")), div_trace_mutation),
    Tool("div_check_dialect", "Check a dialect",
         "Div's verdict on a dialect (isValidCurrentDialect(), as divide's Dialector asks it): a dialect file of the "
         "project decoded by Div, explicit DIV_TAG_* overrides, or the project's dialect.",
         _object({"dialect_file": _optional("string", "A dialect file of the project (.dialect), or nothing for the "
                                                      "project's dialect"),
                  "tags": _optional({"type": "object", "additionalProperties": {"type": "string"}},
                                    "DIV_TAG_* overrides to check instead of a file")}), div_check_dialect),
)
BY_NAME = {tool.name: tool for tool in TOOLS}


# ---------------------------------------------------------------- arguments
_TYPES: dict[str, Callable[[Any], bool]] = {
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer()),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "null": lambda v: v is None,
    "object": lambda v: isinstance(v, dict),
}


def _fits(schema: dict[str, Any], value: Any) -> bool:
    if "anyOf" in schema:
        return any(_fits(option, value) for option in schema["anyOf"])
    if not _TYPES[schema["type"]](value):
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if schema["type"] == "object" and isinstance(schema.get("additionalProperties"), dict):
        return all(_fits(schema["additionalProperties"], v) for v in value.values())
    return True


def _kind(schema: dict[str, Any]) -> str:
    kinds = [o["type"] for o in schema.get("anyOf", [schema]) if o["type"] != "null"]
    names = {"string": "a string", "boolean": "true or false", "integer": "an integer", "number": "a number",
             "object": "an object of strings"}
    text = " or ".join(names[k] for k in kinds)
    return text + (" (or null)" if "anyOf" in schema else "")


def arguments(tool: Tool, given: Any) -> dict[str, Any]:
    """``given`` checked against the tool's schema, with the defaults: the keyword arguments of its call."""
    if given is None:
        given = {}
    if not isinstance(given, dict):
        raise ToolError("arguments: a JSON object")
    properties: dict[str, Any] = tool.input_schema["properties"]
    unknown = sorted(set(given) - set(properties))
    if unknown:
        raise ToolError(f"unknown argument{'s' if len(unknown) > 1 else ''}: {', '.join(unknown)} "
                        f"(the tool takes {', '.join(properties) or 'none'})")
    missing = [name for name in tool.input_schema.get("required", ()) if name not in given]
    if missing:
        raise ToolError(f"missing argument: {', '.join(missing)}")
    out: dict[str, Any] = {}
    for name, schema in properties.items():
        if name not in given:
            continue
        value = given[name]
        if not _fits(schema, value):
            raise ToolError(f"{name}: {_kind(schema)}")
        if isinstance(value, float) and value.is_integer() and "integer" in {o["type"] for o in schema.get("anyOf", [schema])}:
            value = int(value)
        out[name] = value
    return out


async def call(project: Project, name: str, given: Any) -> dict[str, Any]:
    """Run the tool ``name``: its answer, or :class:`ToolError` (KeyError: no such tool)."""
    tool = BY_NAME[name]
    return await tool.run(project, **arguments(tool, given))
