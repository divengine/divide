"""Function Mock Simulation: one Runner Function run with declared dependency doubles (UI-independent).

**MOCK SIMULATION: real PHP runs.** The Function's own PHP code runs, in a PHP process of its own.
Only what it asks its context for is replaced: other Functions (``$context['_importer']``), Runner's
logger (``$context['_logger']``, recorded) and service objects under context keys
(``doubles.services``). PHP's own functions (files, PDO, curl, ``mail``, ``time()``), the Function
file's top-level code and, when the scenario opts in, the project's Composer classes run for real.
This is not a sandbox and never side-effect-free; it is not the Flow simulation of
:mod:`divide.run.simulate` either, where Runner simulates the Flow and no Function code runs.
Design: ``docs/function-simulation.md``.

- :func:`check_scenario`: a ``divide.function-simulation`` v1 scenario, refused before anything
  runs (:class:`ScenarioError`) when it is not one this version runs.
- :func:`request_for`: the Function's file, found as Test Function finds it (the Flow's function
  root, ``.div/runner.json``, Module folders: :class:`divide.run.flowmodel.Functions`).
- :func:`simulate`: the process (``funcsim.php`` beside this module), tracked by
  :mod:`divide.run.children`, bounded (wall clock, ``memory_limit``, the Function's output) and
  cancellable; an optional *tripwire* (:func:`tripwire_ini`), labelled as such, not a sandbox.
- :func:`check`: the scenario's ``expect``, checked as Test Function checks its expectations.
- Trust: a per-project opt-in in the user's own settings (never in the project), required before
  the first simulation (:func:`trusted`, :func:`trust`, :func:`distrust`).
- Scenarios: ``.div/function-simulations/<module>/<name>.<scenario>.json`` in the project,
  versioned and shareable (the folder is not ignored).

The line trace (``divide.function-trace``) is a separate deliverable and not here.
"""

from __future__ import annotations

from divide.i18n import _

import asyncio
import hashlib
import json
import os
import re
import secrets
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from divide import config
from divide.run import flowfunctions as ff
from divide.run import flowmodel as fm
from divide.run import functest as ft
from divide.run.flow import vendor_dir
from divide.run.script import ScriptError, ScriptMessage, php_messages, run_script

HARNESS = Path(__file__).with_name("funcsim.php")
PROTOCOL = "divide.function-simulation"
VERSION = 1
OUTCOMES = ("returns", "throws", "sequence")
KEYS = {"protocol", "version", "description", "function", "context", "doubles", "unknown", "autoload", "expect", "limits"}
# name: (default, maximum). lines bounds the line trace; seconds kills the process; stdout bounds the Function's output.
LIMITS = {"lines": (2000, 100_000), "seconds": (20, 300), "stdout": (65_536, 4 * 1024 * 1024)}
MEMORY = "512M"  # memory_limit, as Test Function's
RESULT_BYTES = 32 * 1024 * 1024  # what is read of the process's stdout (the result is after the Function's output)
SCENARIOS = Path(".div") / "function-simulations"
TRUST_KEY = "function_simulation_trust"
_SCENARIO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,63}$")  # no dot: it separates the Function from the scenario
# The tripwire: process, network and mail functions, and the commonest file writes, disabled. A deny-list.
TRIPWIRE = (
    "exec,shell_exec,system,passthru,proc_open,popen,pcntl_exec,pcntl_fork,"
    "mail,fsockopen,pfsockopen,stream_socket_client,stream_socket_server,socket_create,socket_connect,"
    "curl_init,curl_exec,curl_multi_exec,"
    "file_put_contents,fwrite,fputs,unlink,rename,copy,mkdir,rmdir,touch,chmod,chown,symlink,link,tempnam,tmpfile,"
    "putenv,ini_set,set_include_path,dl"
)

# The words every consumer shows: a Mock Simulation is never presented as safe.
LABEL = _('MOCK SIMULATION: real PHP runs; only declared dependencies are replaced')
TRIPWIRE_LABEL = _('Tripwire, not a sandbox: some direct side effects fail, others (fopen, PDO, '
                   'static state) still happen')
TRUST_TEXT = _('A Mock Simulation runs this project\'s PHP code for real: the Function, its file\'s top-level code '
               'and, with autoload, the project\'s classes. Only the declared dependencies are replaced. It is not '
               'a sandbox and not side-effect-free. Allow Mock Simulations in this project?')
STATUSES = ("returned", "exception", "fatal", "exit", "stale", "missing", "timeout", "stopped", "crashed", "protocol")


class SimulationError(Exception):
    """Why a simulation cannot start (no process was started)."""


class ScenarioError(SimulationError):
    """The scenario is not one this version runs."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


class NotTrusted(SimulationError):
    """The project has not been opted in to Mock Simulation (:func:`trust`)."""


# ---------------------------------------------------------------- the scenario
def _outcome_problems(where: str, outcome: object, *, in_sequence: bool = False) -> list[str]:
    """Runner's ``--simulate`` outcome grammar: exactly one of returns, throws, sequence; a context merged."""
    if not isinstance(outcome, dict):
        return [_('{where}: an outcome is a JSON object').format(where=where)]
    kinds = [k for k in OUTCOMES if k in outcome]
    problems = []
    if in_sequence and "sequence" in kinds:
        problems.append(_('{where}: a sequence cannot hold a sequence').format(where=where))
    if len(kinds) != 1:
        problems.append(_('{where}: exactly one of returns, throws, sequence ({found})').format(
            where=where, found=", ".join(kinds) or _('none')))
    if unknown := set(outcome) - {*OUTCOMES, "context"}:
        problems.append(_('{where}: unknown {keys}').format(where=where, keys=", ".join(sorted(map(str, unknown)))))
    ctx = outcome.get("context")
    if ctx is not None and (not isinstance(ctx, dict) or any(str(k).startswith("_") for k in ctx)):
        problems.append(_('{where}: context is a JSON object without \'_\' keys').format(where=where))
    if "throws" in outcome and not isinstance(outcome["throws"], str):
        problems.append(_('{where}: throws is a message').format(where=where))
    if "sequence" in outcome:
        seq = outcome["sequence"]
        if not isinstance(seq, list) or not seq:
            problems.append(_('{where}: sequence is a non-empty list').format(where=where))
        else:
            for i, item in enumerate(seq):
                problems += _outcome_problems(f"{where}.sequence[{i}]", item, in_sequence=True)
    return problems


def check_scenario(data: object) -> list[str]:
    """What is wrong with a scenario; empty when this version can run it."""
    if not isinstance(data, dict):
        return [_('A scenario is a JSON object')]
    problems = []
    if data.get("protocol") != PROTOCOL or data.get("version") != VERSION:
        problems.append(_('Not {protocol} version {version}').format(protocol=PROTOCOL, version=VERSION))
    if unknown := set(data) - KEYS:
        problems.append(_('Unknown keys: {keys}').format(keys=", ".join(sorted(map(str, unknown)))))
    if not isinstance(data.get("description", ""), str):
        problems.append(_('description is text'))
    func = data.get("function")
    if not isinstance(func, dict) or not isinstance(func.get("name"), str) or not func["name"].strip():
        problems.append(_('function.name is missing'))
    else:
        module = func.get("module")
        if module is not None and not isinstance(module, str):
            problems.append(_('function.module is a Module name or null'))
        elif module and (problem := fm.module_problem(module, func["name"].strip())):
            problems.append(_('function: {module}:{name} is not a Runner reference ({why})').format(
                module=module, name=func["name"], why=problem))
        sha = func.get("sha256")
        if sha is not None and not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha)):
            problems.append(_('function.sha256 is a sha256 hex digest'))
    context = data.get("context", {})
    if not isinstance(context, dict):
        problems.append(_('context is a JSON object'))
    elif any(str(k).startswith("_") for k in context):
        problems.append(_('context keys starting with \'_\' belong to Runner'))
    if data.get("unknown", "fail") != "fail":
        problems.append(_('unknown: only "fail" (a missing double never calls the real dependency)'))
    doubles = data.get("doubles", {})
    if not isinstance(doubles, dict) or set(doubles) - {"importer", "services"}:
        problems.append(_('doubles has importer and services only'))
        doubles = {}
    importer = doubles.get("importer") or {}
    if not isinstance(importer, dict):
        problems.append(_('doubles.importer is a JSON object'))
        importer = {}
    for key, outcome in importer.items():
        problems += _outcome_problems(f"doubles.importer.{key}", outcome)
    services = doubles.get("services") or {}
    if not isinstance(services, dict):
        problems.append(_('doubles.services is a JSON object'))
        services = {}
    for service, methods in services.items():
        if str(service).startswith("_"):
            problems.append(_('doubles.services.{service}: \'_\' keys belong to Runner').format(service=service))
        if isinstance(context, dict) and service in context:
            problems.append(_('doubles.services.{service}: also in the context').format(service=service))
        if not isinstance(methods, dict) or not methods:
            problems.append(_('doubles.services.{service}: an object of methods').format(service=service))
            continue
        for method, outcome in methods.items():
            problems += _outcome_problems(f"doubles.services.{service}.{method}", outcome)
    limits = data.get("limits", {})
    if not isinstance(limits, dict) or set(limits) - set(LIMITS):
        problems.append(_('limits has {keys} only').format(keys=", ".join(LIMITS)))
    else:
        for key, value in limits.items():
            top = LIMITS[key][1]
            if not isinstance(value, int) or isinstance(value, bool) or not 0 < value <= top:
                problems.append(_('limits.{key}: 1..{top}').format(key=key, top=top))
    if not isinstance(data.get("autoload", False), bool):
        problems.append(_('autoload is true or false'))
    expect = data.get("expect", {})
    if not isinstance(expect, dict) or set(expect) - {"returns", "context"}:
        problems.append(_('expect has returns and context only'))
    elif "context" in expect and not isinstance(expect["context"], dict):
        problems.append(_('expect.context is a JSON object, the keys to find in the context after'))
    return problems


def limit(scenario: dict, key: str) -> int:
    return int((scenario.get("limits") or {}).get(key, LIMITS[key][0]))


def expectation(scenario: dict) -> ft.Expectation:
    """The scenario's ``expect`` as Test Function's :class:`~divide.run.functest.Expectation`."""
    expect = scenario.get("expect") or {}
    return ft.Expectation(expect.get("returns"), "returns" in expect, expect.get("context"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def new_scenario(module: str | None, name: str, file: Path | None = None, *, context: dict | None = None,
                 description: str = "") -> dict:
    """A scenario with no doubles yet, pinned to the file's current sha256 when it is given."""
    func: dict = {"module": module or None, "name": name}
    if file is not None and file.is_file():
        func["sha256"] = sha256(file)
    return {"protocol": PROTOCOL, "version": VERSION, "description": description, "function": func,
            "context": context or {}, "doubles": {"importer": {}, "services": {}}, "unknown": "fail",
            "autoload": False, "expect": {}, "limits": {k: v[0] for k, v in LIMITS.items()}}


# ---------------------------------------------------------------- trust
def _trust_key(project: Path) -> str:
    return str(Path(project).resolve())


def trusted(project: Path) -> bool:
    saved = config.load().get(TRUST_KEY)
    return isinstance(saved, dict) and _trust_key(project) in saved


def trust(project: Path) -> None:
    """The user's opt-in for this project, in their own settings (never in the project)."""
    settings = config.load()
    saved = settings.get(TRUST_KEY) if isinstance(settings.get(TRUST_KEY), dict) else {}
    saved[_trust_key(project)] = {"since": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    settings[TRUST_KEY] = saved
    config.save(settings)


def distrust(project: Path) -> None:
    settings = config.load()
    saved = settings.get(TRUST_KEY)
    if isinstance(saved, dict) and saved.pop(_trust_key(project), None) is not None:
        config.save(settings)


# ---------------------------------------------------------------- the request
@dataclass(frozen=True)
class SimRequest:
    project: Path
    scenario: dict
    file: Path | None  # the Function's file, found as Runner's importer would; None: no such file
    autoload: Path | None = None  # the project's Composer autoload (loaded only if the scenario opts in)

    @property
    def module(self) -> str | None:
        return self.scenario["function"].get("module") or None

    @property
    def name(self) -> str:
        return self.scenario["function"]["name"].strip()

    @property
    def qualified(self) -> str:
        return f"{self.module}:{self.name}" if self.module else self.name


def functions(project: Path) -> fm.Functions:
    """The project's function root and Modules (``.div/runner.json``), when no Flow gives them."""
    return fm.functions_for(project, "", {}, ff.load_settings(project))


def request_for(project: Path, scenario: dict, functions_: fm.Functions | None = None) -> SimRequest:
    """The simulation of the scenario's Function, found where a Step of a Flow with these
    ``functions`` would find it (Test Function's lookup); refused if the scenario is wrong."""
    if problems := check_scenario(scenario):
        raise ScenarioError(problems)
    project = Path(project).resolve()
    functions_ = functions_ or functions(project)
    func = scenario["function"]
    module = (func.get("module") or "").strip() or None
    found = functions_.find(func["name"].strip(), module, project)
    autoload = vendor_dir(project) / "autoload.php"
    return SimRequest(project, scenario, found.resolve() if found else None, autoload if autoload.is_file() else None)


# ---------------------------------------------------------------- the result
@dataclass
class Simulation:
    request: SimRequest
    status: str  # STATUSES
    tripwire: bool = False
    exit_code: int | None = None
    seconds: float = 0.0
    returned: object = None
    return_type: str | None = None
    before: object = None
    after: object = None
    calls: list[dict] = field(default_factory=list)  # each double's answer, in order
    logs: list[dict] = field(default_factory=list)  # $context['_logger']
    output: str = ""  # what the Function printed (bounded by limits.stdout)
    output_cut: int = 0  # bytes of it not kept
    exception: dict | None = None  # class, message, file, line, missing_double
    error: dict | None = None  # a fatal error: message, file, line
    message: str = ""
    sha256: str | None = None
    phase: str = ""  # bootstrap, load, call, done: where the harness was
    stderr: str = ""
    messages: list[ScriptMessage] = field(default_factory=list)
    leaked: str = ""  # what reached the process's stdout around the output buffer (fwrite(STDOUT))
    memory_peak: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == "returned"

    @property
    def missing_double(self) -> bool:
        return bool(self.exception and self.exception.get("missing_double"))

    @property
    def changes(self) -> list[ft.Change]:
        if not isinstance(self.before, dict) or not isinstance(self.after, dict):
            return []
        return ft.diff(self.before, self.after)

    def result(self) -> dict:
        """The ``result`` object of a ``divide.function-trace`` v1 document (docs/function-simulation.md §7)."""
        out = {"status": self.status, "return": self.returned, "return_type": self.return_type,
               "before": self.before, "after": self.after, "calls": self.calls, "logs": self.logs,
               "stdout": self.output, "stdout_cut": self.output_cut, "tripwire": self.tripwire,
               "seconds": round(self.seconds, 3)}
        for key, value in (("exception", self.exception), ("error", self.error), ("message", self.message or None),
                           ("memory_peak", self.memory_peak)):
            if value is not None:
                out[key] = value
        return out


def check(sim: Simulation) -> list[tuple[bool, str]]:
    """The scenario's expectations and whether each holds, as Test Function checks its own."""
    return ft.check(sim, expectation(sim.request.scenario))  # type: ignore[arg-type]


# ---------------------------------------------------------------- the process
def tripwire_ini(request: SimRequest, work: Path) -> list[str]:
    """INI for the tripwire: a deny-list and a filesystem fence (``open_basedir``). Not a sandbox."""
    fence = [request.project, HARNESS.parent.resolve(), work.resolve()]
    if request.file is not None:
        fence.append(request.file.parent)  # a Module folder mapped outside the project
    if request.autoload is not None and request.scenario.get("autoload"):
        fence.append(request.autoload.parent.parent.resolve())  # a vendor-dir outside the project
    paths = os.pathsep.join(dict.fromkeys(str(p) for p in fence))
    # Quoted: on Windows the separator is ';', which starts a comment in an unquoted ini value.
    return ["-d", f"disable_functions={TRIPWIRE}", "-d", f'open_basedir="{paths}"', "-d", "allow_url_fopen=0",
            "-d", "allow_url_include=0"]


def _ini(request: SimRequest, work: Path, tripwire: bool) -> list[str]:
    return ["-d", f"memory_limit={MEMORY}", "-d", "max_execution_time=0",
            *(tripwire_ini(request, work) if tripwire else [])]


def prepare(request: SimRequest, work: Path) -> tuple[Path, str]:
    """The harness's request file in ``work`` and the nonce its result follows on stdout."""
    nonce = "divide-funcsim-" + secrets.token_hex(16)
    request_file = work / "request.json"
    request_file.write_text(json.dumps({
        "scenario": request.scenario, "file": str(request.file) if request.file else "", "nonce": nonce,
        "autoload": str(request.autoload) if request.autoload else "",
    }), encoding="utf-8")
    return request_file, nonce


def read_result(stdout: str, nonce: str) -> tuple[dict | None, str]:
    """The harness's result (the JSON after the last marker) and what else reached stdout."""
    head, found, tail = stdout.rpartition("\n" + nonce + "\n")
    if not found:
        return None, stdout
    try:
        data = json.loads(tail)
    except ValueError:
        return None, head
    return (data if isinstance(data, dict) else None), head


def _fill(sim: Simulation, data: dict) -> None:
    if sim.status in ("", "crashed"):
        status = str(data.get("status") or "protocol")
        sim.status = status if status in STATUSES else "protocol"
    sim.returned, sim.return_type = data.get("return"), data.get("return_type")
    if "before" in data:
        sim.before = data["before"]
    sim.after = data.get("after")
    sim.calls = [c for c in data.get("calls") or [] if isinstance(c, dict)]
    sim.logs = [x for x in data.get("logs") or [] if isinstance(x, dict)]
    sim.output, sim.output_cut = str(data.get("stdout") or ""), int(data.get("stdout_cut") or 0)
    sim.exception = data.get("exception") if isinstance(data.get("exception"), dict) else None
    sim.error = data.get("error") if isinstance(data.get("error"), dict) else None
    sim.message = str(data.get("message") or "")
    sim.sha256 = data.get("sha256") if isinstance(data.get("sha256"), str) else None
    sim.phase = str(data.get("phase") or "")
    sim.memory_peak = data.get("memory_peak") if isinstance(data.get("memory_peak"), int) else None


async def simulate(request: SimRequest, *, tripwire: bool = False, php: str | None = None,
                   ini: list[str] | None = None, on_data=None) -> Simulation:
    """Run the request's Function with its doubles, in a PHP process of its own, in the project's folder.

    Refused (:class:`SimulationError`, no process started) when the scenario is wrong, the project is
    not trusted, or PHP is missing. ``limits.seconds`` kills the process (``timeout``); cancelling the
    task kills it too, then re-raises."""
    if problems := check_scenario(request.scenario):
        raise ScenarioError(problems)
    if not trusted(request.project):
        raise NotTrusted(_('Mock Simulation is not allowed in this project yet: it runs real PHP code'))
    if not shutil.which(php or "php"):
        raise SimulationError(_('php was not found in the PATH.'))
    sim = Simulation(request, "", tripwire, before=request.scenario.get("context") or {})
    if request.file is None:
        sim.status = "missing"
        sim.message = _('{name}: no such Function file').format(name=request.qualified)
        return sim
    # Resolved: on Windows the temp folder can be an 8.3 short path, which open_basedir would refuse.
    work = Path(tempfile.mkdtemp(prefix="divide-funcsim-")).resolve()
    started = time.monotonic()
    try:
        request_file, nonce = prepare(request, work)
        job = asyncio.ensure_future(run_script(HARNESS, [str(request_file)], cwd=request.project, php=php,
                                               ini=[*(ini or []), *_ini(request, work, tripwire)],
                                               on_data=on_data, limit=RESULT_BYTES))
        try:
            script = await asyncio.wait_for(asyncio.shield(job), limit(request.scenario, "seconds"))
        except asyncio.TimeoutError:
            job.cancel()
            script = await job
            sim.status = "timeout"
        except asyncio.CancelledError:
            job.cancel()
            await asyncio.shield(job)
            raise
        if script.stopped and not sim.status:
            sim.status = "stopped"
        sim.exit_code, sim.stderr = script.exit_code, script.errors
        sim.messages = php_messages(script.errors)
        data, sim.leaked = read_result(script.output, nonce)
        if data is not None:
            _fill(sim, data)
        elif not sim.status:
            sim.status = "crashed"
            if len(script.output.encode()) >= RESULT_BYTES:
                sim.status, sim.message = "protocol", _('The result was cut: over {size} bytes').format(size=RESULT_BYTES)
        return sim
    except ScriptError as exc:
        raise SimulationError(str(exc)) from exc
    finally:
        sim.seconds = time.monotonic() - started
        shutil.rmtree(work, ignore_errors=True)


def call_line() -> int:
    """The harness's line that calls the Function (where a line trace steps in)."""
    for number, line in enumerate(HARNESS.read_text(encoding="utf-8").split("\n"), 1):
        if "divide: the call" in line:
            return number
    raise RuntimeError("funcsim.php has no call line")


# ---------------------------------------------------------------- scenarios in the project
def scenario_problem(name: str) -> str | None:
    if not _SCENARIO.match(name.strip()):
        return _('A scenario name is letters, digits, spaces, _ and -')
    return None


def _folder(project: Path, module: str | None) -> Path:
    return Path(project) / SCENARIOS / (module or "_root")


def scenario_file(project: Path, module: str | None, name: str, scenario_name: str) -> Path:
    """``.div/function-simulations/<module or _root>/<name>.<scenario>.json``"""
    if problem := scenario_problem(scenario_name):
        raise SimulationError(problem)
    target = _folder(project, module) / f"{name.strip()}.{scenario_name.strip()}.json"
    if not ff.inside(target, Path(project) / SCENARIOS):
        raise SimulationError(_('{name}: not a Function name').format(name=name))
    return target


def list_scenarios(project: Path, module: str | None, name: str) -> dict[str, Path]:
    """The Function's saved scenarios, by name."""
    base = _folder(project, module) / name.strip()
    folder, stem = base.parent, base.name + "."
    if not folder.is_dir():
        return {}
    out = {}
    for path in sorted(folder.glob("*.json")):
        if path.name.startswith(stem) and not scenario_problem(scenario := path.name[len(stem):-len(".json")]):
            out[scenario] = path
    return out


def load_scenario(path: Path) -> dict:
    """A saved scenario; :class:`ScenarioError` if it is not one this version runs."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise SimulationError(str(exc)) from exc
    except ValueError as exc:
        raise ScenarioError([_('{path} is not JSON: {why}').format(path=Path(path).name, why=exc)]) from exc
    if problems := check_scenario(data):
        raise ScenarioError(problems)
    return data


def save_scenario(project: Path, scenario_name: str, scenario: dict) -> Path:
    """The scenario written into the project, for the team; refused if it is wrong."""
    if problems := check_scenario(scenario):
        raise ScenarioError(problems)
    func = scenario["function"]
    path = scenario_file(project, func.get("module") or None, func["name"], scenario_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(scenario, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path
