"""divide's own MCP server: the IDE's design-time services for AI coding agents.

``divide --mcp PROJECT`` serves the Model Context Protocol over stdio (the
messages on stdout, logs on stderr), without the interface. It belongs to the
IDE: what it exposes is what divide does while a generator is developed
(the project's Div setup, the editor's checks of a template, a render and the
render trace through the real Div engine). It is not a generator's MCP: a
generator that serves one implements it in its own project.

Every answer comes from the same code the IDE runs (:mod:`divide.run.workbench`,
:mod:`divide.run.render`, :mod:`divide.run.trace`, :mod:`divide.run.setup`); what
is Div's to decide is asked of Div through PHP, never redone in Python.

Trust: a render runs the project's PHP through Div (its engine, the functions
and modifiers its setup allows). That is trusted code running, not a sandbox.
The server takes the trust decisions the user made in divide as they are: a
project's ``php`` settings not trusted in Options > Div setup stay left out,
and the server never trusts them itself. Paths are confined to the project;
outputs and traces are bounded; nothing is written to the project; no shell,
no network listener.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

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

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


class Project:
    """The project the server is confined to, and the traces it keeps for paging."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
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


# ---------------------------------------------------------------- the server
def build(root: Path) -> MCPServer:
    """divide's MCP server for the project at ``root``."""
    project = Project(root)
    server = MCPServer("divide", title="divide", version=__version__, instructions=INSTRUCTIONS, log_level="WARNING",
                       website_url="https://github.com/divengine/divide")

    @server.tool(annotations=READ_ONLY)
    async def project_info() -> dict[str, Any]:
        """The project divide serves: its folder, PHP, the Div engine that renders it, the design-time Div
        setup in effect (.div/setup.json and the user's ~/.div/setup.json), the project's dialect, the
        template and data conventions, what divide left out of the setup and how Div took the setup."""
        setup = div_setup.load(project.root)
        php = shutil.which("php")
        engine = workbench.find_div_engine(project.root, [project.root]) if php else None
        info: dict[str, Any] = {
            "project": {"name": project.root.name, "root": str(project.root)},
            "divide": __version__,
            "php": {"found": bool(php), "version": await _php_version(php) if php else None},
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

    @server.tool(annotations=READ_ONLY)
    async def div_check(
        template: Annotated[str, Field(description="The template, relative to the project")],
        source: Annotated[str | None, Field(description="The template's text to check instead of the saved file")] = None,
    ) -> dict[str, Any]:
        """The checks divide's editor makes on a Div template (Alt+F8 in divide): unclosed blocks, tags Div
        would leave as text, broken JSON in template variables, a broken @_DIALECT and includes Div cannot
        resolve. The template's dialect and its includes are Div's answers (PHP runs for them)."""
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

    @server.tool(annotations=READ_ONLY)
    async def div_render(
        template: Annotated[str, Field(description="The template, relative to the project")],
        data_file: Annotated[str | None, Field(description="The data file (default: the template's, by Div's convention)")] = None,
        source: Annotated[str | None, Field(description="The template's text to render instead of the saved file; "
                                                        "includes and the data file are still found from the template's path")] = None,
        data: Annotated[str | None, Field(description="The data as Div JSON text, instead of the data file")] = None,
        use_data_file: Annotated[bool, Field(description="false: render without data when no data is given")] = True,
        max_output_chars: Annotated[int, Field(description=f"Characters of output returned (1..{MAX_OUTPUT})")] = DEFAULT_OUTPUT,
        timeout_seconds: Annotated[float | None, Field(description=f"Stop PHP after this long (1..{MAX_TIMEOUT:.0f}; "
                                                                   f"default {RENDER_TIMEOUT:.0f})")] = None,
    ) -> dict[str, Any]:
        """Render a template through PHP and the real Div engine, with the project's design-time Div setup, as
        divide renders it (Ctrl+F9). Returns the output, Div's and PHP's messages and the status."""
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

    @server.tool(annotations=READ_ONLY)
    async def div_trace(
        template: Annotated[str, Field(description="The template, relative to the project")],
        data_file: Annotated[str | None, Field(description="The data file (default: the template's, by Div's convention)")] = None,
        source: Annotated[str | None, Field(description="The template's text instead of the saved file")] = None,
        data: Annotated[str | None, Field(description="The data as Div JSON text, instead of the data file")] = None,
        use_data_file: Annotated[bool, Field(description="false: render without data when no data is given")] = True,
        limit: Annotated[int, Field(description=f"Mutations in the first page (1..{MAX_PAGE})")] = 50,
        max_output_chars: Annotated[int, Field(description=f"Characters of output returned (1..{MAX_OUTPUT})")] = DEFAULT_OUTPUT,
        timeout_seconds: Annotated[float | None, Field(description=f"Stop PHP after this long (1..{MAX_TIMEOUT:.0f}; "
                                                                   f"default {TRACE_TIMEOUT:.0f})")] = None,
    ) -> dict[str, Any]:
        """Render as div_render does, keeping every mutation Div made on its way to the fixed point (divide's
        render trace): each change with its causes (Div's own steps), its parse level, its sub-parse (run)
        and cycle. Returns a summary, the output and the first page of mutations; div_trace_page pages
        through the rest and div_trace_mutation shows one mutation's whole text, by the trace_id."""
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

    @server.tool(annotations=READ_ONLY)
    async def div_trace_page(
        trace_id: Annotated[str, Field(description="A trace_id from div_trace")],
        offset: Annotated[int, Field(description="Index of the first mutation")] = 0,
        limit: Annotated[int, Field(description=f"Mutations in the page (1..{MAX_PAGE})")] = 50,
        kind: Annotated[str | None, Field(description="Only this kind: start, change or end")] = None,
        run: Annotated[int | None, Field(description="Only this parse: 1 the template, 2... its sub-parses")] = None,
    ) -> dict[str, Any]:
        """A page of a trace's mutations, optionally only one kind or one run (the server keeps the last
        few traces)."""
        rows = _kept(project, trace_id)
        if offset < 0:
            raise ToolError("offset: 0 or more")
        if kind not in (None, "start", "change", "end"):
            raise ToolError("kind: start, change or end")
        return {"trace_id": trace_id, **_page(rows, offset, _limit(limit, MAX_PAGE, "limit"), kind, run)}

    @server.tool(annotations=READ_ONLY)
    async def div_trace_mutation(
        trace_id: Annotated[str, Field(description="A trace_id from div_trace")],
        index: Annotated[int, Field(description="The mutation's index")],
        max_chars: Annotated[int, Field(description=f"Characters of each text returned (1..{MAX_OUTPUT})")] = DEFAULT_OUTPUT,
    ) -> dict[str, Any]:
        """One mutation of a trace in full: the template's text before and after it, and Div's steps behind it."""
        rows = _kept(project, trace_id)
        if not 0 <= index < len(rows):
            raise ToolError(f"index: 0..{len(rows) - 1}")
        limit = _limit(max_chars, MAX_OUTPUT, "max_chars")
        m = rows[index]
        before, before_cut = _clip(m.before, limit)
        after, after_cut = _clip(m.after, limit)
        return {"trace_id": trace_id, **_row(index, m), "causes": [_clip(c, 300)[0] for c in m.causes[-20:]],
                "before": before, "before_truncated": before_cut, "after": after, "after_truncated": after_cut}

    @server.tool(annotations=READ_ONLY)
    async def div_check_dialect(
        dialect_file: Annotated[str | None, Field(description="A dialect file of the project (.dialect), "
                                                              "or nothing for the project's dialect")] = None,
        tags: Annotated[dict[str, str] | None, Field(description="DIV_TAG_* overrides to check instead of a file")] = None,
    ) -> dict[str, Any]:
        """Div's verdict on a dialect (isValidCurrentDialect(), as divide's Dialector asks it): a dialect file
        of the project decoded by Div, explicit DIV_TAG_* overrides, or the project's dialect."""
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

    return server


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
        out, _ = await asyncio.wait_for(proc.communicate(), 10)
    except (OSError, TimeoutError):
        return None
    return out.decode("utf-8", "replace").strip()[:40] or None


def serve(root: Path) -> None:
    """Serve the project at ``root`` over stdio until the client goes."""
    server = build(root)
    try:
        server.run("stdio")
    finally:
        children.kill_all()


def main(root: str | None) -> int:
    """``divide --mcp PROJECT``; errors on stderr (stdout is the protocol's)."""
    if root is None:
        print("divide --mcp: give the project's folder (divide --mcp /path/to/project)", file=sys.stderr)
        return 2
    path = Path(root).expanduser()
    if not path.is_dir():
        print(f"divide --mcp: {root} is not a folder", file=sys.stderr)
        return 2
    serve(path)
    return 0
