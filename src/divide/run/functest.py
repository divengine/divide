"""Test one Runner Function with a JSON context, in its own PHP process (UI-independent).

A Function test runs the project's **real PHP code**: the Function and whatever it calls may write
files, use a database or the network. A separate process with a time and a memory limit bounds how
long it runs and how much it prints; it is not a sandbox, and Xdebug is not one either.

``functest.php`` (beside this module) does the call, as Runner would: the project's Composer
autoload, the Function resolved by Runner's own importer (``runner::importer()``, with the function
root as ``_root_folder`` and the Module folders as ``_modules``: no second resolver here), then
``$func($context)`` with the context by reference. What the harness tells divide goes to a result
file, so the Function's own output (stdout, stderr, PHP's messages) is never mixed with it.

- :func:`request_for`: what a test of ``module:name`` sends, from :class:`flowmodel.Functions`.
- :func:`run_test`: the process, bounded (``timeout``, memory, output) and cancellable; a
  :class:`TestResult` with the return value, the context before and after, the changes, stdout,
  stderr, PHP's messages, an exception or fatal error with its file and line, and the exit status.
- :func:`check`: simple expectations, a return value and a subset of the context after.
- Scenarios: named inputs saved in the project only when asked (``.div/function-tests/``);
  the last input of each Function is remembered in the user's own settings, never in the project.
- :func:`debug_request`: the same call under divide's Xdebug session (``run.dbgp``).

A direct call is not a Flow Step: the Function's return value is shown as returned. In a Flow,
Runner keeps an activity's result under the Step's id, and a condition's false skips the Step.
"""

from __future__ import annotations

from divide.i18n import _

import asyncio
import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from divide.run import flowmodel as fm
from divide.run.flow import find_runner, vendor_dir
from divide.run.script import ScriptError, ScriptMessage, php_messages, run_script

HARNESS = Path(__file__).with_name("functest.php")
SCENARIOS = Path(".div") / "function-tests"
TIMEOUT = 30.0
MEMORY = "512M"
_SCENARIO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")


class TestError(Exception):
    """Why a test cannot start (nothing was run)."""


@dataclass(frozen=True)
class TestRequest:
    project: Path
    module: str | None
    name: str
    context: dict
    root: Path
    modules: dict[str, Path] = field(default_factory=dict)
    expected: Path | None = None  # the file divide's lookup finds (Runner's importer decides)
    autoload: Path | None = None
    runner: Path | None = None  # Runner's source, when the autoload does not load it

    @property
    def qualified(self) -> str:
        return f"{self.module}:{self.name}" if self.module else self.name

    def payload(self, result: Path) -> dict:
        return {"name": self.name, "module": self.module, "context": self.context, "root": str(self.root),
                "modules": {k: str(v) for k, v in self.modules.items()}, "result": str(result),
                "autoload": str(self.autoload) if self.autoload else "", "runner": str(self.runner) if self.runner else ""}


def parse_context(text: str) -> dict:
    """The context typed or saved: a JSON object (empty: {}); TestError says what is wrong."""
    text = text.strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise TestError(_('The context is not JSON: {why}').format(why=exc)) from exc
    if not isinstance(value, dict):
        raise TestError(_('The context must be a JSON object: {"key": "value"}'))
    return value


def request_for(project: Path, functions: fm.Functions, module: str | None, name: str, context: dict) -> TestRequest:
    """The test of ``module:name`` as a Step of a Flow with these ``functions`` would load it."""
    module = (module or "").strip() or None
    name = name.strip()
    if not name:
        raise TestError(_('No Function to test'))
    if module and (problem := fm.module_problem(module, name)):
        raise TestError(_('{module}:{name} is not a Runner reference ({what})').format(module=module, name=name, what=problem))
    runner = find_runner(project)
    if not runner.usable or runner.bootstrap is None:
        raise TestError(runner.problem or _('Runner is not installed: composer require divengine/runner'))
    autoload = vendor_dir(project) / "autoload.php"
    found = functions.find(name, module, project)
    if found is None and module:
        tried = fm._shown(functions.candidates(name, module, project)[0], project)
        raise TestError(_('{module}:{name}: no file {tried}').format(module=module, name=name, tried=tried))
    return TestRequest(project, module, name, context, functions.root, dict(functions.modules), found,
                       autoload if autoload.is_file() else None, fm.runner_source(runner.bootstrap))


# ---------------------------------------------------------------- the result
@dataclass
class Change:
    path: str  # key.sub[0]
    kind: str  # added | changed | removed
    before: object = None
    after: object = None


@dataclass
class TestResult:
    request: TestRequest
    status: str  # returned | exception | fatal | exit | missing | setup | timeout | stopped | crashed | protocol
    exit_code: int | None = None
    seconds: float = 0.0
    returned: object = None
    return_type: str | None = None
    before: object = None
    after: object = None
    stdout: str = ""
    stderr: str = ""
    messages: list[ScriptMessage] = field(default_factory=list)
    exception: dict | None = None
    error: dict | None = None  # a fatal error: message, file, line
    message: str = ""  # missing, setup, protocol
    resolved: dict | None = None  # the callable Runner's importer gave: file, line, by_reference
    logs: list[dict] = field(default_factory=list)  # Runner's logger
    memory_peak: int | None = None
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "returned"

    @property
    def changes(self) -> list[Change]:
        if not isinstance(self.before, dict) or not isinstance(self.after, dict):
            return []
        return diff(self.before, self.after)

    def location(self) -> tuple[Path, int] | None:
        """Where it failed: the exception's or the fatal error's file and line."""
        where = self.exception or self.error
        if where and where.get("file") and where.get("line"):
            return Path(where["file"]), int(where["line"])
        return None


def diff(before: object, after: object, path: str = "") -> list[Change]:
    if isinstance(before, dict) and isinstance(after, dict):
        out: list[Change] = []
        for key in before:
            sub = f"{path}.{key}" if path else str(key)
            if key not in after:
                out.append(Change(sub, "removed", before[key], None))
            else:
                out.extend(diff(before[key], after[key], sub))
        for key in after:
            if key not in before:
                out.append(Change(f"{path}.{key}" if path else str(key), "added", None, after[key]))
        return out
    if before != after or type(before) is not type(after):
        return [Change(path or "(context)", "changed", before, after)]
    return []


async def run_test(request: TestRequest, *, timeout: float = TIMEOUT, php: str | None = None,
                   on_data=None) -> TestResult:
    """Call the Function in a PHP process of its own, in the project's folder; cancelling stops PHP."""
    if not shutil.which(php or "php"):
        raise TestError(_('php was not found in the PATH.'))
    work = Path(tempfile.mkdtemp(prefix="divide-functest-"))
    try:
        result_file = work / "result.json"
        request_file = work / "request.json"
        request_file.write_text(json.dumps(request.payload(result_file)), encoding="utf-8")
        job = asyncio.ensure_future(run_script(HARNESS, [str(request_file)], cwd=request.project, php=php,
                                               ini=limits(), on_data=on_data))
        status = None
        try:
            script = await asyncio.wait_for(asyncio.shield(job), timeout)
        except asyncio.TimeoutError:
            job.cancel()
            script = await job
            status = "timeout"
        except asyncio.CancelledError:
            job.cancel()
            await asyncio.shield(job)
            raise
        if script.stopped and status is None:
            status = "stopped"
        return read_result(request, result_file, script, status)
    except ScriptError as exc:
        raise TestError(str(exc)) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


def limits() -> list[str]:
    return ["-d", f"memory_limit={MEMORY}", "-d", "max_execution_time=0"]


def read_result(request: TestRequest, result_file: Path, script, status: str | None = None) -> TestResult:
    """The harness's result file and the process's own streams, as one result."""
    out = TestResult(request, status or "crashed", script.exit_code, script.seconds, stdout=script.output, stderr=script.errors,
                     messages=php_messages(script.errors))
    out.truncated = len(script.output.encode()) >= 4 * 1024 * 1024 or len(script.errors.encode()) >= 4 * 1024 * 1024
    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if isinstance(data, dict):
        if status is None:
            out.status = str(data.get("status") or "protocol")
        out.returned = data.get("return")
        out.return_type = data.get("return_type")
        out.before, out.after = data.get("before"), data.get("after")
        out.exception, out.error = data.get("exception"), data.get("error")
        out.message = str(data.get("message") or "")
        out.resolved = data.get("resolved") if isinstance(data.get("resolved"), dict) else None
        out.logs = [x for x in data.get("logs") or [] if isinstance(x, dict)]
        out.memory_peak = data.get("memory_peak")
    if out.before is None:
        out.before = request.context
    return out


# ---------------------------------------------------------------- expectations
@dataclass(frozen=True)
class Expectation:
    returned: object = None
    has_return: bool = False  # an expected return was given (null is a value)
    context: dict | None = None  # a subset of the context after


def parse_expectation(returned: str, context: str) -> Expectation:
    has = bool(returned.strip())
    value = None
    if has:
        try:
            value = json.loads(returned)
        except ValueError as exc:
            raise TestError(_('The expected return is not JSON: {why}').format(why=exc)) from exc
    subset = None
    if context.strip():
        try:
            subset = json.loads(context)
        except ValueError as exc:
            raise TestError(_('The expected context is not JSON: {why}').format(why=exc)) from exc
        if not isinstance(subset, dict):
            raise TestError(_('The expected context must be a JSON object, the keys to find in the context after'))
    return Expectation(value, has, subset)


def contains(whole: object, part: object) -> bool:
    if isinstance(part, dict):
        return isinstance(whole, dict) and all(k in whole and contains(whole[k], v) for k, v in part.items())
    if isinstance(part, list):
        return isinstance(whole, list) and len(whole) == len(part) and all(contains(w, p) for w, p in zip(whole, part))
    return whole == part and type(whole) is type(part) or (isinstance(whole, (int, float)) and isinstance(part, (int, float))
                                                          and not isinstance(whole, bool) and not isinstance(part, bool) and whole == part)


def check(result: TestResult, expect: Expectation) -> list[tuple[bool, str]]:
    """Each expectation and whether it holds."""
    out = []
    if expect.has_return:
        ok = result.ok and contains(result.returned, expect.returned) and contains(expect.returned, result.returned)
        out.append((ok, _('returns {value}').format(value=json.dumps(expect.returned, ensure_ascii=False))))
    if expect.context is not None:
        out.append((result.after is not None and contains(result.after, expect.context),
                    _('the context after has {value}').format(value=json.dumps(expect.context, ensure_ascii=False))))
    return out


# ---------------------------------------------------------------- scenarios and the last input
@dataclass
class Scenario:
    context: str = ""  # the JSON text as typed
    returned: str = ""
    expected: str = ""


def scenario_problem(name: str) -> str | None:
    if not _SCENARIO.match(name.strip()):
        return _('A scenario name is letters, digits, spaces, _ . and -')
    return None


def scenario_file(project: Path, module: str | None, name: str) -> Path:
    return project / SCENARIOS / (module or "_root") / f"{name}.json"


def load_scenarios(project: Path, module: str | None, name: str) -> dict[str, Scenario]:
    path = scenario_file(project, module, name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for key, value in (data.get("scenarios") or {}).items() if isinstance(data, dict) else ():
        if isinstance(value, dict):
            out[str(key)] = Scenario(json.dumps(value.get("context", {}), ensure_ascii=False),
                                     json.dumps(value["return"], ensure_ascii=False) if "return" in value else "",
                                     json.dumps(value["context_after"], ensure_ascii=False) if "context_after" in value else "")
    return out


def save_scenario(project: Path, module: str | None, name: str, scenario_name: str, scenario: Scenario) -> Path:
    """The scenario written into the project (a fixture, for the team); the file's others kept."""
    if problem := scenario_problem(scenario_name):
        raise TestError(problem)
    context = parse_context(scenario.context)
    expect = parse_expectation(scenario.returned, scenario.expected)
    path = scenario_file(project, module, name)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError as exc:
        raise TestError(_('{path} is not JSON: {why}').format(path=path.name, why=exc)) from exc
    if not isinstance(data, dict):
        raise TestError(_('{path} is not a scenarios file').format(path=path.name))
    data.setdefault("function", f"{module}:{name}" if module else name)
    entry: dict = {"context": context}
    if expect.has_return:
        entry["return"] = expect.returned
    if expect.context is not None:
        entry["context_after"] = expect.context
    scenarios = data.get("scenarios") if isinstance(data.get("scenarios"), dict) else {}
    scenarios[scenario_name.strip()] = entry
    data["scenarios"] = scenarios
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


# ---------------------------------------------------------------- the report
def _json(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def summary(result: TestResult) -> str:
    words = {"returned": _('returned'), "exception": _('exception'), "fatal": _('fatal error'), "exit": _('exit() called'),
             "missing": _('not found'), "setup": _('not run'), "timeout": _('timed out'), "stopped": _('stopped'),
             "crashed": _('PHP ended'), "protocol": _('no result')}
    return f"{result.request.qualified} · {words.get(result.status, result.status)} · {result.seconds:.2f}s"


def report(result: TestResult, checks: list[tuple[bool, str]] | None = None, *, role: str | None = None) -> str:
    """The Output window's text: what the call gave, each part apart."""
    req = result.request
    lines = [_('Function test: {name}').format(name=req.qualified),
             _('Real PHP code ran: it may have written files, used a database or the network. Not a sandbox.'), ""]
    where = result.resolved.get("file") if result.resolved else None
    lines.append(_('File: {path}').format(path=where or (str(req.expected) if req.expected else _('(not resolved)'))))
    lines.append(_('Result: {state}').format(state=summary(result).split(" · ", 1)[1]))
    if result.exit_code is not None:
        lines.append(_('Exit code: {code}').format(code=result.exit_code))
    if result.message:
        lines.append(result.message)
    for log in result.logs:
        lines.append(f"Runner {log.get('level', '')}: {log.get('message', '')}")
    if result.status == "timeout":
        lines.append(_('Stopped after the time limit: PHP was ended.'))
    if result.resolved and result.resolved.get("parameters") and not result.resolved.get("by_reference"):
        lines.append(_('The callable takes the context by value: what it changes there is not kept.'))
    if checks:
        lines += ["", _('Expectations')]
        lines += [("  ok    " if ok else "  FAIL  ") + text for ok, text in checks]
    if result.status == "returned":
        lines += ["", _('Returned ({type}):').format(type=result.return_type or "?"), _json(result.returned)]
        if role == "condition":
            lines.append(_('As a condition: {verdict}.').format(
                verdict=_('true, the Step would run its activity, call or jump') if result.returned
                else _('false, the Step would skip the rest')))
        lines.append(_('A direct call: in a Flow, Runner keeps an activity\'s result in $context[<the Step\'s id>]; '
                       'here no Step ran, so it is only returned.'))
    if result.exception:
        exc = result.exception
        lines += ["", _('Exception {cls}: {message}').format(cls=exc.get("class"), message=exc.get("message")),
                  f"  {exc.get('file')}:{exc.get('line')}"]
        lines += [f"  #{i} {f.get('file') or '?'}:{f.get('line') or '?'} {f.get('function') or ''}"
                  for i, f in enumerate(exc.get("trace") or [])][:20]
    if result.error:
        lines += ["", _('Fatal error: {message}').format(message=result.error.get("message")),
                  f"  {result.error.get('file')}:{result.error.get('line')}"]
    changes = result.changes
    if result.after is not None:
        lines += ["", _('Context changes (by reference)') if changes else _('Context: unchanged')]
        for c in changes[:200]:
            if c.kind == "added":
                lines.append(f"  + {c.path} = {json.dumps(c.after, ensure_ascii=False)[:300]}")
            elif c.kind == "removed":
                lines.append(f"  - {c.path} (was {json.dumps(c.before, ensure_ascii=False)[:300]})")
            else:
                lines.append(f"  ~ {c.path}: {json.dumps(c.before, ensure_ascii=False)[:150]} -> {json.dumps(c.after, ensure_ascii=False)[:150]}")
        lines += ["", _('Context before:'), _json(result.before), "", _('Context after:'), _json(result.after)]
    lines += ["", "── stdout ──", result.stdout.rstrip("\n") or _('(nothing)'),
              "", "── stderr ──", result.stderr.rstrip("\n") or _('(nothing)')]
    if result.truncated:
        lines.append(_('(output cut at 4 MB)'))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- debugging
def debug_request(request: TestRequest) -> tuple[Path, Path, list[str]]:
    """The work folder, the result file and the arguments of ``functest.php`` for a debug session
    (``run.dbgp.DebugSession(HARNESS, args, cwd=project)``); the caller removes the folder."""
    work = Path(tempfile.mkdtemp(prefix="divide-functest-"))
    result_file = work / "result.json"
    request_file = work / "request.json"
    request_file.write_text(json.dumps(request.payload(result_file)), encoding="utf-8")
    return work, result_file, [str(request_file)]


def call_line() -> int:
    """The harness's line that calls the Function: a debug session stops there and steps into it."""
    for number, line in enumerate(HARNESS.read_text(encoding="utf-8").split("\n"), 1):
        if "divide: the call" in line:
            return number
    raise RuntimeError("functest.php has no call line")

