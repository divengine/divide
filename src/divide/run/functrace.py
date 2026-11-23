"""The PHP line trace of a Function Mock Simulation, and its ``divide.function-trace`` v1 (UI-independent).

**MOCK SIMULATION: real PHP runs.** A traced run is the same run as :func:`divide.run.funcsim.simulate`
(the same harness, doubles, limits and tripwire), watched line by line. Watching does not make it
safer: the Function's real PHP code runs. These are PHP source lines of one Function, never Runner's
semantic Step events: a Flow simulation (:mod:`divide.run.simulate`) runs no Function code, and its
trace (``divengine.runner.trace``) and this one never mix. Design: ``docs/function-simulation.md`` §5, §7.

- :func:`record`: divide's own Xdebug client (:class:`divide.run.dbgp.DebugSession`), with no person
  at it. A temporary breakpoint on the harness's call line, then one ``step_into`` per line; only the
  Function's file is recorded, any other code (the doubles, other files) is left with ``step_out``.
  The locals are read by an ``eval`` of the harness's encoder in the Function's frame, and never
  written back (``get_defined_vars()`` keeps references: writing back broke the Function in #15).
  Bounded by ``limits.lines`` (the trace is truncated and marked, status ``line_limit``),
  ``limits.seconds`` (PHP is killed, ``timeout``) and the bytes of one read of the locals;
  cancelling the task kills PHP mid-step.
- :func:`document`, :func:`parse_trace`: the versioned trace; a reader refuses another protocol or
  version and ignores unknown fields and event types.
- Runs: ``.div/function-simulation/`` in the project, out of Git, with the retention of Flow
  simulations (:func:`divide.run.simulate.cleanup`; runs open in a window are kept). Runner's
  ``.div/runner/`` and Flow simulations' ``.div/simulation/`` are never touched.
- :class:`LinePlayback`: a cursor over the line events (:class:`divide.run.simulate.Cursor`, shared
  with Flow playback), next at the same depth, and the locals and context folded at event N.

Line semantics:

- Xdebug stops *before* a line runs: an event's ``locals`` are the changes the lines before it left.
- A branch not taken has no event.
- Several statements on one line are one event with a ``repeat`` count while they change no local;
  a statement that changed one is a new event on the same line (its ``locals`` say what changed).
- What a double changed while the line ran (it was called from that line) is the line's
  ``after_call``.
- ``depth`` counts calls inside the Function's own file (a closure it defines and calls is 1).
- A ``foreach`` header appears on the first pass only (Xdebug maps the next-item step to the body).
- Values are bounded by the harness: strings over 4 KiB are cut and marked (``$type: string`` with
  ``head`` and ``bytes``), arrays over 1,000 items end with ``$truncated``, depth stops at 16.
"""

from __future__ import annotations

from divide.i18n import _

import asyncio
import hashlib
import json
import secrets
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from divide.run import funcsim as fs
from divide.run import simulate as sim_flow
from divide.run.dbgp import NS, DebugError, DebugSession, _text, xdebug_ini

PROTOCOL = "divide.function-trace"
VERSION = 1
CACHE = Path(".div") / "function-simulation"  # the project's traced runs, out of Git
META = "divide-function-run.json"  # what marks a folder as a run of divide's (only these are ever removed)
META_PROTOCOL = "divide.function-simulation-run"
TRACE_FILE = "trace.json"
SCENARIO_FILE = "scenario.json"
KEEP_RUNS = sim_flow.KEEP_SESSIONS
MAX_CACHE_BYTES = sim_flow.MAX_CACHE_BYTES
LOCALS_BYTES = 256 * 1024  # one read of the locals (Xdebug's max_data)
_IGNORE = "# divide's Function Mock Simulations: traced runs, not versioned\n*\n"


class TraceError(fs.SimulationError):
    """A trace that cannot be read, or a run that cannot be traced."""


# ---------------------------------------------------------------- recording
def _same(a: Path | None, b: Path) -> bool:
    if a is None:
        return False
    try:
        return a.resolve() == b
    except OSError:
        return False


def _flat(local: dict) -> dict:
    """Locals by name, the context key by key (``context.total``): a change names what changed."""
    flat = {k: v for k, v in local.items() if k != "context"}
    context = local.get("context")
    if isinstance(context, dict):
        flat.update({f"context.{k}": v for k, v in context.items()})
    elif "context" in local:
        flat["context"] = context
    return flat


def _diff(before: dict, after: dict) -> dict:
    changes: dict = {}
    if set_ := {k: v for k, v in after.items() if k not in before or before[k] != v}:
        changes["set"] = set_
    if unset := sorted(k for k in before if k not in after):
        changes["unset"] = unset
    return changes


def _apply(frame: dict, changes: dict | None) -> None:
    if not isinstance(changes, dict):
        return
    for key in changes.get("unset") or []:
        frame.pop(key, None)
    if isinstance(changes.get("set"), dict):
        frame.update(changes["set"])


class _Recorder:
    """Steps through the Function's lines on a :class:`DebugSession` that has just started."""

    def __init__(self, session: DebugSession, target: Path, max_lines: int, project: Path) -> None:
        self.session = session
        self.target = target
        self.harness = fs.HARNESS.resolve()
        self.max_lines = max_lines
        self.project = project
        self.events: list[dict] = []
        self.truncated = False

    def _where(self, where: str) -> str:
        """The frame's name without this machine's paths (PHP 8.4 names closures by file)."""
        for path in (str(self.target), str(self.project)):
            where = where.replace(path, self.target.name if path == str(self.target) else ".")
        return where

    async def _locals(self) -> dict:
        """The current frame's locals, as the harness encodes them (the eval runs in that frame)."""
        reply = await self.session.command("eval", "-d", "0", data="__divide_funcsim_locals(get_defined_vars())")
        prop = reply.find("d:property", NS)
        if prop is None or reply.find("d:error", NS) is not None:
            return {"$error": "unavailable"}
        try:
            value = json.loads(_text(prop))
        except ValueError:
            return {"$error": "cut"}  # over LOCALS_BYTES
        return _flat(value) if isinstance(value, dict) else {}

    async def run(self) -> None:
        session = self.session
        await session.start()
        await session.command("feature_set", "-n", "max_data", "-v", str(LOCALS_BYTES))
        await session.set_breakpoint(fs.HARNESS, fs.call_line(), temporary=True)
        if await session.resume("run") is None:  # ended before the call (stale, missing, an exception loading)
            return
        frames: list[dict] = []  # the locals last seen, per depth inside the Function
        base: int | None = None
        how = "step_into"
        while True:
            location = await session.resume(how)
            if location is None:
                return
            if _same(location.file, self.target):
                stack = await session.stack()
                if base is None:
                    base = len(stack)
                level = max(0, len(stack) - base)
                del frames[level + 1:]
                while len(frames) <= level:
                    frames.append({})
                now = await self._locals()
                event: dict = {"seq": len(self.events) + 1, "type": "line", "line": location.line, "depth": level,
                               "function": self._where(stack[0].where) if stack else ""}
                if "$error" in now:
                    event["locals_error"] = now["$error"]
                    changes: dict = {}
                else:
                    changes = _diff(frames[level], now)
                    frames[level] = now
                last = self.events[-1] if self.events else None
                same = last is not None and last["line"] == event["line"] and last["depth"] == level
                if same and how == "step_out":
                    if changes:  # back from a double called on this line: what it changed
                        last.setdefault("after_call", {}).update(changes)
                elif same and not changes:
                    last["repeat"] = last.get("repeat", 0) + 1  # one line, several statements
                else:
                    if changes:
                        event["locals"] = changes
                    self.events.append(event)
                if len(self.events) >= self.max_lines:
                    self.truncated = True
                    await session.stop()
                    return
                how = "step_into"
            elif base is not None and _same(location.file, self.harness) and len(await session.stack()) == 1:
                await session.resume("run")  # the Function returned or threw: let the harness write its result
                return
            else:
                how = "step_out"  # a double or other code: not the Function's lines


async def record(request: fs.SimRequest, *, tripwire: bool = False, php: str | None = None,
                 ini: list[str] | None = None, xdebug: str | None = None) -> fs.Simulation:
    """The request's simulation with its PHP line trace (``events``). The same checks as an untraced
    run refuse it first (:class:`divide.run.funcsim.SimulationError`); so does a PHP without Xdebug
    (php.ini, else ``xdebug``: the extension's file). Cancelling the task kills PHP, then re-raises."""
    sim = fs.preflight(request, php, tripwire)
    sim.traced = True
    if sim.status:
        return sim
    php = php or shutil.which("php")
    loads = await xdebug_ini(php, xdebug)
    if loads is None:
        raise TraceError(_('The line trace needs Xdebug: install it, or set its extension file in Options'))
    work = Path(tempfile.mkdtemp(prefix="divide-functrace-")).resolve()
    started = time.monotonic()
    try:
        request_file, nonce = fs.prepare(request, work)
        session = DebugSession(fs.HARNESS, [str(request_file)], cwd=request.project, php=php,
                               ini=[*(ini or []), *loads, *fs.process_ini(request, work, tripwire)],
                               limit=fs.RESULT_BYTES)
        recorder = _Recorder(session, request.file, fs.limit(request.scenario, "lines"), request.project)  # type: ignore[arg-type]
        try:
            await asyncio.wait_for(recorder.run(), fs.limit(request.scenario, "seconds"))
        except TimeoutError:
            sim.status = "timeout"
        except (DebugError, OSError, ET.ParseError) as exc:
            sim.status, sim.message = "crashed", str(exc)
        finally:
            if session.state != "stopped":
                await session.stop()  # also when cancelled: PHP never outlives the run
        if recorder.truncated:
            sim.status, sim.truncated = "line_limit", True
        sim.events = recorder.events
        sim.exit_code, sim.stderr = session.exit_code, session.errors
        sim.messages = session.messages
        data, sim.leaked = fs.read_result(session.output, nonce)
        if data is not None:
            fs.fill(sim, data)
        elif not sim.status:
            sim.status = "crashed"
        return sim
    finally:
        sim.seconds = time.monotonic() - started
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- the protocol
def scenario_sha256(scenario: dict) -> str:
    return hashlib.sha256(json.dumps(scenario, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _relative(path: Path | None, project: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)


def document(sim: fs.Simulation) -> dict:
    """The ``divide.function-trace`` v1 document of a traced run.

    ``function.pinned`` says whether the scenario fixed the source (``function.sha256``): only a pinned
    scenario was checked against the file it ran; an unpinned one ran whatever the file was then."""
    req = sim.request
    func = req.scenario["function"]
    return {
        "protocol": PROTOCOL, "version": VERSION,
        "scenario": {"sha256": scenario_sha256(req.scenario), "description": req.scenario.get("description", "")},
        "function": {"module": req.module, "name": req.name, "file": _relative(req.file, req.project),
                     "sha256": sim.sha256, "pinned": bool(func.get("sha256"))},
        "result": sim.result(),
        "events": sim.events,
        "truncated": sim.truncated,
    }


@dataclass
class FunctionTrace:
    """A ``divide.function-trace`` v1 document, read."""

    data: dict
    events: list[dict] = field(default_factory=list)  # every event, the unknown types too

    @property
    def result(self) -> dict:
        return self.data.get("result") if isinstance(self.data.get("result"), dict) else {}

    @property
    def status(self) -> str:
        return str(self.result.get("status") or "")

    @property
    def function(self) -> dict:
        return self.data.get("function") if isinstance(self.data.get("function"), dict) else {}

    @property
    def pinned(self) -> bool:
        """The scenario fixed the source's sha256. Never shown as pinned otherwise."""
        return self.function.get("pinned") is True and isinstance(self.function.get("sha256"), str)

    @property
    def truncated(self) -> bool:
        return self.data.get("truncated") is True

    @property
    def lines(self) -> list[dict]:
        """The line events, in order (the event types this version knows)."""
        return [e for e in self.events if e.get("type") == "line" and isinstance(e.get("line"), int)]


def parse_trace(data: object) -> FunctionTrace:
    """A trace this version reads; :class:`TraceError` for another protocol or version. Unknown
    fields and event types are kept and ignored."""
    if not isinstance(data, dict):
        raise TraceError(_('A Function trace is a JSON object'))
    if data.get("protocol") != PROTOCOL:
        raise TraceError(_('Not a Function trace ({protocol})').format(protocol=data.get("protocol")))
    if data.get("version") != VERSION:
        raise TraceError(_('Function trace version {version}: this divide reads version {known}').format(
            version=data.get("version"), known=VERSION))
    events = data.get("events")
    if not isinstance(events, list):
        raise TraceError(_('A Function trace has a list of events'))
    return FunctionTrace(data, [e for e in events if isinstance(e, dict)])


def read_trace(path: Path) -> FunctionTrace:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise TraceError(_('{name} cannot be read: {error}').format(name=Path(path).name, error=exc)) from exc
    return parse_trace(data)


# ---------------------------------------------------------------- runs in the project
def cache_dir(project: Path) -> Path:
    return Path(project) / CACHE


def prepare_cache(project: Path) -> Path:
    folder = cache_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    ignore = folder / ".gitignore"
    if not ignore.exists():
        ignore.write_text(_IGNORE, encoding="utf-8")
    return folder


def save_run(sim: fs.Simulation, *, active: set[Path] | None = None) -> Path:
    """The traced run kept in the project's cache (the trace and the scenario it ran), then the
    oldest runs past the retention removed, never one in ``active`` (open in a window)."""
    project = sim.request.project
    stamp = datetime.now(timezone.utc)
    folder = prepare_cache(project) / f"{stamp.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    folder.mkdir()
    (folder / TRACE_FILE).write_text(json.dumps(document(sim), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (folder / SCENARIO_FILE).write_text(json.dumps(sim.request.scenario, indent=4, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    meta = {"protocol": META_PROTOCOL, "version": 1, "function": sim.request.qualified, "status": sim.status,
            "created": stamp.isoformat(timespec="seconds"), "lines": len(sim.events), "truncated": sim.truncated}
    (folder / META).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    cleanup(project, active={*(active or set()), folder})
    return folder


def runs(project: Path) -> list[Path]:
    """The project's traced runs, newest first (only folders divide marked as its own)."""
    return sim_flow.sessions(Path(project), cache=CACHE, meta=META)


def load_run(folder: Path) -> tuple[FunctionTrace, dict]:
    """A saved run's trace and scenario (no PHP runs)."""
    trace = read_trace(Path(folder) / TRACE_FILE)
    try:
        scenario = json.loads((Path(folder) / SCENARIO_FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        scenario = {}
    return trace, scenario if isinstance(scenario, dict) else {}


def cleanup(project: Path, *, keep: int = KEEP_RUNS, max_bytes: int = MAX_CACHE_BYTES,
            active: set[Path] | None = None) -> list[Path]:
    """Flow simulations' retention, on this cache only."""
    return sim_flow.cleanup(Path(project), keep=keep, max_bytes=max_bytes, active=active, cache=CACHE, meta=META)


# ---------------------------------------------------------------- playback
def _cut(value: object) -> bool:
    if isinstance(value, dict):
        return value.get("$type") in ("string", "binary", "depth") or "$truncated" in value \
            or any(_cut(v) for v in value.values())
    if isinstance(value, list):
        return any(_cut(v) for v in value)
    return False


@dataclass
class LineView:
    """What a playback shows at one event: the line, and the state before it ran."""

    event: dict
    line: int
    depth: int
    locals: dict  # the frame's variables (not the context), before the line ran
    context: dict  # the Function's context (depth 0), before the line ran
    cut: list[str] = field(default_factory=list)  # names whose value was cut by the bounds


class LinePlayback(sim_flow.Cursor):
    """A Function trace's PHP lines and a cursor over them. Moving changes nothing but the cursor;
    what is shown is folded from the events. Runner's semantic events are never here."""

    def __init__(self, trace: FunctionTrace) -> None:
        self.trace = trace
        self.events: list[dict] = trace.lines
        self.cursor = 0

    def next_same_depth(self, direction: int = 1) -> bool:
        """The next (or previous) line at the cursor's depth or shallower: over a closure's lines."""
        if not self.events:
            return False
        depth = self.events[self.cursor].get("depth", 0)
        i = self.cursor + direction
        while 0 <= i < len(self.events):
            if self.events[i].get("depth", 0) <= depth:
                return self.go(i)
            i += direction
        return self.go(len(self.events) - 1 if direction > 0 else 0)

    def view(self, upto: int | None = None) -> LineView | None:
        """The state before event ``upto`` (default: the cursor's) ran, folded from the events as the
        recorder diffed them: each event's ``locals``, and the ``after_call`` of the lines before it."""
        if not self.events:
            return None
        upto = self.cursor if upto is None else max(0, min(len(self.events) - 1, upto))
        frames: list[dict] = []
        for k, event in enumerate(self.events[:upto + 1]):
            level = int(event.get("depth") or 0)
            del frames[level + 1:]
            while len(frames) <= level:
                frames.append({})
            _apply(frames[level], event.get("locals"))
            if k < upto:
                _apply(frames[level], event.get("after_call"))
        event = self.events[upto]
        level = int(event.get("depth") or 0)
        mine = frames[level]
        local = {k: v for k, v in mine.items() if not k.startswith("context.") and k != "context"}
        top = frames[0] if frames else {}
        context = {k[len("context."):]: v for k, v in top.items() if k.startswith("context.")}
        cut = sorted([k for k, v in local.items() if _cut(v)] + [f"context.{k}" for k, v in context.items() if _cut(v)])
        return LineView(event, int(event["line"]), level, local, context, cut)
