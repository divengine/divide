"""Flow Simulation (divide.run.simulate): what needs a double, the doubles file, Runner's trace protocol,
the playback rebuilt from Runner's own fixtures, real simulations through Runner's command line in
separate processes, and the project's cache of sessions.

The subprocess tests need php and Runner 0.3 or newer in ``examples/runner``
(``composer install --working-dir examples/runner``); they skip without them.
"""

import asyncio
import copy
import json
import os
import shutil
from pathlib import Path

import pytest

from divide.run import flowmodel as fm
from divide.run import simulate as sim
from divide.run.flow import Runner, find_runner, run_flow

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).with_name("fixtures") / "runner-simulation"  # Runner 0.3.0's examples/simulation
EXAMPLE = ROOT / "examples" / "runner"
VENDOR = EXAMPLE / "vendor"


def runner_03() -> bool:
    if not shutil.which("php"):
        return False
    return sim.simulation_problem(find_runner(EXAMPLE)) is None


needs_runner = pytest.mark.skipif(not runner_03(), reason="needs php and Runner >= 0.3 in examples/runner (composer install)")


def project_with_vendor(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    try:
        (root / "vendor").symlink_to(VENDOR, target_is_directory=True)
    except OSError:  # Windows without the right to make links
        shutil.copytree(VENDOR, root / "vendor")
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root.resolve()


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixture_traces() -> list[sim.Trace]:
    return [sim.parse_trace(fixture("expected/segment-1.json")), sim.parse_trace(fixture("expected/segment-2.json"))]


def invoice_doc() -> fm.FlowDoc:
    return fm.parse((FIXTURES / "flows" / "invoice.yml").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- Runner's version
def fake_runner(tmp_path: Path, version: str, simulate: bool) -> Runner:
    bootstrap = tmp_path / "run.php"
    bootstrap.write_text("<?php // " + ("--simulate <file>" if simulate else "--save-context <file>"), encoding="utf-8")
    return Runner(bootstrap, version)


def test_runner_0_2_cannot_simulate_and_says_run_still_works(tmp_path):
    problem = sim.simulation_problem(fake_runner(tmp_path, "v0.2.0", simulate=False))
    assert problem is not None and "0.3.0" in problem and "Run (Ctrl+F9)" in problem and "Nothing was run" in problem
    assert sim.simulation_problem(fake_runner(tmp_path, "v0.3.0", simulate=True)) is None
    assert sim.simulation_problem(fake_runner(tmp_path, "0.4.1", simulate=True)) is None


def test_a_branch_of_runner_is_asked_its_command_line(tmp_path):
    assert sim.simulation_problem(fake_runner(tmp_path, "dev-main", simulate=True)) is None
    assert sim.simulation_problem(fake_runner(tmp_path, "dev-main", simulate=False)) is not None
    assert sim.simulation_problem(Runner(None, None, "Runner is not installed")) == "Runner is not installed"


# ---------------------------------------------------------------- what needs a double
FLOW = """id: demo
blocks:
  main:
    steps:
      a:
        module: billing
        activity: total
      b:
        condition: ready
        activity: send
      c:
        call: other.x
  other:
    steps:
      x:
        module: billing
        condition: ready
        activity: " spaced "
"""


def test_every_reference_is_keyed_as_runner_keys_doubles():
    reqs = {r.key: r for r in sim.requirements(fm.parse(FLOW))}
    assert set(reqs) == {"billing:total", "ready", "send", "billing:ready", "billing:spaced"}
    assert reqs["ready"].kinds == ["condition"] and reqs["ready"].places == ["main.b"]
    assert reqs["billing:ready"].places == ["other.x"]


def test_a_nested_flow_named_by_a_double_needs_its_own_doubles(tmp_path):
    (tmp_path / "child.yml").write_text("blocks:\n  main:\n    steps:\n      s:\n        activity: inner\n", encoding="utf-8")
    reqs = sim.requirements(fm.parse(FLOW), project=tmp_path, doubles={"send": {"flow": "child.yml"}})
    inner = next(r for r in reqs if r.key == "inner")
    assert inner.flow == "child.yml" and inner.places == ["child.yml:main.s"]


def test_an_incomplete_or_malformed_doubles_file_is_refused_before_anything_runs(tmp_path):
    reqs = sim.requirements(fm.parse(FLOW))
    check = sim.check_spec({"doubles": {"billing:total": {"returns": 1}}}, reqs, tmp_path)
    assert not check.ok and {r.key for r in check.missing} == {"ready", "send", "billing:ready", "billing:spaced"}
    assert any("No double for ready (condition, used by main.b)" in m for m in check.messages())
    bad = {
        "doubles": {
            "ready": {"pause": True},  # a condition cannot pause
            "send": {"returns": 1, "throws": "x"},  # two kinds
            "billing:total": {"returns": 1, "context": {"_flow_state": 1}},  # Runner's keys
            "billing:ready": {"sequence": []},
            "billing:spaced": {"flow": "nowhere.yml"},
            "bad module:x": {"returns": 1},
        },
        "budget": {"steps": 0, "minutes": 3},
        "extra": 1,
    }
    problems = "\n".join(sim.check_spec(bad, reqs, tmp_path).problems)
    for words in ("a condition cannot pause", "exactly one of returns, throws, pause, sequence, flow", "_flow_state",
                  "non-empty list", "no nested Flow nowhere.yml", "is not a Module name", "steps must be a positive",
                  "Unknown budget minutes", "Unknown key(s) in the doubles file: extra"):
        assert words in problems, words
    assert not sim.check_spec([1, 2], reqs, tmp_path).ok


def test_the_template_is_complete_and_valid(tmp_path):
    reqs = sim.requirements(fm.parse(FLOW))
    data = sim.template(reqs, "start")
    check = sim.check_spec(data, reqs, tmp_path)
    assert check.ok and data["doubles"]["ready"] == {"returns": True} and data["doubles"]["send"] == {"returns": None}


# ---------------------------------------------------------------- the trace protocol
def test_another_protocol_or_version_is_refused_with_a_reason():
    data = fixture("expected/segment-1.json")
    with pytest.raises(sim.SimulationError, match="Not a Runner trace"):
        sim.parse_trace({**data, "protocol": "something.else"})
    with pytest.raises(sim.SimulationError, match="version 2"):
        sim.parse_trace({**data, "version": 2})
    with pytest.raises(sim.SimulationError, match="no list of events"):
        sim.parse_trace({**data, "events": None})


def test_unknown_fields_and_event_types_are_ignored_as_the_protocol_asks():
    data = copy.deepcopy(fixture("expected/segment-1.json"))
    data["future_field"] = {"x": 1}
    data["events"].insert(3, {"seq": 99, "type": "future.event", "flow_depth": 0, "call_depth": 0, "new": True})
    for event in data["events"]:
        event["future"] = 1
    trace = sim.parse_trace(data)
    playback = sim.Playback([trace], invoice_doc())
    playback.last()
    reference = sim.Playback([sim.parse_trace(fixture("expected/segment-1.json"))], invoice_doc())
    reference.last()
    assert playback.view().marks == reference.view().marks and playback.view().context == reference.view().context


# ---------------------------------------------------------------- the playback, on Runner's own fixtures
def test_segment_one_pauses_inside_the_call_with_runners_checkpoint():
    playback = sim.Playback(fixture_traces()[:1], invoice_doc())
    playback.last()
    view = playback.view()
    assert view.marks[("step", "approval", "check")] == "paused"
    assert view.marks[("step", "main", "approval")] == "active"  # its call waits
    assert view.stack == [("step", "main", "approval")]
    assert (("step", "main", "approval"), "call") in view.taken
    end = playback.event.data
    assert end["type"] == "run.end" and end["checkpoint"] == {"flow_state": {"block": "approval", "step_index": 1},
                                                              "flow_stack": [{"block": "main", "step_index": 3}]}
    assert view.context["approval_requested"] is True and view.context["total"] == 1250.0
    assert view.context["order"]["card_token"] == {"$type": "redacted"}  # Runner's redaction, kept


def test_the_resumed_segment_returns_into_the_call_from_its_checkpoint():
    playback = sim.Playback(fixture_traces(), invoice_doc())
    start = next(i for i, e in enumerate(playback.events) if e.segment == 2)
    playback.go(start)
    assert playback.event.data["resume"] is True
    assert playback.view().stack == [("step", "main", "approval")]  # the frame _flow_stack kept
    back = next(i for i, e in enumerate(playback.events) if e.type == "call.return" and e.segment == 2 and e.data.get("resumed"))
    assert playback.view(back).stack == []
    playback.last()
    view = playback.view()
    assert view.marks[("step", "approval", "check")] == "visited"  # paused, then resumed
    assert view.marks[("step", "payment", "retry")] == "skipped"  # its condition was false the second time
    assert (("step", "payment", "retry"), "jump") in view.taken and (("step", "main", "payment"), "call") in view.taken
    expected = fixture("expected/segment-2.json")["events"][-1]["context"]
    assert view.context == expected and not view.approximate


def test_context_rebuilt_from_changes_matches_runners_snapshots_at_every_end():
    playback = sim.Playback(fixture_traces(), invoice_doc())
    for i, event in enumerate(playback.events):
        if event.type == "run.end":
            # one event earlier, from the changes alone, the context is the one Runner's run.end holds
            assert playback.view(i - 1).context == event.data["context"]


def test_navigation_moves_only_the_cursor():
    traces = fixture_traces()
    before = json.dumps([t.data for t in traces], sort_keys=True)
    playback = sim.Playback(traces, invoice_doc())
    assert playback.first() is False and playback.cursor == 0
    playback.next_step()
    assert playback.event.type == "step.start" and playback.event.step == "validated"
    playback.next_step()
    playback.next_step(-1)
    assert playback.event.step == "validated"
    assert playback.find_step(("step", "payment", "charge")) and playback.event.step == "charge" and playback.event.segment == 2
    assert playback.find_step(("step", "payment", "charge")) and playback.event.seq == 22  # the retry
    assert not playback.find_step(("step", "main", "nowhere"))
    playback.last()
    playback.next(5)
    assert playback.cursor == len(playback) - 1
    assert json.dumps([t.data for t in traces], sort_keys=True) == before
    assert playback.occurrences(("step", "payment", "charge")) == 2


def test_a_failed_step_and_a_truncated_trace_are_marked():
    events = [
        {"seq": 1, "type": "run.start", "flow_depth": 0, "call_depth": 0, "context": {"a": 1}, "checkpoint": {}},
        {"seq": 2, "type": "step.start", "flow_depth": 0, "call_depth": 0, "block": "main", "step": "validated", "index": 1},
        {"seq": 3, "type": "context.update", "flow_depth": 0, "call_depth": 0, "block": "main", "step": "validated",
         "changes": [{"key": "big", "op": "added", "after": {"$type": "truncated"}}]},
        {"seq": 4, "type": "activity.error", "flow_depth": 0, "call_depth": 0, "block": "main", "step": "validated",
         "function": "x", "error": {"class": "RuntimeException", "message": {"$type": "redacted"}}},
        {"seq": 5, "type": "trace.truncated", "flow_depth": 0, "call_depth": 0, "reason": "max_events",
         "dropped_events": 3, "compacted_events": 0},
    ]
    trace = sim.parse_trace({"protocol": sim.PROTOCOL, "version": 1, "events": events, "truncated": True,
                             "truncation": {"reason": "max_events", "dropped_events": 3}})
    playback = sim.Playback([trace], invoice_doc())
    playback.last()
    view = playback.view()
    assert view.marks[("step", "main", "validated")] == "failed" and view.approximate and trace.truncated


# ---------------------------------------------------------------- sessions and the cache
def test_a_session_keeps_a_snapshot_and_never_writes_the_flow(tmp_path):
    flow = tmp_path / "flows" / "a.yml"
    flow.parent.mkdir()
    flow.write_text("blocks: {}\n", encoding="utf-8")
    spec = tmp_path / "d.json"
    spec.write_text('{"doubles": {}}', encoding="utf-8")
    unsaved = "blocks:\n  main:\n    steps:\n      s:\n        activity: x\n"
    session = sim.new_session(tmp_path, flow, unsaved, {"doubles": {}}, spec, {"a": 1}, context_from="typed")
    assert session.snapshot.read_text(encoding="utf-8") == unsaved and flow.read_text(encoding="utf-8") == "blocks: {}\n"
    assert session.folder.parent == tmp_path / ".div" / "simulation"
    assert (tmp_path / ".div" / "simulation" / ".gitignore").read_text(encoding="utf-8").endswith("*\n")
    assert session.changed(unsaved) == []
    assert session.changed(unsaved + "# edited\n") == ["the Flow's YAML"]
    spec.write_text('{"doubles": {"x": {"returns": 1}}}', encoding="utf-8")
    assert session.changed(unsaved) == ["the doubles file"]
    loaded = sim.load_session(session.folder, tmp_path)
    assert loaded.meta["flow"] == "flows/a.yml" and loaded.segments == []


def test_cleanup_keeps_the_newest_and_the_open_and_never_touches_other_folders(tmp_path):
    flow = tmp_path / "a.yml"
    made = []
    for n in range(5):
        session = sim.new_session(tmp_path, flow, "blocks: {}\n", {"doubles": {}}, None, {})
        (session.folder / "trace-1.json").write_bytes(b"x" * 1000)
        os.utime(session.folder / sim.META, (1000 + n, 1000 + n))
        made.append(session.folder)
    stranger = tmp_path / ".div" / "simulation" / "mine"
    stranger.mkdir()
    (stranger / "keep.txt").write_text("not divide's", encoding="utf-8")
    removed = sim.cleanup(tmp_path, keep=2, active={made[0]})
    assert set(removed) == {made[1], made[2]}
    assert made[0].is_dir() and made[3].is_dir() and made[4].is_dir() and stranger.is_dir()
    room = sim._size(made[4]) + sim._size(made[3]) + 10  # the two newest fit
    removed = sim.cleanup(tmp_path, keep=10, max_bytes=room)
    assert set(removed) == {made[0]} and (stranger / "keep.txt").is_file()


# ---------------------------------------------------------------- real simulations, in separate processes
def run(coro):
    return asyncio.run(coro)


@needs_runner
def test_runners_own_example_gives_its_expected_traces_through_divide(tmp_path):
    """Protocol compatibility: Runner's example, simulated by divide in two processes, gives the events
    of Runner's own expected traces."""
    root = project_with_vendor(tmp_path, {})
    shutil.copytree(FIXTURES / "flows", root / "flows")
    flow = root / "flows" / "invoice.yml"
    runner = find_runner(root)
    session = sim.new_session(root, flow, flow.read_text(encoding="utf-8"), fixture("doubles.json"), None, fixture("context.json"))
    first = run(sim.run_segment(runner, session))
    assert first.state == "paused" and first.exit_code == 3 and first.trace is not None
    second = run(sim.run_segment(runner, session))
    assert second.state == "done" and second.exit_code == 0
    for n, segment in ((1, first), (2, second)):
        expected = fixture(f"expected/segment-{n}.json")
        assert segment.trace.events == expected["events"]
        assert segment.trace.result == expected["result"] and segment.trace.double_calls == expected["simulation"]["double_calls"]
    with pytest.raises(sim.SimulationError, match="nothing to resume"):
        run(sim.run_segment(runner, session))
    loaded = sim.load_session(session.folder, root)
    assert [s.state for s in loaded.segments] == ["paused", "done"] and len(loaded.traces) == 2


SIDE_EFFECTS = {
    "flows/effects.yml": """id: effects
blocks:
  main:
    steps:
      write:
        activity: write_marker
      check:
        condition: is_ready
        call: more.go
      skipped:
        condition: never
        activity: write_marker
      wait:
        module: tools
        activity: wait
  more:
    steps:
      go:
        module: tools
        activity: touch
      again:
        condition: is_ready
        jump: .done
      not_here:
        activity: write_marker
      done:
        context: {finished: true}
""",
    "functions/write_marker.php": "<?php\nreturn function (array &$c) { file_put_contents(__DIR__ . '/../MARKER-write', 'ran'); return 1; };\n",
    "functions/is_ready.php": "<?php\nfile_put_contents(__DIR__ . '/../MARKER-import', 'imported');\nreturn fn (array &$c): bool => true;\n",
    "functions/never.php": "<?php\nfile_put_contents(__DIR__ . '/../MARKER-never', 'imported');\nreturn fn (array &$c): bool => false;\n",
    "functions/tools/touch.php": "<?php\nreturn function (array &$c) { touch(__DIR__ . '/../../MARKER-touch'); return 'touched'; };\n",
    "functions/tools/wait.php": "<?php\nreturn function (array &$c) { touch(__DIR__ . '/../../MARKER-wait'); return 'waited'; };\n",
}
EFFECT_DOUBLES = {
    "doubles": {
        "write_marker": {"returns": "mocked", "context": {"written": "mocked"}},
        "is_ready": {"returns": True},
        "never": {"returns": False},
        "tools:touch": {"returns": "mocked touch"},
        "tools:wait": {"pause": True, "context": {"waiting": True}},
    },
    "budget": {"steps": 100, "transfers": 20, "seconds": 5},
}


@needs_runner
def test_side_effectful_functions_are_never_imported_or_called(tmp_path):
    root = project_with_vendor(tmp_path, SIDE_EFFECTS)
    flow = root / "flows" / "effects.yml"
    runner = find_runner(root)
    session = sim.new_session(root, flow, flow.read_text(encoding="utf-8"), EFFECT_DOUBLES, None, {"order": 1})
    first = run(sim.run_segment(runner, session))
    second = run(sim.run_segment(runner, session))
    assert (first.state, second.state) == ("paused", "done")
    assert not list(root.glob("MARKER-*")), "a Function of the project ran or was imported"
    playback = sim.Playback(session.traces, fm.parse(flow.read_text(encoding="utf-8")))
    playback.last()
    view = playback.view()
    # multiple Blocks, a condition-skipped Step, call, jump, context update and pause, all in the playback
    assert view.marks[("step", "main", "skipped")] == "skipped"
    assert (("step", "main", "check"), "call") in view.taken and (("step", "more", "again"), "jump") in view.taken
    assert ("step", "more", "not_here") not in view.marks or view.marks[("step", "more", "not_here")] == "skipped"
    assert view.context["written"] == "mocked" and view.context["finished"] is True and view.context["waiting"] is True
    assert any(e.type == "pause" for e in playback.events) and any(e.type == "context.update" for e in playback.events)
    # deterministic: the same inputs give the same events
    again = sim.new_session(root, flow, flow.read_text(encoding="utf-8"), EFFECT_DOUBLES, None, {"order": 1})
    run(sim.run_segment(runner, again))
    assert again.traces[0].events == session.traces[0].events
    # and the same Flow run for real does run them: the files are side-effectful indeed
    real = run(run_flow(runner, flow, cwd=root, context_text='{"_root_folder": "functions"}'))
    assert real.state in ("paused", "done") and (root / "MARKER-write").is_file()


@needs_runner
def test_a_missing_double_fails_in_runner_too_and_nothing_runs(tmp_path):
    root = project_with_vendor(tmp_path, SIDE_EFFECTS)
    flow = root / "flows" / "effects.yml"
    doubles = copy.deepcopy(EFFECT_DOUBLES)
    del doubles["doubles"]["is_ready"]
    session = sim.new_session(root, flow, flow.read_text(encoding="utf-8"), doubles, None, {})
    segment = run(sim.run_segment(find_runner(root), session))
    assert segment.state == "error" and segment.exit_code == 1
    assert any(e["type"] == "function.missing" for e in segment.trace.events)
    assert not list(root.glob("MARKER-*"))


LOOP = """blocks:
  main:
    steps:
      spin:
        activity: tick
        jump: .spin
"""


@needs_runner
def test_an_endless_jump_ends_at_runners_budget(tmp_path):
    root = project_with_vendor(tmp_path, {"flows/loop.yml": LOOP})
    flow = root / "flows" / "loop.yml"
    spec = {"doubles": {"tick": {"returns": 1}}, "budget": {"steps": 50, "transfers": 1000000, "seconds": 5}}
    session = sim.new_session(root, flow, LOOP, spec, None, {})
    segment = run(sim.run_segment(find_runner(root), session))
    assert segment.state == "error" and any(e["type"] == "budget.exhausted" for e in segment.trace.events)


@needs_runner
def test_the_time_limit_and_a_cancel_kill_php_and_keep_the_session(tmp_path):
    root = project_with_vendor(tmp_path, {"flows/loop.yml": LOOP})
    flow = root / "flows" / "loop.yml"
    spec = {"doubles": {"tick": {"returns": 1}},
            "budget": {"steps": 10 ** 9, "transfers": 10 ** 9, "seconds": 600}}
    runner = find_runner(root)
    session = sim.new_session(root, flow, LOOP, spec, None, {})
    segment = run(sim.run_segment(runner, session, timeout=1.5))
    assert segment.state == "timeout" and segment.trace is None and not session.trace_file(1).exists()
    assert not session.session_file.exists() and session.segments == []

    async def cancel_soon():
        task = asyncio.ensure_future(sim.run_segment(runner, session))
        await asyncio.sleep(1.0)
        task.cancel()
        return await task

    segment = run(cancel_soon())
    assert segment.state == "cancelled" and session.segments == [] and not session.session_file.exists()


@needs_runner
def test_a_changed_nested_flow_refuses_the_resume_and_a_real_checkpoint_is_never_a_session(tmp_path):
    child = "blocks:\n  inner:\n    steps:\n      hold:\n        activity: hold\n"
    parent = "blocks:\n  main:\n    steps:\n      sub:\n        activity: nested\n      after:\n        activity: after\n"
    root = project_with_vendor(tmp_path, {"flows/parent.yml": parent, "flows/child.yml": child})
    # a pause inside a nested Flow is its early return (Runner): the parent pauses after it
    spec = {"doubles": {"nested": {"flow": "flows/child.yml"}, "hold": {"returns": 1}, "after": {"pause": True}}}
    assert sim.check_spec(spec, sim.requirements(fm.parse(parent), project=root, doubles=spec["doubles"]), root).ok
    runner = find_runner(root)
    session = sim.new_session(root, root / "flows" / "parent.yml", parent, spec, None, {})
    first = run(sim.run_segment(runner, session))
    assert first.state == "paused"
    nested = [e for e in first.trace.events if e.get("flow_depth", 0) > 0]
    assert nested, "the nested Flow's events are in the trace"
    playback = sim.Playback(session.traces, fm.parse(parent))
    inside = next(i for i, e in enumerate(playback.events) if e.depth > 0 and e.type == "step.start")
    assert playback.view(inside).current == ("step", "main", "sub")  # the Step that runs the nested Flow
    (root / "flows" / "child.yml").write_text(child + "      more:\n        activity: hold\n", encoding="utf-8")
    second = run(sim.run_segment(runner, session))
    assert second.state == "invocation" and second.exit_code == 2 and "changed" in (second.problem or "")
    assert session.paused and len(session.segments) == 1  # Runner left its session: once the child is back, it resumes
    (root / "flows" / "child.yml").write_text(child, encoding="utf-8")
    third = run(sim.run_segment(runner, session))
    assert third.state == "done" and len(session.segments) == 2
    # Runner refuses a normal run's context as a session, and leaves it as it was
    checkpoint = root / "checkpoint.json"
    checkpoint.write_text('{"_runner_state": "paused", "_flow_state": {"block": "main", "step_index": 1}}', encoding="utf-8")
    other = sim.new_session(root, root / "flows" / "parent.yml", parent, spec, None, {})
    other.session_file.unlink(missing_ok=True)
    shutil.copy(checkpoint, other.session_file)
    other.segments.append(sim.Segment(1, "paused", 3, 0.0))
    refused = run(sim.run_segment(runner, other))
    assert refused.state == "invocation" and "not a simulation session" in refused.problem
    assert json.loads(other.session_file.read_text(encoding="utf-8"))["_runner_state"] == "paused"
