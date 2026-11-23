"""The PHP line trace of a Function Mock Simulation (divide.run.functrace, #22): divide's own Xdebug client
stepping through one Function with no person at it, the divide.function-trace v1 document, its cache
and its playback, on a copy of examples/runner (the fixtures of tests/test_funcsim.py).

A traced run is the same Mock Simulation as an untraced one (real PHP runs); these tests show that
watching it changes nothing in its result. Needs php with Xdebug (php.ini or DIVIDE_XDEBUG=path/xdebug.so)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

import test_funcsim as base  # the #21 fixtures (a module attribute: its tests are not collected here)
from divide.run import children
from divide.run import funcsim as fs
from divide.run import functrace as tr
from divide.run import simulate as flow_sim

XDEBUG = os.environ.get("DIVIDE_XDEBUG")


def _xdebug() -> bool:
    if not shutil.which("php"):
        return False
    if XDEBUG and Path(XDEBUG).is_file():
        return True
    return "xdebug" in subprocess.run(["php", "-m"], capture_output=True, text=True).stdout.lower().split()


pytestmark = pytest.mark.skipif(not _xdebug(), reason="needs php with Xdebug (php.ini or DIVIDE_XDEBUG=path/xdebug.so)")
project = base.project
scenario, write, just = base.scenario, base.write, base.just


def run(project: Path, data: dict, *, trace: bool = True, **kwargs) -> fs.Simulation:
    return asyncio.run(fs.simulate(fs.request_for(project, data), trace=trace, xdebug=XDEBUG, **kwargs))


def line_of(path: Path, text: str, nth: int = 1) -> int:
    found = [n for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1) if text in line]
    return found[nth - 1]


def checkout(project: Path) -> Path:
    return project / "functions" / "checkout.php"


def _no_php_left() -> None:
    assert children.running() == [], "a PHP process outlived the trace"


# ---------------------------------------------------------------- agreement
def test_a_traced_run_gives_what_an_untraced_run_gives(project):
    plain = run(project, scenario(), trace=False)
    traced = run(project, scenario())
    assert plain.ok and traced.ok and traced.traced and not plain.traced
    assert traced.returned == plain.returned == "notified"
    assert traced.after == plain.after and traced.before == plain.before
    assert traced.calls == plain.calls and traced.logs == plain.logs and traced.output == plain.output
    assert [(c.path, c.after) for c in traced.changes] == [(c.path, c.after) for c in plain.changes]
    assert fs.check(traced) == fs.check(plain) and all(ok for ok, _ in fs.check(traced))
    assert traced.events and not plain.events


def test_observing_never_writes_into_the_functions_context(project):
    write(project, "t", """return function (array &$c): bool {
    $a = 1;
    $b = $a + 1;
    $c['seen'] = $b;
    return is_callable($c['_importer']) && is_callable($c['_logger']) && $c['seen'] === 2;
};
""")
    out = run(project, just())
    assert out.ok and out.returned is True and out.after == {"seen": 2}


def test_agreement_on_an_exception_and_with_the_tripwire(project):
    data = scenario()
    data["doubles"]["services"]["mailer"] = {"queue": {"returns": True}}
    plain, traced = run(project, data, trace=False), run(project, data)
    assert plain.status == traced.status == "exception" and traced.missing_double
    assert traced.exception["message"] == plain.exception["message"] and traced.after == plain.after
    plain, traced = run(project, scenario(), trace=False, tripwire=True), run(project, scenario(), tripwire=True)
    assert plain.ok and traced.ok and traced.after == plain.after and traced.tripwire


# ---------------------------------------------------------------- lines
def test_the_trace_records_the_functions_lines_in_order_with_their_locals(project):
    out = run(project, scenario())
    file = checkout(project)
    lines = [e["line"] for e in out.events]
    first, body = line_of(file, "$total = 0.0;"), line_of(file, "$total += $item")
    assert lines[0] == first and lines.count(body) == 2  # two items: the loop body twice
    assert line_of(file, '$context["_logger"]') in lines and line_of(file, '$context["review"] = true') in lines
    assert lines[-1] == line_of(file, "return $sent")
    assert all(e["type"] == "line" and e["depth"] == 0 for e in out.events)  # the doubles' own code is not traced
    assert [e["seq"] for e in out.events] == list(range(1, len(out.events) + 1))
    start = out.events[0]["locals"]["set"]
    assert start["context.email"] == "buyer@example.com"
    assert not any(k.startswith("context._") or k == "context.mailer" for e in out.events
                   for k in (e.get("locals") or {}).get("set", {}))  # the helpers and doubles are not data
    assert out.events[1]["locals"]["set"] == {"total": 0.0}  # before line 2 ran: what line 1 left


def test_a_branch_not_taken_has_no_line(project):
    out = run(project, scenario(context={"items": [{"price": 1, "qty": 1}], "email": "a@b"}, expect={}))
    lines = [e["line"] for e in out.events]
    assert out.ok and out.returned == "notified"
    assert line_of(checkout(project), "if ($total > 100)") in lines
    assert line_of(checkout(project), '$context["review"] = true') not in lines


def test_a_closure_of_the_function_is_traced_at_depth_one(project):
    file = write(project, "t", """return function (array &$c): int {
    $twice = function (int $x): int {
        $y = $x * 2;
        return $y;
    };
    $a = $twice(3);
    $b = $twice($a);
    return $b;
};
""")
    out = run(project, just())
    assert out.ok and out.returned == 12
    inner = [e for e in out.events if e["depth"] == 1]
    assert {e["line"] for e in inner} >= {line_of(file, "$y = $x * 2;"), line_of(file, "return $y;")}
    assert len([e for e in inner if e["line"] == line_of(file, "$y = $x * 2;")]) == 2
    assert inner[0]["locals"]["set"]["x"] == 3
    playback = tr.LinePlayback(tr.parse_trace(tr.document(out)))
    playback.go(next(i for i, e in enumerate(playback.events) if e["line"] == line_of(file, "$a = $twice(3);")))
    playback.next_same_depth()
    assert playback.event["line"] == line_of(file, "$b = $twice($a);")  # over the closure's lines
    assert playback.view().locals["a"] == 6


def test_an_exception_ends_the_trace_on_its_line(project):
    data = scenario()
    data["doubles"]["services"]["mailer"] = {"queue": {"returns": True}}
    out = run(project, data)
    assert out.status == "exception" and out.missing_double
    assert out.events[-1]["line"] == line_of(checkout(project), "->send(")


def test_statements_on_one_line_fold_into_repeat_unless_they_change_locals(project):
    file = write(project, "t", "return function (array &$c): int {\n    echo 'x'; echo 'y'; echo 'z';\n"
                                "    $a = 1; $b = 2;\n    return $a + $b;\n};\n")
    out = run(project, just())
    assert out.ok and out.output == "xyz" and out.returned == 3
    echoes = [e for e in out.events if e["line"] == line_of(file, "echo 'x'")]
    assert len(echoes) == 1 and echoes[0].get("repeat", 0) >= 1  # no change between them: one event
    sets = [e for e in out.events if e["line"] == line_of(file, "$a = 1; $b = 2;")]
    assert len(sets) == 2 and sets[1]["locals"]["set"] == {"a": 1}  # a change mid-line: its own event


def test_large_values_are_cut_and_marked(project):
    write(project, "t", """return function (array &$c): int {
    $big = str_repeat('x', 10000);
    $list = range(1, 1500);
    return strlen($big) + count($list);
};
""")
    out = run(project, just())
    assert out.ok and out.returned == 11500
    view = tr.LinePlayback(tr.parse_trace(tr.document(out)))
    view.last()
    shown = view.view()
    assert shown.locals["big"] == {"$type": "string", "head": "x" * 4096, "bytes": 10000}
    assert shown.locals["list"]["$truncated"] == 1500 and len(shown.locals["list"]) == 1001
    assert shown.cut == ["big", "list"]


# ---------------------------------------------------------------- bounds and stops
def test_the_line_limit_truncates_the_trace(project):
    write(project, "t", "return function (array &$c): int {\n    $s = 0;\n    for ($i = 0; $i < 1000; $i++) {\n"
                        "        $s += $i;\n    }\n    return $s;\n};\n")
    out = run(project, just() | {"limits": {"lines": 50}})
    assert out.status == "line_limit" and out.truncated and len(out.events) == 50
    assert tr.document(out)["truncated"] is True
    _no_php_left()


def test_a_timeout_mid_step_leaves_no_php(project):
    write(project, "t", "return function (array &$c): void {\n    while (true) {\n        $c['n'] = ($c['n'] ?? 0) + 1;\n    }\n};\n")
    out = run(project, just() | {"limits": {"seconds": 2, "lines": 100_000}})
    assert out.status == "timeout" and out.events
    _no_php_left()


def test_cancelling_mid_step_leaves_no_php(project):
    write(project, "t", "return function (array &$c): void {\n    while (true) {\n        $c['n'] = ($c['n'] ?? 0) + 1;\n    }\n};\n")
    request = fs.request_for(project, just() | {"limits": {"lines": 100_000}})

    async def go() -> None:
        task = asyncio.ensure_future(fs.simulate(request, trace=True, xdebug=XDEBUG))
        for _ in range(200):
            await asyncio.sleep(0.05)
            if children.running():
                break
        assert children.running(), "PHP never started"
        await asyncio.sleep(1.0)  # well into the stepping
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
    _no_php_left()


def test_a_stale_or_missing_function_has_no_lines(project):
    file = write(project, "t", "return fn (array &$c): int => 1;\n")
    data = fs.new_scenario(None, "t", file)
    file.write_text(file.read_text(encoding="utf-8") + "// edited\n", encoding="utf-8")
    out = run(project, data)
    assert out.status == "stale" and out.events == [] and out.traced
    out = run(project, scenario("nowhere", "billing"))
    assert out.status == "missing" and out.events == []


def test_without_xdebug_the_trace_is_refused_before_php_starts(project, monkeypatch):
    async def none(*_a, **_k):
        return None

    monkeypatch.setattr(tr, "xdebug_ini", none)
    with pytest.raises(tr.TraceError, match="Xdebug"):
        run(project, scenario())
    _no_php_left()


def test_the_trace_refuses_what_an_untraced_run_refuses(project):
    fs.distrust(project)
    with pytest.raises(fs.NotTrusted):
        run(project, scenario())


def test_throughput_is_usable(project):
    write(project, "t", "return function (array &$c): int {\n    $s = 0;\n    for ($i = 0; $i < 300; $i++) {\n"
                        "        $s += $i;\n    }\n    return $s;\n};\n")
    started = time.monotonic()
    out = run(project, just())
    seconds = time.monotonic() - started
    assert out.ok and out.returned == 44850 and len(out.events) >= 600
    assert len(out.events) / seconds > 30  # loose: ~2,000 lines/s measured; CI machines vary


# ---------------------------------------------------------------- the protocol
def test_the_document_is_divide_function_trace_v1(project):
    out = run(project, scenario())
    doc = tr.document(out)
    assert doc["protocol"] == "divide.function-trace" and doc["version"] == 1
    assert doc["function"] == {"module": None, "name": "checkout", "file": "functions/checkout.php",
                               "sha256": fs.sha256(checkout(project)), "pinned": False}
    assert doc["result"]["status"] == "returned" and doc["result"]["return"] == "notified"
    assert doc["scenario"]["sha256"] == tr.scenario_sha256(scenario())
    assert all(str(project) not in e.get("function", "") for e in doc["events"])  # no machine paths
    read = tr.parse_trace(json.loads(json.dumps(doc)))
    assert read.status == "returned" and read.lines == doc["events"] and not read.pinned
    pinned = tr.document(run(project, fs.new_scenario(None, "checkout", checkout(project)) | {
        "context": scenario()["context"], "doubles": scenario()["doubles"]}))
    assert pinned["function"]["pinned"] is True and tr.parse_trace(pinned).pinned


def _doc(**change) -> dict:
    doc = {"protocol": "divide.function-trace", "version": 1, "scenario": {}, "function": {"name": "t"},
           "result": {"status": "returned"}, "events": [{"seq": 1, "type": "line", "line": 3, "depth": 0}],
           "truncated": False}
    doc.update(change)
    return doc


def test_another_version_or_protocol_is_refused():
    with pytest.raises(tr.TraceError, match="version 2"):
        tr.parse_trace(_doc(version=2))
    with pytest.raises(tr.TraceError, match="Not a Function trace"):
        tr.parse_trace(_doc(protocol="divengine.runner.trace"))
    with pytest.raises(tr.TraceError):
        tr.parse_trace(_doc(events={}))
    with pytest.raises(tr.TraceError):
        tr.parse_trace([])


def test_unknown_fields_and_event_types_are_ignored():
    doc = _doc(later={"x": 1}, events=[{"seq": 1, "type": "line", "line": 3, "depth": 0, "new": True},
                                       {"seq": 2, "type": "watch", "expr": "$a"}, "junk",
                                       {"seq": 3, "type": "line", "line": 4, "depth": 0}])
    read = tr.parse_trace(doc)
    assert [e["seq"] for e in read.events] == [1, 2, 3] and [e["line"] for e in read.lines] == [3, 4]
    assert len(tr.LinePlayback(read)) == 2


def test_function_lines_and_runner_events_never_mix(project):
    doc = tr.document(run(project, scenario()))
    with pytest.raises(flow_sim.SimulationError):
        flow_sim.parse_trace(doc)  # a Flow playback refuses a Function trace
    with pytest.raises(tr.TraceError):
        tr.parse_trace({"protocol": flow_sim.PROTOCOL, "version": flow_sim.VERSION, "events": []})


# ---------------------------------------------------------------- playback
def test_playback_moves_and_folds_the_state_before_each_line(project):
    out = run(project, scenario())
    playback = tr.LinePlayback(tr.parse_trace(tr.document(out)))
    file = checkout(project)
    assert len(playback) == len(out.events) and playback.cursor == 0
    assert not playback.first() and playback.next() and playback.cursor == 1
    assert playback.next(-1) and playback.cursor == 0 and not playback.next(-1)
    assert playback.last() and playback.event["line"] == line_of(file, "return $sent")
    assert playback.view(0).locals == {} and playback.view(0).context == scenario()["context"]
    after_tax = next(i for i, e in enumerate(playback.events) if e["line"] == line_of(file, "if ($total > 100)"))
    view = playback.view(after_tax)
    assert view.locals["total"] == 121.0 and view.context["tax_rate"] == 0.21 and "review" not in view.context
    last = playback.view()
    assert last.context == out.after  # the return line changes nothing: the folded state is the result's
    assert last.locals["sent"] is True and last.depth == 0 and last.cut == []
    playback.go(10 ** 6)
    assert playback.cursor == len(playback) - 1


# ---------------------------------------------------------------- runs in the project
def test_runs_are_kept_out_of_git_with_retention_and_never_touch_runners_or_flow_simulations(project):
    runner = project / ".div" / "runner" / "flows" / "order.yml.context.json"
    flow = project / ".div" / "simulation" / "s1"
    runner.parent.mkdir(parents=True)
    runner.write_text("{}", encoding="utf-8")
    flow.mkdir(parents=True)
    (flow / flow_sim.META).write_text(json.dumps({"protocol": flow_sim.META_PROTOCOL}), encoding="utf-8")
    out = run(project, scenario())
    first = tr.save_run(out)
    assert first.parent == project / ".div" / "function-simulation"
    assert (first.parent / ".gitignore").read_text(encoding="utf-8").splitlines()[-1] == "*"
    trace, data = tr.load_run(first)
    assert trace.status == "returned" and data == scenario() and len(trace.lines) == len(out.events)
    saved = [first, *(tr.save_run(out) for _ in range(3))]
    for n, folder in enumerate(saved):  # distinct times, oldest first: the retention orders by them
        os.utime(folder / tr.META, (1_000_000 + n, 1_000_000 + n))
    assert tr.runs(project) == saved[::-1]
    removed = tr.cleanup(project, keep=1, active={saved[0]})
    assert set(removed) == {saved[1], saved[2]} and tr.runs(project) == [saved[3], saved[0]]
    tr.cleanup(project, keep=0)
    assert tr.runs(project) == []
    assert runner.read_text(encoding="utf-8") == "{}" and flow_sim.sessions(project) == [flow]
    kept = tr.save_run(out)
    flow_sim.cleanup(project, keep=0)
    assert tr.runs(project) == [kept] and flow_sim.sessions(project) == []  # each cache only sees its own
    assert runner.read_text(encoding="utf-8") == "{}"
