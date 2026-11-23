# Function simulation: feasibility and decision (#15)

**Status:** approved (#15), with the five decisions of its review. **Engine:** built in `divide.run.funcsim`
(#21), tested by `tests/test_funcsim.py`; the line trace (#22) and the UI (#23) are not built yet.
**Proof of concept:** [`prototypes/function-simulation`](../prototypes/function-simulation) (not packaged), kept for
the line trace until #22 promotes it, tested by `tests/test_funcsim_poc.py`.

## 1. Question

Can divide offer a **Mock Simulation** of one Runner Function, and do it honestly? That means:

- the Function's body runs with an explicit JSON context;
- its dependencies are replaced by declared doubles, and a missing double fails loudly;
- each PHP line it ran is recorded with its locals, the context's changes, its result, its output and its errors;
- the result can be replayed.

This is not the Flow simulation of #10 / Runner #35. There, Runner simulates the *Flow* and no Function code runs. Here, the Function's own PHP *does* run, and only what it asks for is replaced.

## 2. Decision

1. **Feasible, for Functions written for injection.** A Function that gets its collaborators from the context (`$context['_importer']`, service objects under context keys) can be simulated deterministically. The doubles answer, and a missing double throws `DivideMissingDouble` before any real dependency loads. The PoC shows this with running code (§4, tests).
2. **Not a sandbox.** A double replaces only what the Function *asks the context for*. PHP's own functions (files, PDO, curl, `mail`, `time()`) and the Function file's top-level code run for real. divide will say so every time, and require an explicit per-project opt-in. It will never claim side-effect-free execution (§6).
3. **Line trace: non-interactive DBGp stepping**, on divide's existing Xdebug client (`divide.run.dbgp.DebugSession`). It is a separate session with no UI and no user breakpoints. One `step_into` per line, and the locals are read by an `eval` in the Function's frame. Xdebug's trace mode, coverage, ticks and AST instrumentation were evaluated and rejected (§5).
4. **A separate, versioned protocol**: the `divide.function-simulation` v1 scenario and the `divide.function-trace` v1 trace. These are PHP source lines, never Runner's semantic Step events (§7). The doubles' outcome grammar *is* Runner's `--simulate` grammar (`returns`, `throws`, `sequence`, `context`), so users learn one.
5. **Build it in three issues** (engine #21, trace #22, UI #23), plus one isolation spike (#24) (§9). This issue stops at the decision and the PoC.

## 3. What a Function depends on

From Runner 0.3.0 (`runner.php`: `importer()`, `run()`'s helpers, `HELPER_KEYS`, `RESERVED_KEYS`) and divide's Test Function (`functest.php`):

| Dependency | How the Function reaches it | Mock Simulation |
|---|---|---|
| Context data | `$context['key']`, by reference | **Input**: the scenario's `context`. `_` keys are refused (Runner's). |
| Other Functions | `$context['_importer']($name, $module)` | **Doubled** (`doubles.importer`, keyed `module:name` or `name`, like Runner). Not doubled: throws, and the real file is never required (tested). |
| Runner's logger | `$context['_logger']($level, $msg)` | **Recorded**, in the result. |
| Service objects in the context (mailer, repository, PDO wrapper...) | `$context['mailer']->send(...)`. The PHP code that starts the Flow puts them there; JSON cannot hold them. | **Doubled** as strict objects (`doubles.services`). An undeclared method or property throws (tested). |
| Runner's Flow machinery (`_update_context`, `_wrap_*`, `_check_pause`, `_flow_state`, `_flow_stack`, ...) | Present only inside a Flow run | **Absent.** A Function that drives the Flow belongs to the Flow simulation (#10). |
| Composer classes (`new Acme\Mailer`, `Foo::bar()`) | Autoload | **Fail loudly by default**: the project's autoload is not loaded, and a throwing autoloader names the class (tested). `"autoload": true` opts in, and the classes are then *real code*. Class doubles are a follow-up spike. |
| PHP functions and extensions: files, sockets, curl, PDO, `mail`, `exec`, `time()`, `rand()` | Called directly | **Cannot be intercepted** on a standard PHP. That would need an extension such as `uopz` or `runkit7`, which is not installed by default and cannot be assumed on users' PHP. Namespaced-function shadowing works only for unqualified calls in namespaced code. A *tripwire* blocks part of it (§6). |
| The Function file's top-level code, its `require`s, globals, static state, environment | Runs when the file is required | **Real.** Only the Function under test is required. |

The **sha256** of the Function's file is in the scenario. A changed file is reported as `stale` before anything is called (tested).

## 4. The scenario (`divide.function-simulation` v1)

```json
{
    "protocol": "divide.function-simulation",
    "version": 1,
    "description": "A large order: tax doubled, the mailer accepts",
    "function": {"module": null, "name": "checkout", "sha256": "79ac23c6...b021464"},
    "context": {"items": [{"price": 60, "qty": 1}, {"price": 20, "qty": 2}], "email": "buyer@example.com"},
    "doubles": {
        "importer": {"billing:tax": {"returns": 21.0, "context": {"tax_rate": 0.21}}},
        "services": {"mailer": {"send": {"sequence": [{"returns": true}]}}}
    },
    "unknown": "fail",
    "autoload": false,
    "expect": {"returns": "notified", "context": {"review": true}},
    "limits": {"lines": 2000, "seconds": 20, "stdout": 65536}
}
```

- **Outcomes:** exactly one of `returns`, `throws` (a message) or `sequence` (one outcome per call, and a call past the end fails). An optional `context` is merged into the context, as in Runner's `--simulate`.
- **`unknown`:** only `"fail"` is accepted. A missing double never falls back to the real dependency.
- **`expect`:** `returns` and `context` (a subset of the context after), the same checks as Test Function's scenarios (`.div/function-tests`): `funcsim.check`.
- **`limits`:** bounded: lines ≤ 100,000, seconds ≤ 300, stdout ≤ 4 MiB.
- **Refusal:** the scenario is checked before anything runs. A wrong scenario starts no process (tested with a marker file).
- **Storage:** `.div/function-simulations/<module>/<name>.<scenario>.json` (`_root` for a Function with no Module), versioned and shareable: divide writes no `.gitignore` there. Traced runs (#22) go to an ignored cache, `.div/function-simulation/`, with the retention of #10.

## 5. The line trace

| Mechanism | Evidence (Xdebug 3.5.0, PHP 8.5) | Verdict |
|---|---|---|
| Xdebug **trace mode** (`xdebug.mode=trace`, `trace_format=1`, `collect_assignments`, `collect_return`) | Records calls, returns and *assignments* with file and line. A line with no assignment and no call has no record: an `if`, an `echo`, a `return $x`. Values are PHP-like text cut by `var_display_max_*`, not JSON. | Rejected as the trace; possibly a cheap "assignments only" mode later. |
| Xdebug **coverage** | The set of lines that ran: no order, no count, no values. | Rejected. |
| `declare(ticks=1)` | Needs the source rewritten. A tick function cannot see the caller's locals. | Rejected. |
| AST instrumentation (`nikic/php-parser`) | A new dependency, the user's code rewritten, line mapping to maintain. | Rejected. |
| **DBGp stepping, non-interactive** (`DebugSession`) | Every line Xdebug breaks on, in order, with structured locals. **~2,000 lines/s**: 2,004 lines in 0.91 s for a 1,000-iteration loop, with 3 round trips per line (step, stack, eval). The example's 15 lines take 0.055 s. | **Chosen.** |

How it works:

1. A temporary breakpoint is set on the harness's call line.
2. The tracer `step_into`s, and records only lines of the Function's file.
3. Other code (the harness's doubles, other files) is left with `step_out`.
4. When the harness's `{main}` is reached again, it `run`s to the end.

It is its own `DebugSession` on its own port. It shares nothing with the user's interactive debugger and never uses the user's breakpoints.

Line semantics (from the PoC; tests in parentheses):

- Xdebug stops **before** a line runs, so a line's `locals` are what the lines before it left.
- A branch not taken has no line (tested).
- A line with several statements is one event with a `repeat` count. Changes made by a double are attached to the line that called it (`after_call`).
- A `foreach` header appears on the first pass only: Xdebug maps the loop's next-item opcode to the body's first line.
- Closures defined in the Function file are traced at `depth` > 0.
- The doubles' own code is not traced (tested: every event has depth 0).

**Observer effect, found and fixed.** `get_defined_vars()` keeps references. The PoC's first version wrote the cleaned context back through the by-reference `$context` and broke the Function (`_importer` became null). The locals encoder now builds a new array and never assigns into what it observes. A test compares a traced run with a plain run (return, context, double calls).

## 6. Isolation, limits, trust

- **Process:** one PHP child process per simulation. The harness's result goes to its own stdout after a random marker. The Function's stdout goes into a bounded output buffer, so it cannot break the result by accident. A hostile Function runs in the same process and could reach the marker: the project is trusted input (below).
- **Limits:** wall-clock seconds (the process is killed; tested with an endless loop), lines (the trace is truncated and marked; tested), `memory_limit`, stdout bytes.
- **Cancellation:** `DebugSession.stop()` for a traced run (#22), or a kill for the plain run. The process is tracked by divide's `children` registry, so it never outlives divide.
- **Tripwire (opt-in, best effort):**
  - `disable_functions` covers process, network and mail functions and the commonest file writes;
  - `open_basedir` is the project, the harness and the work folder;
  - `allow_url_fopen=0`.

  Tested both ways:
  - `file_put_contents` outside the project is stopped;
  - `fopen` plus `stream_copy_to_stream` inside the project still writes: **a deny-list is not a sandbox**.
- **Without the tripwire**, a direct write happens (tested). This is the evidence for the warning.
- **Trust model:**
  - A Mock Simulation runs project code. The project and its scenarios are trusted inputs, as for Run, Debug and Test Function.
  - The first simulation in a project asks for an explicit opt-in, recorded in the user's settings, not in the project.
  - The dialog and the trace say **MOCK SIMULATION: real PHP runs; only declared dependencies are replaced**.
- **Stronger isolation:** an OS sandbox around the child. On Linux, bubblewrap or a container with no network and a read-only project bind. It is platform-specific: nothing equivalent ships on Windows or macOS. It is proposed as a separate spike, not a promise.
- **Never touched:** Flow checkpoints (`.div/runner/`) and #10's sessions (`.div/simulation/`).

## 7. The trace (`divide.function-trace` v1) and what it shares with #10

```json
{
  "protocol": "divide.function-trace", "version": 1,
  "scenario": {"sha256": "4f92...e7f682", "description": "A large order: tax doubled, the mailer accepts"},
  "function": {"module": null, "name": "checkout", "file": "functions/checkout.php", "sha256": "79ac...1464"},
  "result": {"status": "returned", "return": "notified", "return_type": "string",
             "before": {"...": "..."}, "after": {"...": "...", "total": 121.0, "review": true},
             "calls": [{"double": "billing:tax", "call": 1, "args": [], "outcome": "returns"},
                       {"double": "mailer->send", "call": 1, "args": ["buyer@example.com", "Total: 121"], "outcome": "returns"}],
             "logs": [{"level": "INFO", "message": "large order"}], "stdout": "sent: yes\n", "stdout_cut": 0},
  "events": [
    {"seq": 1, "type": "line", "line": 7, "depth": 0, "locals": {"set": {"context.items": ["..."], "context.email": "buyer@example.com"}}},
    {"seq": 2, "type": "line", "line": 8, "depth": 0, "locals": {"set": {"total": 0.0}}},
    {"seq": 8, "type": "line", "line": 13, "depth": 0, "locals": {"set": {"tax": {"$type": "closure"}}}},
    {"seq": 9, "type": "line", "line": 14, "depth": 0, "locals": {"set": {"total": 121.0, "context.tax_rate": 0.21}}},
    {"seq": 14, "type": "line", "line": 20, "depth": 0, "locals": {"set": {"context.total": 121.0}}, "repeat": 2}
  ],
  "truncated": false
}
```

Statuses:

- the outcomes Test Function already reports: `returned`, `exception` (with `missing_double`), `fatal`, `exit`;
- `stale` (the file changed);
- `missing` (no such Function);
- `timeout`;
- `line_limit`.

Consumers ignore unknown fields and event types, as for Runner's trace.

**Reused from #10 (Runner trace):**

- the session folder and its retention (`divide.run.simulate.cleanup`);
- the playback cursor (an event list, first/last/next/previous, "the state at event N" folded from changes);
- the doubles' outcome grammar;
- the version gate;
- the Simulation dialog's layout.

**Not reused:**

- Runner's event types and the Flow board's marks. A PHP line is shown in the **code editor** (a gutter mark plus a locals and context panel), never as a Step on the board.
- The two protocols have different names and different trust labels. A Flow simulation runs no Function code; a Mock Simulation does.

## 8. The workflow (proposed)

1. **Pick the Function.** In the Functions window or with T on a Step, choose **Simulate...** (Shift+T). Test Function stays **Run / Debug**, for real.
2. **The dialog.** It has the context (JSON), the doubles (pre-filled from a static scan of `_importer` calls and `$context['x']->method(` in the file, all marked `unknown: fail`), the expectations and the limits. Under them, the banner **MOCK SIMULATION: real PHP runs; only these dependencies are replaced**.
3. **Simulate.** It runs one bounded child process with the line trace. Esc cancels.
4. **Playback.** The code editor opens read-only on the Function, with the current line marked:
   - F7 / Shift+F7: next / previous line;
   - F8: next line at the same depth;
   - Ctrl+Home / Ctrl+End: first / last event.

   The panel shows the locals changed, the context so far, the double calls and the output. The result is at the end, and **Save as scenario** keeps it.

## 9. Follow-up issues

Estimates are for one developer who knows divide, with tests:

1. **Function Mock Simulation engine** (`divide.run.funcsim`), #21. About 3 days. It promotes the PoC harness and driver:
   - resolution through `flowfunctions` and Test Function's `request_for`;
   - scenarios in `.div/function-simulations/`;
   - the `children` registry and cancellation;
   - the opt-in and the tripwire option.

   Integration tests are the PoC's, against `examples/runner` and `examples/generator`.
2. **Line trace recorder and `divide.function-trace` v1**, #22. About 3 days. It adds:
   - the bounded DBGp stepper;
   - storage, retention and a reader that refuses another version;
   - a playback model shared with #10's cursor.

   Integration tests:
   - Xdebug in CI (already installed);
   - a traced run equals a plain run;
   - branches, closures, exceptions, limits, truncation, cancellation mid-step.
3. **Mock Simulation UI and help (EN/ES)**, #23. About 5 days:
   - the dialog, with doubles pre-filled by a static scan;
   - playback in the code editor, with the MOCK banner;
   - Save as scenario, and Real Run / Debug kept apart;
   - the help pages and screenshots, after UI review.

   UI tests at 80×24 and 120×34 and in the phosphor themes.
4. **Spike: stronger isolation and class doubles**, #24. About 2 days, a decision only:
   - bubblewrap or containers on Linux, and what Windows and macOS can offer;
   - class doubles generated at autoload time, which work only for classes not yet loaded and not `final`-dependent.

## 10. Limits of this decision

- Functions that are not written for injection (direct I/O, `new` of real services, static calls) can be simulated only with `autoload` opted in, and then those parts are real. Simulation shows which dependencies it replaced; it cannot show what it did not.
- Non-determinism inside the Function (`time()`, `rand()`, `uniqid()`) is not controlled.
- The trace needs Xdebug. Without it, a simulation still runs with doubles but has no lines.
- Values in the trace are bounded:
  - strings over 4 KiB are cut and marked;
  - arrays over 1,000 items are truncated;
  - depth is limited to 16;
  - objects are shown as their class and public properties.
