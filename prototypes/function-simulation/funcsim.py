"""Proof of concept for divide #15: Mock Simulation of one Runner Function, with a PHP line trace.

Not part of divide's package and not wired to the UI. It answers three questions with running code:

1. Can a Runner Function be called with its dependencies replaced by explicit doubles, and fail
   loudly when one is missing? (``funcsim.php``: an ``_importer`` double, strict service doubles,
   no Composer autoload, an autoloader that throws.)
2. Can divide record, line by line, what the Function's PHP did, with its locals, by reusing its
   Xdebug client (``divide.run.dbgp.DebugSession``) non-interactively? (``trace_lines``.)
3. What does a bounded, versioned scenario and trace look like? (``check_scenario``, ``simulate``.)

Usage::

    python prototypes/function-simulation/funcsim.py PROJECT FUNCTION_FILE SCENARIO.json [--trace] [--tripwire]

The result is ``divide.function-trace`` v1 JSON on stdout.

This runs the Function's real PHP code. Doubles replace what the Function asks its context for;
PHP's own functions (files, PDO, curl, ...) are not intercepted. ``--tripwire`` adds
``disable_functions`` and ``open_basedir`` to make some direct side effects fail; it is not a
sandbox either (see docs/function-simulation.md).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:  # a prototype: run from the repository
    sys.path.insert(0, str(ROOT / "src"))

from divide.run.dbgp import NS, DebugError, DebugSession, _text  # noqa: E402

HARNESS = Path(__file__).with_name("funcsim.php")
PROTOCOL = "divide.function-simulation"
TRACE_PROTOCOL = "divide.function-trace"
VERSION = 1
OUTCOMES = ("returns", "throws", "sequence")
LIMITS = {"lines": (2000, 100_000), "seconds": (20, 300), "stdout": (65_536, 4 * 1024 * 1024)}  # default, maximum
LOCALS_BYTES = 256 * 1024  # one eval of the locals
# What --tripwire disables: process, network, mail and the commonest file writes. A deny-list: not a sandbox.
TRIPWIRE = (
    "exec,shell_exec,system,passthru,proc_open,popen,pcntl_exec,pcntl_fork,"
    "mail,fsockopen,pfsockopen,stream_socket_client,stream_socket_server,socket_create,socket_connect,"
    "curl_init,curl_exec,curl_multi_exec,"
    "file_put_contents,fwrite,fputs,unlink,rename,copy,mkdir,rmdir,touch,chmod,chown,symlink,link,tempnam,tmpfile,"
    "putenv,ini_set,set_include_path,dl"
)


class ScenarioError(ValueError):
    """The scenario is not one this version runs (nothing was run)."""


# ------------------------------------------------------------------ scenario
def _outcome_problems(where: str, outcome: object, *, in_sequence: bool = False) -> list[str]:
    if not isinstance(outcome, dict):
        return [f"{where}: an outcome is an object"]
    kinds = [k for k in OUTCOMES if k in outcome]
    problems = []
    if in_sequence and "sequence" in kinds:
        problems.append(f"{where}: a sequence cannot hold a sequence")
    if len(kinds) != 1:
        problems.append(f"{where}: exactly one of returns, throws, sequence ({', '.join(kinds) or 'none'})")
    if unknown := set(outcome) - {*OUTCOMES, "context"}:
        problems.append(f"{where}: unknown {', '.join(sorted(unknown))}")
    ctx = outcome.get("context")
    if ctx is not None and (not isinstance(ctx, dict) or any(str(k).startswith("_") for k in ctx)):
        problems.append(f"{where}: context is an object without '_' keys")
    if "throws" in outcome and not isinstance(outcome["throws"], str):
        problems.append(f"{where}: throws is a message")
    if "sequence" in outcome:
        seq = outcome["sequence"]
        if not isinstance(seq, list) or not seq:
            problems.append(f"{where}: sequence is a non-empty list")
        else:
            for i, item in enumerate(seq):
                problems += _outcome_problems(f"{where}.sequence[{i}]", item, in_sequence=True)
    return problems


def check_scenario(data: object) -> list[str]:
    """What is wrong with a scenario; empty when it can run."""
    if not isinstance(data, dict):
        return ["a scenario is a JSON object"]
    problems = []
    if data.get("protocol") != PROTOCOL or data.get("version") != VERSION:
        problems.append(f"not {PROTOCOL} version {VERSION}")
    func = data.get("function")
    if not isinstance(func, dict) or not isinstance(func.get("name"), str) or not func["name"].strip():
        problems.append("function.name is missing")
    elif func.get("sha256") is not None and not (isinstance(func["sha256"], str) and len(func["sha256"]) == 64):
        problems.append("function.sha256 is a sha256 hex digest")
    if not isinstance(data.get("context", {}), dict):
        problems.append("context is a JSON object")
    elif any(str(k).startswith("_") for k in data.get("context", {})):
        problems.append("context keys starting with '_' belong to Runner")
    if data.get("unknown", "fail") != "fail":
        problems.append("unknown: only \"fail\" (a missing double never calls the real dependency)")
    doubles = data.get("doubles", {})
    if not isinstance(doubles, dict) or set(doubles) - {"importer", "services"}:
        problems.append("doubles has importer and services only")
        doubles = {}
    for key, outcome in (doubles.get("importer") or {}).items():
        problems += _outcome_problems(f"doubles.importer.{key}", outcome)
    for service, methods in (doubles.get("services") or {}).items():
        if str(service).startswith("_"):
            problems.append(f"doubles.services.{service}: '_' keys belong to Runner")
        if not isinstance(methods, dict) or not methods:
            problems.append(f"doubles.services.{service}: an object of methods")
            continue
        for method, outcome in methods.items():
            problems += _outcome_problems(f"doubles.services.{service}.{method}", outcome)
    limits = data.get("limits", {})
    if not isinstance(limits, dict) or set(limits) - set(LIMITS):
        problems.append(f"limits has {', '.join(LIMITS)} only")
    else:
        for key, value in limits.items():
            top = LIMITS[key][1]
            if not isinstance(value, int) or isinstance(value, bool) or not 0 < value <= top:
                problems.append(f"limits.{key}: 1..{top}")
    if not isinstance(data.get("autoload", False), bool):
        problems.append("autoload is true or false")
    return problems


def limit(scenario: dict, key: str) -> int:
    return int((scenario.get("limits") or {}).get(key, LIMITS[key][0]))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ the run
@dataclass
class Simulation:
    status: str  # returned exception fatal exit missing stale timeout line_limit crashed
    result: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    truncated: bool = False
    seconds: float = 0.0
    stderr: str = ""
    stdout: str = ""  # the harness's own (the Function's output is in the result)

    def document(self, project: Path, file: Path, scenario: dict) -> dict:
        """The ``divide.function-trace`` v1 document."""
        result = dict(self.result)
        result["status"] = self.status
        return {
            "protocol": TRACE_PROTOCOL, "version": VERSION,
            "scenario": {"sha256": hashlib.sha256(json.dumps(scenario, sort_keys=True).encode()).hexdigest(),
                         "description": scenario.get("description", "")},
            "function": {"module": scenario["function"].get("module"), "name": scenario["function"]["name"],
                         "file": _rel(file, project), "sha256": result.pop("sha256", None)},
            "result": result,
            "events": self.events,
            "truncated": self.truncated,
            "seconds": round(self.seconds, 3),
            "stderr": self.stderr[:65536],
        }


def _rel(path: Path, project: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return str(path)


def tripwire(project: Path, work: Path) -> list[str]:
    """INI for --tripwire: a deny-list and a filesystem fence (not a sandbox)."""
    fence = os.pathsep.join(str(p) for p in (project.resolve(), HARNESS.parent.resolve(), work.resolve()))
    return ["-d", f"disable_functions={TRIPWIRE}", "-d", f"open_basedir={fence}", "-d", "allow_url_fopen=0",
            "-d", "allow_url_include=0"]


def _request(project: Path, file: Path, scenario: dict, work: Path) -> tuple[Path, str]:
    nonce = "divide-funcsim-" + secrets.token_hex(16)
    request_file = work / "request.json"
    autoload = project / "vendor" / "autoload.php"
    request_file.write_text(json.dumps({
        "scenario": scenario, "file": str(file.resolve()), "nonce": nonce,
        "autoload": str(autoload) if autoload.is_file() else "",
    }), encoding="utf-8")
    return request_file, nonce


def _read(stdout: str, nonce: str) -> dict | None:
    """The harness's result: the JSON after the last marker on its stdout."""
    _head, found, tail = stdout.rpartition("\n" + nonce + "\n")
    if not found:
        return None
    try:
        return json.loads(tail)
    except ValueError:
        return None


async def simulate(project: Path, file: Path, scenario: dict, *, trace: bool = False, harden: bool = False,
                   php: str | None = None, ini: list[str] | None = None) -> Simulation:
    """Simulate one Function: refused (ScenarioError) before anything runs when the scenario is wrong."""
    if problems := check_scenario(scenario):
        raise ScenarioError("; ".join(problems))
    php = php or shutil.which("php")
    if not php:
        raise ScenarioError("php not found in PATH")
    work = Path(tempfile.mkdtemp(prefix="divide-funcsim-"))
    try:
        request_file, nonce = _request(project, file, scenario, work)
        extra = [*(ini or []), "-d", "memory_limit=256M", "-d", "display_errors=stderr", "-d", "html_errors=0",
                 "-d", "log_errors=0", *(tripwire(project, work) if harden else [])]
        started = time.monotonic()
        if trace:
            sim = await trace_lines(project, file.resolve(), request_file, scenario, php, extra)
        else:
            sim = await _plain(project, request_file, scenario, php, extra)
        sim.seconds = time.monotonic() - started
        result = _read(sim.stdout, nonce)
        if result is not None:
            if sim.status in ("", "crashed"):
                sim.status = result.get("status", "protocol")
            sim.result = result
        elif not sim.status:
            sim.status = "crashed"
        return sim
    finally:
        shutil.rmtree(work, ignore_errors=True)


async def _plain(project: Path, request_file: Path, scenario: dict, php: str, ini: list[str]) -> Simulation:
    proc = await asyncio.create_subprocess_exec(
        php, *ini, str(HARNESS), str(request_file), cwd=str(project),
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), limit(scenario, "seconds"))
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return Simulation("timeout")
    return Simulation("", stderr=err.decode("utf-8", "replace"), stdout=out.decode("utf-8", "replace"))


# ------------------------------------------------------------------ the line trace
def call_line() -> int:
    for number, line in enumerate(HARNESS.read_text(encoding="utf-8").split("\n"), 1):
        if "divide: the call" in line:
            return number
    raise RuntimeError("funcsim.php has no call line")


def _same(a: Path | None, b: Path) -> bool:
    if a is None:
        return False
    try:
        return a.resolve() == b
    except OSError:
        return False


async def _locals(session: DebugSession) -> dict:
    """The current frame's locals, as the harness encodes them (eval runs in that frame)."""
    reply = await session.command("eval", "-d", "0", data="__divide_funcsim_locals(get_defined_vars())")
    prop = reply.find("d:property", NS)
    if prop is None or reply.find("d:error", NS) is not None:
        return {"$error": "locals unavailable"}
    try:
        value = json.loads(_text(prop))
    except ValueError:
        return {"$error": "locals cut"}
    return value if isinstance(value, dict) else {}


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
    before, after = _flat(before), _flat(after)
    changes: dict = {}
    if set_ := {k: v for k, v in after.items() if k not in before or before[k] != v}:
        changes["set"] = set_
    if unset := sorted(k for k in before if k not in after):
        changes["unset"] = unset
    return changes


async def trace_lines(project: Path, target: Path, request_file: Path, scenario: dict, php: str,
                      ini: list[str]) -> Simulation:
    """Step through the Function's own lines with Xdebug, without a person at the debugger.

    One DBGp ``step_into`` per line; in the Function's file, the locals are read (``eval`` in that
    frame) and their changes recorded. Anything else (the harness's doubles, PHP code in other
    files) is left with ``step_out``: only the Function's lines are events. Xdebug stops *before*
    a line runs, so a line's locals are those its previous lines left."""
    session = DebugSession(HARNESS, [str(request_file)], cwd=project, php=php, ini=ini)
    events: list[dict] = []
    max_lines = limit(scenario, "lines")
    sim = Simulation("")

    async def run() -> None:
        await session.start()
        await session.command("feature_set", "-n", "max_data", "-v", str(LOCALS_BYTES))
        await session.set_breakpoint(HARNESS, call_line(), temporary=True)
        location = await session.resume("run")
        if location is None:  # ended before the call (stale, missing, an exception while loading)
            return
        frames: list[dict] = []  # the locals last seen, per depth inside the Function
        base: int | None = None
        how = "step_into"
        while True:
            location = await session.resume(how)
            if location is None:
                return
            if _same(location.file, target):
                stack = await session.stack()
                depth = len(stack)
                if base is None:
                    base = depth
                level = depth - base
                del frames[level + 1:]
                while len(frames) <= level:
                    frames.append({})
                now = await _locals(session)
                event = {"seq": len(events) + 1, "type": "line", "line": location.line, "depth": level,
                         "function": stack[0].where if stack else ""}
                changes = _diff(frames[level], now)
                frames[level] = now
                last = events[-1] if events else None
                same = last is not None and last["line"] == event["line"] and last["depth"] == level
                if same and how == "step_out":
                    if changes:  # back from a double: what it changed, on the same line
                        last.setdefault("after_call", {}).update(changes)
                elif same and not changes:
                    last["repeat"] = last.get("repeat", 0) + 1  # one line, several statements (echo a, b)
                else:
                    if changes:
                        event["locals"] = changes
                    events.append(event)
                if len(events) >= max_lines:
                    sim.status, sim.truncated = "line_limit", True
                    await session.stop()
                    return
                how = "step_into"
            elif base is not None and _same(location.file, HARNESS.resolve()) and len(await session.stack()) == 1:
                await session.resume("run")  # the Function returned or threw: let the harness write
                return
            else:
                how = "step_out"  # a double or other code: not the Function's lines

    try:
        await asyncio.wait_for(run(), limit(scenario, "seconds"))
    except TimeoutError:
        sim.status = "timeout"
    except DebugError as exc:
        sim.status, sim.stderr = "crashed", str(exc)
    finally:
        if session.running or session.state == "stopping":
            await session.stop()
    sim.events = events
    sim.stderr = sim.stderr or session.errors
    sim.stdout = session.output
    return sim


# ------------------------------------------------------------------ command line
def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    project, file, scenario_file = Path(args[0]), Path(args[1]), Path(args[2])
    scenario = json.loads(scenario_file.read_text(encoding="utf-8"))
    ini = []
    if xdebug := os.environ.get("DIVIDE_XDEBUG"):
        ini = ["-d", f"zend_extension={xdebug}"]
    try:
        sim = asyncio.run(simulate(project, project / file if not file.is_absolute() else file, scenario,
                                   trace="--trace" in argv, harden="--tripwire" in argv, ini=ini))
    except ScenarioError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(sim.document(project, project / file, scenario), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
