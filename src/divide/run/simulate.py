"""Flow Simulation: a Runner Flow simulated with test doubles, its trace replayed (UI-independent).

divide does not interpret a Flow. A simulation is Runner's own (0.3.0 or newer),
through its command line:

    php vendor/divengine/runner/bin/run.php --json --simulate DOUBLES --session SESSION
        --trace TRACE [--context CONTEXT] [--trace-messages] -- FLOW

Runner compiles the YAML with its own compiler, runs it with its own runtime,
answers every ``condition`` and ``activity`` from the declared doubles (never
loading or calling a Function of the project), and writes a trace of semantic
events (protocol ``divengine.runner.trace``, version 1) and a session
(``divengine.runner.simulation-session``) from which the next segment of a paused
simulation resumes, in another process. divide reads the trace; replaying it
never runs PHP again.

Everything a simulation uses or writes is kept in a session folder of the
project's ``.div/simulation/`` (kept out of Git, with a size and count limit):
the Flow's YAML as it was simulated (a snapshot: the user's file, saved or not,
is never written, and a later edit does not change what was simulated), the
doubles, the initial context, Runner's session and one trace per segment.
Normal runs' checkpoints (``.div/runner/``) are never read or written here.
"""

from __future__ import annotations

from divide.i18n import _

import asyncio
import copy
import hashlib
import json
import os
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from divide.run import flowmodel as fm
from divide.run.flow import Runner, version_tuple
from divide.run.script import ScriptError, ScriptResult, run_script

PROTOCOL = "divengine.runner.trace"
VERSION = 1
SESSION_PROTOCOL = "divengine.runner.simulation-session"
MIN_VERSION = (0, 3, 0)
CACHE = Path(".div") / "simulation"  # the project's simulation sessions, out of Git
SPECS = Path(".div") / "simulations"  # the doubles files divide offers to make: the team's, versioned
META = "divide-session.json"  # what marks a folder as a session of divide's (only these are ever removed)
META_PROTOCOL = "divide.simulation-session"
KEEP_SESSIONS = 20
MAX_CACHE_BYTES = 64 * 1024 * 1024
MARGIN = 20.0  # seconds past Runner's own time budget before PHP is killed
DEFAULT_SECONDS = 10.0  # Runner's default time budget
SPEC_KEYS = ("description", "doubles", "budget", "trace")
BUDGET_KEYS = ("steps", "transfers", "seconds")
KINDS = ("returns", "throws", "pause", "sequence", "flow")
_MODULE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*$")  # Runner's MODULE_PATTERN
_IGNORE = "# divide's Flow simulations: snapshots, doubles, sessions and traces, not versioned\n*\n"


class SimulationError(Exception):
    """A simulation cannot start, or its trace cannot be read: the message says why, for the user."""


# ---------------------------------------------------------------- can Runner simulate?
def simulation_problem(runner: Runner) -> str | None:
    """Why the project's Runner cannot simulate (it has no ``--simulate``), or None. Run (Ctrl+F9) is
    not concerned: it runs the Flow for real with any Runner divide supports."""
    if not runner.usable:
        return runner.problem or _('Runner is not installed in this project.')
    numbers = version_tuple(runner.version) if runner.version else None
    if numbers is not None and numbers >= MIN_VERSION:
        return None
    if numbers is None:  # a branch (dev-main) or an unknown version: does its command line have --simulate?
        try:
            if runner.bootstrap is not None and "--simulate" in runner.bootstrap.read_text(encoding="utf-8", errors="replace"):
                return None
        except OSError:
            pass
    return _('Runner {version} is installed; Simulation needs 0.3.0 or newer, the first that simulates a Flow '
             '(composer require divengine/runner:^0.3). Nothing was run. Run (Ctrl+F9) still runs the Flow '
             'for real.').format(version=runner.version or "?")


# ---------------------------------------------------------------- what needs a double
@dataclass
class Requirement:
    """A function reference of the Flow (or of a nested Flow a double names), keyed as Runner keys
    doubles: ``module:name`` for a Step with a module, else the name."""

    key: str
    kinds: list[str] = field(default_factory=list)  # activity, condition
    places: list[str] = field(default_factory=list)  # block.step (prefixed by a nested Flow's file)
    flow: str = ""  # "" for the simulated Flow; a nested Flow's path as the double gives it


def reference_key(name: str, module: str) -> str:
    name, module = name.strip(), module.strip()
    return f"{module}:{name}" if module else name


def requirements(doc: fm.FlowDoc, *, project: Path | None = None, doubles: dict | None = None) -> list[Requirement]:
    """Every condition and activity the Flow references, and those of the nested Flows its doubles
    name (``{"flow": "child.yml"}``, read from the project's folder, as Runner does)."""
    found: dict[str, Requirement] = {}

    def add(document: fm.FlowDoc, where: str) -> None:
        for step in document.steps():
            module = step.get("module")
            for kind in fm.FUNCTION_ATTRS:
                attr = step.attrs.get(kind)
                if attr is None or attr.kind != "scalar" or not str(attr.value or "").strip():
                    continue
                key = reference_key(str(attr.value), module)
                req = found.setdefault(key, Requirement(key, flow=where))
                if kind not in req.kinds:
                    req.kinds.append(kind)
                place = f"{where}:{step.name}" if where else step.name
                if place not in req.places:
                    req.places.append(place)

    add(doc, "")
    seen: set[str] = set()
    pending = [spec.get("flow") for spec in (doubles or {}).values() if isinstance(spec, dict) and isinstance(spec.get("flow"), str)]
    while pending:
        path = pending.pop(0)
        if path in seen:
            continue
        seen.add(path)
        target = Path(path) if Path(path).is_absolute() or project is None else project / path
        try:
            child = fm.parse(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        add(child, path)
    return list(found.values())


def template(reqs: list[Requirement], description: str = "") -> dict:
    """A doubles file with a double for each reference: a condition true, an activity returning null.
    A start to edit, in Runner's ``--simulate`` format."""
    doubles = {}
    for req in reqs:
        doubles[req.key] = {"returns": True} if req.kinds == ["condition"] else {"returns": None}
    out: dict = {"description": description} if description else {}
    out["doubles"] = doubles
    out["budget"] = {"steps": 1000, "transfers": 1000, "seconds": DEFAULT_SECONDS}
    return out


# ---------------------------------------------------------------- the doubles file
@dataclass
class SpecCheck:
    problems: list[str] = field(default_factory=list)  # the file's shape: refused
    warnings: list[str] = field(default_factory=list)  # said, not refused
    missing: list[Requirement] = field(default_factory=list)  # references without a double: refused

    @property
    def ok(self) -> bool:
        return not self.problems and not self.missing

    def messages(self) -> list[str]:
        """Why a simulation is refused, each reason in the Flow's terms."""
        return self.problems + [_('No double for {name} ({kinds}, used by {places})').format(
            name=r.key, kinds="/".join(r.kinds), places=", ".join(r.places[:4])) for r in self.missing]


def _outcome_problems(outcome, label: str, condition: bool) -> list[str]:
    if not isinstance(outcome, dict):
        return [_('{label}: an outcome is a JSON object').format(label=label)]
    unknown = sorted(set(outcome) - {"returns", "throws", "pause", "context"})
    kinds = [k for k in ("returns", "throws", "pause") if k in outcome]
    if unknown or len(kinds) != 1:
        return [_('{label}: needs exactly one of returns, throws, pause (and optionally context)').format(label=label)]
    out = []
    if kinds[0] == "throws" and (not isinstance(outcome["throws"], str) or not outcome["throws"].strip()):
        out.append(_('{label}: throws takes an error message').format(label=label))
    if kinds[0] == "pause":
        if outcome["pause"] is not True:
            out.append(_('{label}: pause must be true').format(label=label))
        elif condition:
            out.append(_('{label}: a condition cannot pause (Runner has no condition pause)').format(label=label))
    if "context" in outcome:
        context = outcome["context"]
        if kinds[0] == "throws" or not isinstance(context, dict):
            out.append(_('{label}: context is a JSON object, with returns or pause').format(label=label))
        else:
            hidden = [k for k in context if str(k).startswith("_")]
            if hidden:
                out.append(_('{label}: context keys starting with _ are Runner\'s: {keys}').format(label=label, keys=", ".join(hidden)))
    return out


def check_spec(data: object, reqs: list[Requirement], project: Path) -> SpecCheck:
    """What is wrong with a doubles file (Runner's ``--simulate`` format) before anything runs: its
    shape, as Runner validates it, and every reference of the Flow without a double. Runner checks it
    again; this only refuses earlier, and says it in the Flow's terms."""
    check = SpecCheck()
    if not isinstance(data, dict):
        check.problems.append(_('The doubles file must be a JSON object: {"doubles": {...}}'))
        return check
    unknown = sorted(set(data) - set(SPEC_KEYS))
    if unknown:
        check.problems.append(_('Unknown key(s) in the doubles file: {keys} (Runner takes {allowed})').format(
            keys=", ".join(unknown), allowed=", ".join(SPEC_KEYS)))
    doubles = data.get("doubles", {})
    if not isinstance(doubles, dict):
        check.problems.append(_('"doubles" must be a JSON object: function -> double'))
        doubles = {}
    for key in ("budget", "trace"):
        if key in data and not isinstance(data[key], dict):
            check.problems.append(_('"{key}" must be a JSON object').format(key=key))
    budget = data.get("budget") if isinstance(data.get("budget"), dict) else {}
    for key, value in budget.items():
        if key not in BUDGET_KEYS:
            check.problems.append(_('Unknown budget {key} (Runner takes steps, transfers, seconds)').format(key=key))
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            check.problems.append(_('The budget {key} must be a positive number').format(key=key))
    kinds_of = {req.key: req.kinds for req in reqs}
    for name, spec in doubles.items():
        label = _('Double {name}').format(name=name)
        if not name or name.strip() != name:
            check.problems.append(_('A double has an empty name, or spaces around it: "{name}"').format(name=name))
            continue
        if ":" in name and "::" not in name:
            module = name.split(":", 1)[0]
            if not _MODULE.match(module):
                check.problems.append(_('{label}: "{module}" is not a Module name').format(label=label, module=module))
        if not isinstance(spec, dict):
            check.problems.append(_('{label}: a double is a JSON object').format(label=label))
            continue
        kinds = [k for k in KINDS if k in spec]
        if len(kinds) != 1:
            check.problems.append(_('{label}: needs exactly one of returns, throws, pause, sequence, flow').format(label=label))
            continue
        condition = kinds_of.get(name) == ["condition"]
        if kinds[0] == "flow":
            path = spec["flow"]
            extra = sorted(set(spec) - {"flow", "description"})
            if extra or not isinstance(path, str) or not path.lower().endswith((".yml", ".yaml")):
                check.problems.append(_('{label}: flow takes only a .yml or .yaml path').format(label=label))
            elif not ((project / path) if not Path(path).is_absolute() else Path(path)).is_file():
                check.problems.append(_('{label}: no nested Flow {path} (relative to the project)').format(label=label, path=path))
        elif kinds[0] == "sequence":
            seq = spec["sequence"]
            extra = sorted(set(spec) - {"sequence", "description"})
            if extra or not isinstance(seq, list) or not seq:
                check.problems.append(_('{label}: sequence is a non-empty list of outcomes').format(label=label))
            else:
                for i, outcome in enumerate(seq):
                    check.problems += _outcome_problems(outcome, f"{label}, sequence[{i}]", condition)
        else:
            outcome = {k: v for k, v in spec.items() if k != "description"}
            check.problems += _outcome_problems(outcome, label, condition)
        if name not in kinds_of:
            check.warnings.append(_('{name} has a double but the Flow does not use it').format(name=name))
    for req in reqs:
        if req.key not in doubles:
            check.missing.append(req)
    return check


def read_spec(path: Path) -> object:
    """The doubles file's data; SimulationError when it cannot be read as JSON."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SimulationError(_('The doubles file {name} cannot be read: {error}').format(name=path.name, error=exc)) from exc
    except (UnicodeDecodeError, ValueError) as exc:
        raise SimulationError(_('The doubles file {name} is not JSON: {error}').format(name=path.name, error=exc)) from exc


def default_spec_path(flow: Path, project: Path) -> Path:
    """Where divide offers the doubles of a Flow: ``.div/simulations/<flow path>.doubles.json``, a file
    of the project the team can share (unlike the sessions)."""
    try:
        rel = flow.relative_to(project)
    except ValueError:
        rel = Path("outside") / flow.name
    return project / SPECS / rel.parent / (rel.name + ".doubles.json")


# ---------------------------------------------------------------- the trace
@dataclass
class Trace:
    """A trace document Runner wrote (protocol ``divengine.runner.trace`` v1). Unknown fields and event
    types are kept and ignored, as the protocol asks."""

    data: dict
    events: list[dict]

    @property
    def result(self) -> dict:
        r = self.data.get("result")
        return r if isinstance(r, dict) else {}

    @property
    def state(self) -> str:
        return str(self.result.get("state") or "?")

    @property
    def truncated(self) -> bool:
        return bool(self.data.get("truncated"))

    @property
    def truncation(self) -> dict:
        t = self.data.get("truncation")
        return t if isinstance(t, dict) else {}

    @property
    def fingerprint(self) -> str:
        return str(self.data.get("fingerprint") or "")

    @property
    def double_calls(self) -> dict:
        sim = self.data.get("simulation")
        calls = sim.get("double_calls") if isinstance(sim, dict) else None
        return calls if isinstance(calls, dict) else {}


def parse_trace(data: object) -> Trace:
    """A trace from its JSON data; SimulationError for another protocol or version, or a shape that
    is not a trace."""
    if not isinstance(data, dict):
        raise SimulationError(_('The trace is not a JSON object.'))
    protocol, version = data.get("protocol"), data.get("version")
    if protocol != PROTOCOL:
        raise SimulationError(_('Not a Runner trace (protocol {protocol!r}; divide reads {expected}).').format(
            protocol=protocol, expected=PROTOCOL))
    if version != VERSION:
        raise SimulationError(_('Runner trace version {version}: this divide reads version {expected}. '
                                'Update divide, or use the Runner it supports.').format(version=version, expected=VERSION))
    events = data.get("events")
    if not isinstance(events, list):
        raise SimulationError(_('The trace has no list of events.'))
    kept = [e for e in events if isinstance(e, dict) and isinstance(e.get("type"), str)]
    return Trace(data, kept)


def read_trace(path: Path) -> Trace:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SimulationError(_('The trace {name} cannot be read: {error}').format(name=path.name, error=exc)) from exc
    except (UnicodeDecodeError, ValueError) as exc:
        raise SimulationError(_('The trace {name} is not JSON: {error}').format(name=path.name, error=exc)) from exc
    return parse_trace(data)


# ---------------------------------------------------------------- sessions
def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cache_dir(project: Path) -> Path:
    return project / CACHE


def prepare_cache(project: Path) -> Path:
    folder = cache_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    ignore = folder / ".gitignore"
    if not ignore.exists():
        ignore.write_text(_IGNORE, encoding="utf-8")
    return folder


@dataclass
class Segment:
    """One process of a simulation: from its start or a pause to its end or the next pause."""

    number: int
    state: str  # done, paused, error (Runner's); invocation (exit 2); crashed; cancelled; timeout
    exit_code: int | None
    seconds: float
    trace: Trace | None = None
    problem: str | None = None  # why there is no trace, or it could not be read
    stderr: str = ""
    diagnostics: list[str] = field(default_factory=list)  # Runner's "runner: ..." lines

    @property
    def ok(self) -> bool:
        return self.state in ("done", "paused")


@dataclass
class Session:
    """A simulation's folder in the project's cache, and what started it."""

    folder: Path
    project: Path
    flow: Path  # the user's Flow file the snapshot was taken from
    meta: dict = field(default_factory=dict)
    segments: list[Segment] = field(default_factory=list)

    @property
    def snapshot(self) -> Path:
        return self.folder / "flow.yml"

    @property
    def doubles(self) -> Path:
        return self.folder / "doubles.json"

    @property
    def context(self) -> Path:
        return self.folder / "context.json"

    @property
    def session_file(self) -> Path:
        return self.folder / "session.json"

    def trace_file(self, number: int) -> Path:
        return self.folder / f"trace-{number}.json"

    @property
    def snapshot_text(self) -> str:
        try:
            return self.snapshot.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

    @property
    def paused(self) -> bool:
        return bool(self.segments) and self.segments[-1].state == "paused"

    @property
    def traces(self) -> list[Trace]:
        return [s.trace for s in self.segments if s.trace is not None]

    def save_meta(self) -> None:
        self.meta["segments"] = [{"number": s.number, "state": s.state, "exit_code": s.exit_code,
                                  "seconds": round(s.seconds, 3), "problem": s.problem} for s in self.segments]
        tmp = self.folder / (META + ".tmp")
        tmp.write_text(json.dumps(self.meta, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.folder / META)

    def changed(self, current_text: str | None, spec_path: Path | None = None) -> list[str]:
        """What differs now from what this simulation ran: the Flow's YAML (the editor's text, saved
        or not) and the doubles file it was copied from. Replay and resume use the snapshot either way."""
        out = []
        if current_text is not None and _sha(current_text.encode("utf-8")) != self.meta.get("flow_sha256"):
            out.append(_('the Flow\'s YAML'))
        source = spec_path or (self.project / self.meta["doubles_from"] if self.meta.get("doubles_from") else None)
        if source is not None:
            try:
                now = _sha(source.read_bytes())
            except OSError:
                now = None
            if now != self.meta.get("doubles_sha256"):
                out.append(_('the doubles file'))
        return out


def _relative(path: Path, project: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return str(path)


def new_session(project: Path, flow: Path, flow_text: str, spec_data: dict, spec_from: Path | None,
                context: dict, *, context_from: str = "", messages: bool = False) -> Session:
    """A new session folder: the Flow's YAML as it is now (the snapshot Runner simulates), the doubles
    and the initial context. The user's files are only read."""
    cache = prepare_cache(project)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = re.sub(r"[^A-Za-z0-9_.-]", "_", flow.stem)[:40] or "flow"
    folder = cache / f"{stamp}-{base}"
    n = 1
    while folder.exists():
        n += 1
        folder = cache / f"{stamp}-{base}-{n}"
    folder.mkdir(parents=True)
    session = Session(folder, project, flow)
    session.snapshot.write_text(flow_text, encoding="utf-8")
    session.doubles.write_text(json.dumps(spec_data, indent=2, ensure_ascii=False), encoding="utf-8")
    session.context.write_text(json.dumps(context if context else {}, indent=2, ensure_ascii=False), encoding="utf-8")
    spec_sha = None
    if spec_from is not None:
        try:
            spec_sha = _sha(spec_from.read_bytes())
        except OSError:
            spec_sha = None
    session.meta = {
        "protocol": META_PROTOCOL, "version": 1, "flow": _relative(flow, project),
        "flow_sha256": _sha(flow_text.encode("utf-8")),
        "doubles_from": _relative(spec_from, project) if spec_from is not None else None,
        "doubles_sha256": spec_sha, "context_from": context_from, "messages": messages,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "segments": [],
    }
    session.save_meta()
    return session


def load_session(folder: Path, project: Path) -> Session:
    """A session divide saved, with its segments' traces read again (no PHP runs)."""
    try:
        meta = json.loads((folder / META).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SimulationError(_('{name} is not a simulation of divide: {error}').format(name=folder.name, error=exc)) from exc
    if not isinstance(meta, dict) or meta.get("protocol") != META_PROTOCOL:
        raise SimulationError(_('{name} is not a simulation of divide').format(name=folder.name))
    session = Session(folder, project, project / str(meta.get("flow") or "flow.yml"), meta)
    for item in meta.get("segments") or []:
        if not isinstance(item, dict):
            continue
        number = int(item.get("number") or len(session.segments) + 1)
        segment = Segment(number, str(item.get("state") or "?"), item.get("exit_code"), float(item.get("seconds") or 0),
                          problem=item.get("problem"))
        path = session.trace_file(number)
        if path.is_file():
            try:
                segment.trace = read_trace(path)
            except SimulationError as exc:
                segment.problem = str(exc)
        session.segments.append(segment)
    return session


def sessions(project: Path, *, cache: Path = CACHE, meta: str = META) -> list[Path]:
    """The project's simulation sessions, newest first (only folders divide marked as its own with
    ``meta``). ``cache`` and ``meta`` default to Flow simulations'; Function simulations
    (:mod:`divide.run.functrace`) keep theirs apart, in their own folder."""
    folder = project / cache
    if not folder.is_dir():
        return []
    found = [p for p in folder.iterdir() if p.is_dir() and (p / meta).is_file()]
    return sorted(found, key=lambda p: (p / meta).stat().st_mtime, reverse=True)


def _size(folder: Path) -> int:
    total = 0
    for path in folder.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except OSError:
            pass
    return total


def cleanup(project: Path, *, keep: int = KEEP_SESSIONS, max_bytes: int = MAX_CACHE_BYTES,
            active: set[Path] | None = None, cache: Path = CACHE, meta: str = META) -> list[Path]:
    """Remove the oldest sessions past ``keep`` or ``max_bytes`` in all; never one in ``active`` (open in a
    window), never anything that is not a session folder of divide's (marked with ``meta``, in
    ``cache``). Returns what was removed."""
    active = {p.resolve() for p in (active or set())}
    removed: list[Path] = []
    total = 0
    for n, folder in enumerate(sessions(project, cache=cache, meta=meta)):
        size = _size(folder)
        if folder.resolve() in active or (n < keep and total + size <= max_bytes):
            total += size
            continue
        if not (folder / meta).is_file() or folder.is_symlink():
            continue
        shutil.rmtree(folder, ignore_errors=True)
        removed.append(folder)
    return removed


# ---------------------------------------------------------------- running a segment
def segment_command(session: Session, number: int, *, messages: bool = False) -> list[str]:
    """The bootstrap's arguments for segment ``number`` (after ``php run.php``): the first gives the
    initial context, a later one resumes from Runner's session file."""
    args = ["--json", "--simulate", str(session.doubles), "--session", str(session.session_file),
            "--trace", str(session.trace_file(number))]
    if number == 1:
        args += ["--context", str(session.context)]
    if messages:
        args.append("--trace-messages")
    return [*args, "--", str(session.snapshot)]


def time_limit(spec: dict) -> float:
    """How long PHP may take before divide kills it: Runner's own time budget, and a margin."""
    budget = spec.get("budget") if isinstance(spec.get("budget"), dict) else {}
    seconds = budget.get("seconds")
    seconds = float(seconds) if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds > 0 else DEFAULT_SECONDS
    return seconds + MARGIN


def _state_of(result: ScriptResult, timed_out: bool) -> str:
    if timed_out:
        return "timeout"
    if result.stopped:
        return "cancelled"
    return {0: "done", 3: "paused", 1: "error", 2: "invocation"}.get(result.exit_code, "crashed")  # type: ignore[arg-type]


async def run_segment(runner: Runner, session: Session, *, php: str | None = None, timeout: float | None = None,
                      on_data: Callable[[bytes, bytes], None] | None = None) -> Segment:
    """The next segment of ``session``, in a PHP process of its own, in the project's folder (where
    Runner resolves a nested Flow's path). Cancelling the task stops PHP: the segment is ``cancelled``,
    Runner's session file is left as it was (Runner writes it only at the end), and no trace is kept."""
    if runner.bootstrap is None:
        raise SimulationError(runner.problem or _('Runner is not installed in this project.'))
    if session.paused is False and session.segments:
        raise SimulationError(_('This simulation ended {state}: there is nothing to resume.').format(state=session.segments[-1].state))
    number = len(session.segments) + 1
    if number > 1 and not session.session_file.is_file():
        raise SimulationError(_('The session file of this simulation is gone: it cannot be resumed.'))
    trace_file = session.trace_file(number)
    try:
        spec = json.loads(session.doubles.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        spec = {}
    limit = timeout if timeout is not None else time_limit(spec if isinstance(spec, dict) else {})
    args = segment_command(session, number, messages=bool(session.meta.get("messages")))
    job = asyncio.ensure_future(run_script(runner.bootstrap, args, cwd=session.project, php=php, on_data=on_data))
    timed_out = False
    try:
        result = await asyncio.wait_for(asyncio.shield(job), limit)
    except asyncio.TimeoutError:
        job.cancel()
        result = await job
        timed_out = True
    except asyncio.CancelledError:
        job.cancel()
        result = await asyncio.shield(job)
        result.stopped = True
    except ScriptError as exc:
        raise SimulationError(str(exc)) from exc
    state = _state_of(result, timed_out)
    segment = Segment(number, state, result.exit_code, result.seconds, stderr=result.errors)
    segment.diagnostics = [line[len("runner: "):] for line in result.errors.splitlines() if line.startswith("runner: ")]
    if state in ("cancelled", "timeout"):
        try:
            trace_file.unlink()
        except OSError:
            pass
        segment.problem = (_('Stopped by you: PHP was killed; the simulation stays where it was.') if state == "cancelled"
                           else _('PHP took more than {seconds:.0f}s and was killed; the simulation stays where it was.').format(seconds=limit))
    elif trace_file.is_file():
        try:
            segment.trace = read_trace(trace_file)
        except SimulationError as exc:
            segment.problem = str(exc)
    else:
        segment.problem = "\n".join(segment.diagnostics) or result.errors.strip() or _('Runner wrote no trace.')
    if segment.trace is not None and segment.trace.state in ("done", "paused", "error") and state in ("done", "paused", "error") \
            and segment.trace.state != state:
        segment.problem = _('Runner exited {code} but its trace says {state}.').format(code=result.exit_code, state=segment.trace.state)
    if segment.trace is not None:  # a segment Runner ran; a refused or killed one left Runner's session as it was
        session.segments.append(segment)
        session.save_meta()
    return segment


# ---------------------------------------------------------------- playback
Key = tuple  # ("step", block, id) | ("block", id), as the board's


@dataclass
class Event:
    segment: int  # 1-based
    data: dict

    @property
    def type(self) -> str:
        return str(self.data.get("type") or "")

    @property
    def seq(self) -> int:
        return int(self.data.get("seq") or 0)

    @property
    def depth(self) -> int:
        return int(self.data.get("flow_depth") or 0)

    @property
    def block(self) -> str | None:
        b = self.data.get("block")
        return str(b) if b is not None else None

    @property
    def step(self) -> str | None:
        s = self.data.get("step")
        return str(s) if s is not None else None

    def key(self) -> Key | None:
        if self.block is not None and self.step is not None:
            return ("step", self.block, self.step)
        return None


@dataclass
class View:
    """What the board and the inspector show at the playback cursor."""

    marks: dict = field(default_factory=dict)  # Step key -> current, visited, skipped, paused, failed, active
    taken: set = field(default_factory=set)  # (Step key, call|jump)
    current: Key | None = None
    context: dict = field(default_factory=dict)  # the business keys, rebuilt from the trace up to the cursor
    approximate: bool = False  # a value in the rebuilt context was cut by the trace's caps
    stack: list = field(default_factory=list)  # pending call frames: the calling Steps, oldest first
    scope: list = field(default_factory=list)  # nested Flow scopes entered (their functions), outermost first


def _cut_value(value) -> bool:
    return isinstance(value, dict) and value.get("$type") in ("truncated", "more")


class Cursor:
    """A list of recorded events and a position in it: first, last, next, previous. Moving changes
    nothing but the position. Shared by a Flow simulation's :class:`Playback` (Runner's semantic
    events) and a Function simulation's line playback (:mod:`divide.run.functrace`, PHP lines);
    the two never share their events."""

    events: list
    cursor: int = 0

    def __len__(self) -> int:
        return len(self.events)

    @property
    def event(self) -> Event | None:
        return self.events[self.cursor] if self.events else None

    def go(self, index: int) -> bool:
        if not self.events:
            return False
        index = max(0, min(len(self.events) - 1, index))
        moved = index != self.cursor
        self.cursor = index
        return moved

    def first(self) -> bool:
        return self.go(0)

    def last(self) -> bool:
        return self.go(len(self.events) - 1)

    def next(self, step: int = 1) -> bool:
        return self.go(self.cursor + step)


class Playback(Cursor):
    """A simulation's events, every segment one after the other, and a cursor over them. Moving the
    cursor changes nothing but the cursor: what the board shows is computed from the events."""

    def __init__(self, traces: list[Trace], doc: fm.FlowDoc) -> None:
        self.doc = doc
        self.events: list[Event] = [Event(n, e) for n, t in enumerate(traces, 1) for e in t.events]
        self.segments = len(traces)
        self.cursor = 0

    def _is_step(self, event: Event) -> bool:
        return event.type in ("step.start", "step.skip") and event.depth == 0

    def next_step(self, direction: int = 1) -> bool:
        """The next (or previous) Step started or skipped in the simulated Flow."""
        i = self.cursor + direction
        while 0 <= i < len(self.events):
            if self._is_step(self.events[i]):
                return self.go(i)
            i += direction
        return self.go(len(self.events) - 1 if direction > 0 else 0)

    def find_step(self, key: Key) -> bool:
        """The next event of Step ``key`` after the cursor (from the start again past the last)."""
        n = len(self.events)
        for k in range(1, n + 1):
            i = (self.cursor + k) % n
            event = self.events[i]
            if event.depth == 0 and event.key() == key and event.type in ("step.start", "step.skip"):
                return self.go(i) or True
        return False

    def occurrences(self, key: Key) -> int:
        return sum(1 for e in self.events if e.depth == 0 and e.type == "step.start" and e.key() == key)

    # ------------------------------------------------------------ what is shown
    def _step_at(self, block: str | None, index) -> Key | None:
        b = self.doc.block(str(block)) if block is not None else None
        if b is None or not isinstance(index, int) or not 1 <= index <= len(b.steps):
            return None
        return ("step", b.id, b.steps[index - 1].id)

    def view(self, upto: int | None = None) -> View:
        """The board's marks, the taken connections, the call stack and the context after the event at
        ``upto`` (the cursor by default), from the events alone."""
        upto = self.cursor if upto is None else upto
        view = View()
        marks: dict = {}
        stack: list = []
        started: Key | None = None  # the last Step started and not left
        for event in self.events[:upto + 1]:
            data, kind = event.data, event.type
            if kind == "run.start":
                ctx = data.get("context")
                view.context = copy.deepcopy(ctx) if isinstance(ctx, dict) else {}
                view.approximate = False
                checkpoint = data.get("checkpoint") if isinstance(data.get("checkpoint"), dict) else {}
                frames = checkpoint.get("flow_stack") if isinstance(checkpoint.get("flow_stack"), list) else []
                stack = [k for k in (self._step_at(f.get("block"), f.get("step_index")) for f in frames if isinstance(f, dict)) if k]
                if data.get("resume"):  # the pause is over: the Step that paused ran
                    marks = {k: ("visited" if m == "paused" else m) for k, m in marks.items()}
                view.scope = []
                started = None
                continue
            if kind == "flow.enter":
                view.scope.append(str(data.get("function") or data.get("initial_block") or "?"))
                continue
            if kind == "flow.exit":
                if view.scope:
                    view.scope.pop()
                continue
            if event.depth != 0:
                continue
            key = event.key()
            if kind == "step.start" and key is not None:
                started = key
                marks[key] = "visited"
            elif kind == "step.skip" and key is not None:
                reason = data.get("reason")
                if reason == "before_checkpoint":
                    marks.setdefault(key, "visited")  # it ran before the pause
                elif reason == "condition_false" or key not in marks:
                    marks[key] = "skipped"
                if started == key:
                    started = None
            elif kind in ("activity.error", "condition.error", "function.missing") and key is not None:
                marks[key] = "failed"
            elif kind == "function.missing" and started is not None:
                marks[started] = "failed"
            elif kind == "pause" and key is not None:
                marks[key] = "paused"
            elif kind in ("call", "jump") and key is not None:
                view.taken.add((key, kind))
                if kind == "call":
                    stack.append(key)
            elif kind == "call.return":
                if stack:
                    stack.pop()
            elif kind == "call.drop":
                frames = data.get("frames")
                count = len(frames) if isinstance(frames, list) else (frames if isinstance(frames, int) else 0)
                del stack[max(0, len(stack) - count):]
            elif kind in ("block.exit",):
                started = None
            elif kind == "run.end":
                started = None
                ctx = data.get("context")
                if isinstance(ctx, dict):
                    view.context = copy.deepcopy(ctx)
                    view.approximate = False
            changes = data.get("changes")
            if isinstance(changes, list) and kind != "run.end":
                for change in changes:
                    if not isinstance(change, dict) or "key" not in change:
                        if _cut_value(change):
                            view.approximate = True
                        continue
                    name, op = str(change["key"]), change.get("op")
                    if op == "removed":
                        view.context.pop(name, None)
                    elif "after" in change:
                        view.context[name] = copy.deepcopy(change["after"])
                        if _cut_value(change["after"]):
                            view.approximate = True
            elif _cut_value(changes):
                view.approximate = True
        for key in stack:
            if marks.get(key) not in ("failed", "paused"):
                marks[key] = "active"
        event = self.events[upto] if self.events else None
        current = event.key() if event is not None and event.depth == 0 else None
        if current is None and event is not None and event.depth == 0:
            if event.type == "call.return":  # back in the calling Step
                current = self.target_key(event.data.get("to"))
            elif event.type == "run.end" and event.data.get("state") == "paused":  # where it waits
                checkpoint = event.data.get("checkpoint") if isinstance(event.data.get("checkpoint"), dict) else {}
                state = checkpoint.get("flow_state") if isinstance(checkpoint.get("flow_state"), dict) else {}
                current = self._step_at(state.get("block"), state.get("step_index"))
        if current is None and event is not None and event.depth != 0:
            current = stack[-1] if stack else started  # inside a nested Flow: the Step that runs it
        if current is None and event is not None and event.type not in ("run.end", "block.exit", "trace.truncated"):
            current = started
        if current is not None and marks.get(current) not in ("failed", "paused", "skipped"):
            marks[current] = "current"
        view.marks, view.stack, view.current = marks, stack, current
        return view

    def logs_near(self, index: int | None = None) -> list[Event]:
        """The log events of the Step occurrence the event at ``index`` belongs to."""
        index = self.cursor if index is None else index
        if not self.events:
            return []
        start = index
        while start > 0 and self.events[start].type != "step.start":
            start -= 1
        end = index + 1
        while end < len(self.events) and self.events[end].type not in ("step.start", "run.end"):
            end += 1
        return [e for e in self.events[start:end] if e.type == "log"]

    def step_index(self, key: Key) -> int | None:
        """The 1-based position of a Step in its Block (as Runner counts it)."""
        block = self.doc.block(key[1]) if key and key[0] == "step" else None
        if block is None:
            return None
        ids = [s.id for s in block.steps]
        return ids.index(key[2]) + 1 if key[2] in ids else None

    def target_key(self, target) -> Key | None:
        """A ``call``/``jump`` target or a return place ({block, index}) as a board key."""
        if not isinstance(target, dict):
            return None
        if target.get("step") is not None and target.get("block") is not None:
            return ("step", str(target["block"]), str(target["step"]))
        return self._step_at(target.get("block"), target.get("index"))
