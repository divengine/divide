"""Runner Flows: run, pause and resume them through Runner's own command line (UI-independent).

divide does not run a Flow itself: it starts the official bootstrap of the
project's Composer installation,

    php vendor/divengine/runner/bin/run.php FLOW --json [--context C] [--root R] [--save-context S]

in the project's folder (relative paths in a context, ``_root_folder`` and
``_modules``, are Runner's to resolve from there), and reads what Runner
says: the exit code (0 done, 3 paused, 1 error, 2 invocation or context
persistence error), the resulting context on stdout (``--json``) and the
diagnostics and what the Flow printed on stderr. Runner parses the YAML,
runs the Blocks and Steps, follows ``call`` and ``jump``, pauses, and
writes the context (atomically) only when the run ends: a run stopped
before that leaves the saved context as it was.

Flows are trusted PHP code, not a sandbox.
"""

from __future__ import annotations

from divide.i18n import _

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from divide.run.script import ScriptMessage, ScriptResult, php_messages, run_script

PACKAGE = "divengine/runner"
BOOTSTRAP = Path("divengine") / "runner" / "bin" / "run.php"
MIN_VERSION = (0, 2, 0)
FLOW_SUFFIXES = (".yml", ".yaml")
STATES = ("done", "paused", "error")
_FLOW_ROOT = re.compile(r"^blocks[ \t]*:[ \t]*(#.*)?$", re.MULTILINE)
_VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?")
_ENDED = re.compile(r"^flow ended (done|paused|error), but the context")


def is_flow(path: Path | None, text: str) -> bool:
    """A Runner Flow, as far as divide needs to know to offer running it: a YAML file whose
    root has ``blocks``. (Whether it is a valid Flow is Runner's to say when it runs.)"""
    return path is not None and path.suffix.lower() in FLOW_SUFFIXES and bool(_FLOW_ROOT.search(text))


# ---------------------------------------------------------------- finding Runner
@dataclass(frozen=True)
class Runner:
    """Runner as the project installed it: its bootstrap and version, or why it cannot be used."""

    bootstrap: Path | None
    version: str | None = None
    problem: str | None = None

    @property
    def usable(self) -> bool:
        return self.bootstrap is not None and self.problem is None


def vendor_dir(root: Path) -> Path:
    """The project's Composer vendor folder (``config.vendor-dir`` of composer.json, else vendor)."""
    try:
        data = json.loads((root / "composer.json").read_text(encoding="utf-8"))
        configured = data.get("config", {}).get("vendor-dir") if isinstance(data, dict) else None
    except (OSError, UnicodeDecodeError, ValueError, AttributeError):
        configured = None
    return (root / configured) if isinstance(configured, str) and configured.strip() else root / "vendor"


def _installed_version(vendor: Path) -> str | None:
    try:
        data = json.loads((vendor / "composer" / "installed.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    packages = data.get("packages") if isinstance(data, dict) else data  # Composer 2, or 1's list
    for item in packages if isinstance(packages, list) else []:
        if isinstance(item, dict) and item.get("name") == PACKAGE:
            return str(item.get("version") or "") or None
    return None


def version_tuple(version: str) -> tuple[int, int, int] | None:
    """``v0.2.0`` / ``0.2.1`` / ``0.3.x-dev`` as numbers; None for a branch (``dev-main``)."""
    m = _VERSION.match(version.strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)) if m else None


def find_runner(root: Path) -> Runner:
    """Runner in the project's Composer installation, or a clear reason why not."""
    vendor = vendor_dir(root)
    bootstrap = vendor / BOOTSTRAP
    version = _installed_version(vendor)
    if not bootstrap.is_file():
        return Runner(None, version, _('Runner is not installed in this project: composer require divengine/runner '
                                       '(divide runs {bootstrap})').format(bootstrap=_shown(bootstrap, root)))
    numbers = version_tuple(version) if version else None
    if numbers is not None and numbers < MIN_VERSION:
        return Runner(bootstrap, version, _('Runner {version} is installed; divide needs 0.2.0 or newer, the first '
                                            'with its command line: composer require divengine/runner:^0.2').format(version=version))
    return Runner(bootstrap, version)


def _shown(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


# ---------------------------------------------------------------- saved contexts
CHECKPOINTS = Path(".div") / "runner"  # the contexts divide saves for the user's Flows, in the project
_IGNORE = "# divide's Runner checkpoints: generated contexts, not versioned\n*\n"


def default_checkpoint(flow: Path, project: Path) -> Path:
    """Where divide saves a Flow's context unless the user says otherwise: under ``.div/runner/``,
    one file per Flow (``flows/order.yml`` -> ``.div/runner/flows/order.yml.context.json``; a Flow
    outside the project gets a folder named after a hash of its own)."""
    try:
        rel = flow.relative_to(project)
    except ValueError:
        rel = Path("outside") / hashlib.sha1(str(flow.parent).encode("utf-8")).hexdigest()[:12] / flow.name
    return project / CHECKPOINTS / rel.parent / (rel.name + ".context.json")


def is_managed(path: Path, project: Path) -> bool:
    """``path`` is one of divide's checkpoints (under the project's ``.div/runner/``)."""
    try:
        path.resolve().relative_to((project / CHECKPOINTS).resolve())
    except ValueError:
        return False
    return True


def prepare_checkpoint(path: Path, project: Path) -> None:
    """The folder of a checkpoint divide manages, made if missing (Runner wants it), with a
    ``.gitignore`` that keeps the generated contexts out of Git."""
    if not is_managed(path, project):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    ignore = project / CHECKPOINTS / ".gitignore"
    if not ignore.exists():
        ignore.write_text(_IGNORE, encoding="utf-8")


@dataclass(frozen=True)
class Saved:
    """What a context file holds, for the IDE to say and to decide whether a resume is possible."""

    path: Path
    exists: bool
    state: str | None = None  # Runner's _runner_state: done, paused, error
    block: str | None = None  # where a paused run stopped
    step: str | None = None
    calls: int = 0  # pending call return frames (_flow_stack)
    problem: str | None = None  # not JSON, not an object...

    @property
    def resumable(self) -> bool:
        return self.exists and self.problem is None and self.state == "paused"


def read_saved(path: Path) -> Saved:
    if not path.exists():
        return Saved(path, False)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return Saved(path, True, problem=_('cannot be read: {error}').format(error=exc))
    except ValueError as exc:
        return Saved(path, True, problem=_('is not JSON: {error}').format(error=exc))
    if not isinstance(data, dict):
        return Saved(path, True, problem=_('is not a JSON object'))
    state = data.get("_runner_state") if isinstance(data.get("_runner_state"), str) else None
    stack = data.get("_flow_stack")
    flow_state = data.get("_flow_state")
    block = flow_state.get("block") if isinstance(flow_state, dict) else None
    if state == "paused" and not isinstance(flow_state, dict):
        return Saved(path, True, state, problem=_('says paused but has no _flow_state to resume from'))
    return Saved(path, True, state, str(block) if block is not None else data.get("_current_block_id"),
                 data.get("_current_step_id") if state == "paused" else None,
                 len(stack) if isinstance(stack, list) else 0)


def check_context_file(path: Path) -> str | None:
    """Why ``path`` cannot be an initial context (Runner takes a JSON object), or None."""
    if not path.is_file():
        return _('no such file: {path}').format(path=path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return _('{path} cannot be read: {error}').format(path=path.name, error=exc)
    except ValueError as exc:
        return _('{path} is not JSON: {error}').format(path=path.name, error=exc)
    return None if isinstance(data, dict) or data == [] else _('{path} is not a JSON object').format(path=path.name)


def check_context_text(text: str) -> str | None:
    """Why ``text`` (a context typed in divide) is not a JSON object, or None."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        return _('The context is not JSON: {error}').format(error=exc)
    return None if isinstance(data, dict) else _('The context must be a JSON object')


# ---------------------------------------------------------------- running
@dataclass
class FlowRun:
    """How a run of a Flow ended."""

    flow: Path
    state: str  # done, paused, error; invocation (exit 2, the Flow did not run); unsaved (exit 2 after the
    # Flow ran: its context could not be encoded or saved); crashed (PHP died: exit(), a fatal error); cancelled
    exit_code: int | None
    seconds: float
    resumed: bool = False
    context: dict | None = None  # the resulting context (--json)
    stdout: str = ""
    stderr: str = ""
    saved_to: Path | None = None  # the context file Runner wrote
    messages: list[ScriptMessage] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)  # Runner's "runner: ..." lines

    @property
    def logs(self) -> list[dict]:
        logs = (self.context or {}).get("_runner_logs")
        return [entry for entry in logs if isinstance(entry, dict)] if isinstance(logs, list) else []

    @property
    def result(self) -> str | None:
        value = (self.context or {}).get("_runner_result")
        return value if isinstance(value, str) else None


def flow_command(runner: Runner, flow: Path, *, context: Path | None = None, functions: Path | None = None,
                 save_to: Path | None = None) -> list[str]:
    """The bootstrap's arguments (after ``php run.php``)."""
    args = ["--json"]
    if context is not None:
        args += ["--context", str(context)]
    if functions is not None:
        args += ["--root", str(functions)]
    if save_to is not None:
        args += ["--save-context", str(save_to)]
    return [*args, "--", str(flow)]


async def run_flow(runner: Runner, flow: Path, *, cwd: Path, context: Path | None = None, context_text: str | None = None,
                   functions: Path | None = None, save_to: Path | None = None, resumed: bool = False,
                   php: str | None = None, on_data: Callable[[bytes, bytes], None] | None = None) -> FlowRun:
    """Run ``flow`` with Runner's bootstrap in ``cwd`` (the project). ``context_text`` is a context typed in
    divide (given to Runner as a temporary file); cancelling the task stops PHP: the run is ``cancelled``
    and the context file is left as it was. ScriptError when there is no PHP."""
    assert runner.bootstrap is not None
    temp_dir = None
    if context_text is not None:
        temp_dir = Path(tempfile.mkdtemp(prefix="divide-flow-"))
        context = temp_dir / "context.json"
        context.write_text(context_text, encoding="utf-8")
    started = time.time()
    try:
        result: ScriptResult = await run_script(runner.bootstrap, flow_command(runner, flow, context=context,
                                                functions=functions, save_to=save_to), cwd=cwd, php=php, on_data=on_data)
    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)
    run = FlowRun(flow, _state_of(result), result.exit_code, result.seconds, resumed, stdout=result.output,
                  stderr=result.errors, messages=php_messages(result.errors))
    run.diagnostics = [line[len("runner: "):] for line in result.errors.splitlines() if line.startswith("runner: ")]
    if run.state == "invocation" and any(_ENDED.match(d) for d in run.diagnostics):
        run.state = "unsaved"  # "flow ended paused, but the context was not saved: ..."
    if run.state in STATES:
        try:
            data = json.loads(result.output)
            run.context = data if isinstance(data, dict) else ({} if data == [] else None)
        except ValueError:
            run.context = None
        if save_to is not None and run.context is not None:
            run.saved_to = save_to
    if run.state == "cancelled" and save_to is not None:
        _remove_partial_saves(save_to, started)
    return run


def _state_of(result: ScriptResult) -> str:
    if result.stopped:
        return "cancelled"
    return {0: "done", 3: "paused", 1: "error", 2: "invocation"}.get(result.exit_code, "crashed")  # type: ignore[arg-type]


def _remove_partial_saves(target: Path, since: float) -> None:
    """A run stopped while Runner was writing the context may leave its temporary file
    (``.<name>.XXXX`` beside it, replaced into place only at the end): it goes; the context
    file itself was never touched."""
    try:
        for leftover in target.parent.glob(f".{target.name}.*"):
            if leftover.is_file() and leftover.stat().st_mtime >= since - 1:
                os.unlink(leftover)
    except OSError:
        pass
