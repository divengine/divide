# Flow Simulation

**Simulation** runs a [Runner](https://github.com/divengine/runner) Flow without running its Functions. Runner answers each `condition` and `activity` from **test doubles** you declare, records what the Flow does as a list of events, and divide replays those events on the Flow's board. You move through the events one by one, forwards and backwards, and the board shows which Steps ran, which were skipped, which `call` and `jump` were taken, where the Flow paused and how the context changed.

Simulation and replay are one feature. The simulation runs once, in a PHP process of its own. Replaying its events never runs anything again.

![Shift+F9 on the Flow Designer: the Simulate Flow dialog, the simulation replayed event by event on the board, F8 by Step, the pause at invoice.sum and Ctrl+F9 resuming it in a new process](images/flow-simulation.gif)

Runner simulates the Flow, not divide. It uses its own compiler and runtime, the ones a real run uses: the same Blocks, Steps, `call`, `jump`, `pause`, `_flow_state` and `_flow_stack`. There is no second interpreter.

| | **Real Run** (Ctrl+F9) | **Simulation** (Shift+F9) |
|---|---|---|
| The Flow's Functions | run, with their side effects (files, databases, network) | never loaded or called: the doubles answer |
| Runner needed | 0.2.0 or newer | 0.3.0 or newer |
| What you get | the context, saved to resume ([[Running Flows]]) | every event, replayed on the board |
| Pause and resume | from the saved context in `.div/runner/` | from Runner's simulation session in `.div/simulation/` |

## What you need

- **PHP 8.1** or newer on the `PATH`.
- **Runner 0.3.0** or newer installed in the project:

  ```bash
  composer require divengine/runner:^0.3
  ```

  With an older Runner, Simulation says so and runs nothing. Run (Ctrl+F9) still runs the Flow for real.

The repository's `examples/runner` is ready to try. Run `composer install` in it, open `flows/fulfil.yml` and press **Shift+F9**: its doubles are already in `.div/simulations/flows/fulfil.yml.doubles.json`.

## Simulate a Flow

Open the **Simulate Flow** dialog from a Flow's code, its Flow window or its board, in any of these ways:

- **Shift+F9**;
- **Run > Simulate Flow with doubles**;
- **S** on the [[Flow Designer]]'s board.

The dialog has:

- **Initial context**: a JSON file, or a JSON object typed in the field. Empty: an empty context.
- **Doubles**: the doubles file, in Runner's `--simulate` format (below). By default, `.div/simulations/<flow>.doubles.json`. It is a project file the team can share and keep in Git.
- **Keep error and log messages in the trace**: Runner's `--trace-messages`. It is off by default. Without it, an error's or a log's message is left out of the trace, because it is free text that could hold a secret. The error's class and the log's level are still kept.

Under the fields, the dialog says how many of the Flow's functions need a double, which ones still have none, and what is wrong with the file. **A simulation is refused before anything runs** in two cases:

- a reference of the Flow (or of a nested Flow a double names) has no double;
- the file is not what Runner takes: two outcomes in one double, a condition that pauses, a context key starting with `_`, a nested Flow that is not there, an unknown budget.

Runner checks the file again when it simulates.

The buttons:

- **Simulate** runs the simulation, in a box that **Esc** stops. The Simulation window then opens at the last event.
- **Edit doubles** opens the doubles file in an editor. If the file is not there yet, it first writes one with a double for every function (a condition returns `true`, an activity `null`). If the file lacks doubles, it asks first, then adds them; the rest of the file stays as it was.
- **Replay** opens the last recorded simulation of this Flow, without running PHP.

A modified Flow is simulated as it is in the editor. Its YAML is copied into the simulation's folder (a **snapshot**), and **your file is not saved or written**. Its unsaved changes stay unsaved.

![The Simulate Flow dialog for flows/fulfil.yml with Runner v0.3.0: the initial context as JSON, the doubles file in .div/simulations, 9 functions that need a double, all of them with one, and the warning that no Function of the project is loaded or called](images/flow-simulation-dialog.png)

## The doubles file

The doubles file is Runner's own `--simulate` file:

```json
{
    "description": "A small order: the stock short once, the invoice paused",
    "doubles": {
        "compute_total": {"returns": 25, "context": {"total": 25}},
        "needs_approval": {"returns": false},
        "stock_short": {"sequence": [{"returns": true}, {"returns": false}]},
        "billing:total": {"returns": 20},
        "invoice_sum": {"pause": true, "context": {"sum": 25}},
        "format_receipt": {"returns": "Receipt: 25"}
    },
    "budget": {"steps": 200, "transfers": 50, "seconds": 5}
}
```

A double's key is the reference as the Step writes it: `module:name` for a Step with a `module`, otherwise the name.

| Double | What it does |
|---|---|
| `{"returns": value}` | Returns `value`. A condition takes PHP's truth of it. |
| `{"throws": "message"}` | Throws: the Step fails. |
| `{"pause": true}` | Pauses the Flow at this Step. Activities only. |
| `{"sequence": [outcome, ...]}` | One outcome per call: the first call gets the first outcome. A call past the end fails. |
| `{"flow": "child.yml"}` | A nested YAML Flow is used as the activity, simulated with the same doubles. The path is relative to the project. |

Each double works like this:

- **Context.** An outcome may add `"context": {...}`, merged into the context as the function would.
- **Budget.** `budget` stops a Flow that loops: `steps` (10000 by default), `transfers` (calls and jumps, 10000) and `seconds` (10). divide stops PHP if it runs 20 seconds past that.
- **Trace options.** `trace` holds Runner's trace options (`max_events`, `redact_keys`...).

## The Simulation window

The window has the Flow's board as it was simulated. It is **read-only**: no key in it edits the Flow.

![The Simulation window at event 22 of 52: the JUMP from stock.short to stock.reserve, which goes on there and does not return; reserve visited, short current, the taken lines underlined and the legend of the marks](images/flow-simulation.png)

Over the board, each Step's card has a mark at the left of its title:

| Mark | The Step |
|---|---|
| **►** | current: the event under the cursor is this Step's |
| **√** | visited: it ran |
| **-** | skipped: its condition was false, or it was before the target of a call or jump |
| **»** | waiting for its `call`: the Block it called has not returned yet |
| **=** | paused: the Flow paused after it |
| **X** | failed: its function threw, or had no double |

The `call` and `jump` lines taken so far are **underlined**. A `call` is still a single line and a `jump` a double line, as in the Designer. The marks are characters, not colours, so they read the same in every theme, the phosphor ones included.

The panel on the right (under the board below 100 columns) shows:

- **SIMULATION**, the event's number and its segment, in reverse video;
- **the event**, with its Block.Step and what it says (see below);
- **the context's changes** in that event: `+` added, `~` changed (before -> after), `-` removed;
- **the logs** of that Step;
- **the calls** waiting to return, oldest first;
- **the selected card**: how many times it ran, and its state;
- **at the bottom**, how the simulation ended: done, paused (where), or the error. If the trace was cut, it says by how much. If the Flow or its doubles changed since the simulation, it says that too.

### Keys

| Key | What it does |
|---|---|
| **F7** / **Shift+F7** | The next / previous event |
| **F8** / **Shift+F8** | The next / previous Step (started or skipped) |
| **Ctrl+Home** / **Ctrl+End** | The first / last event |
| **F4**, or **Enter** on a card | The selected Step's next event (from the start again after its last) |
| **F** | Follow the current Step with the selection, or not |
| **X** | The context at the event, as JSON, in the Output window |
| **Ctrl+F2** | Back to the first event |
| **Ctrl+F9** | Resume a paused simulation; on an ended one, the Simulate Flow dialog |
| **arrows**, **Home / End**, **Tab**, **Backspace** | Move around the board and its connections, as in the [[Flow Designer]] |

Moving the cursor changes only what is shown. The events, the context, the YAML and every file stay as they were.

### The event

The event's details depend on its type:

- `run.start` and `run.end` give the state, the error and the checkpoint: Runner's exact `_flow_state` and `_flow_stack`.
- `block.enter` gives why the Block runs: the start, a resume, a call, a jump, a return.
- `step.skip` gives why the Step did not run.
- `condition` gives the function and its result, and what that result does to the Step.
- `activity.end` gives the result, kept under the Step's id.
- `activity.error` gives the error.
- `call` gives the target and says it **returns here when the Block ends**.
- `jump` gives the target and says it **goes on there, does not return**.
- `call.return` gives the Step it returns to, and whether that frame came from a checkpoint.
- `pause` gives the checkpoint.
- `double` gives which call of the double answered, and how.
- `function.missing` and `budget.exhausted` explain why the run failed.

Event types this divide does not know are shown with their fields.

## Pause and resume

When a simulation pauses, **Ctrl+F9** in its window resumes it. A **new PHP process** continues from Runner's simulation session: the simulated context, the double call counts (a `sequence` goes on where it was) and a fingerprint of the sources. The new segment is added to the same playback, after the first. A `call` that paused returns into its Step from the `_flow_stack` the checkpoint kept, and `call.return` says so.

![The last event of the first segment: run.end paused at invoice.sum, with Runner's exact _flow_state and _flow_stack, and the call to main.invoice waiting to return](images/flow-simulation-paused.png)

![After Ctrl+F9, segment 2 of 2: call.return from invoice to main.invoice, the frame came from the checkpoint, and the simulation done](images/flow-simulation-resumed.png)

A resume uses what the simulation started with:

- **The snapshot.** If the Flow or the doubles file changed since, divide asks first: Resume simulates the snapshot, not the changes. Shift+F9 starts a new simulation with them.
- **Nested Flows.** These are read from the project. If one changed, Runner refuses the resume (its fingerprint), and divide says so. Start a new simulation.

A simulation never touches a real run's checkpoint:

- Its session lives in `.div/simulation/`, never in `.div/runner/`.
- Runner refuses a file that is not a simulation session.

## Where it is kept

Each simulation has a folder in the project's `.div/simulation/`. divide makes that folder with a `.gitignore` that keeps it out of Git. A simulation's folder holds:

| File | What it is |
|---|---|
| `flow.yml` | the Flow's YAML as simulated (the snapshot) |
| `doubles.json`, `context.json` | the doubles and the initial context it started with |
| `session.json` | Runner's session, from which a pause resumes |
| `trace-1.json`, `trace-2.json`... | one trace per segment: what is replayed |
| `divide-session.json` | where it came from (the Flow, the doubles file) and how each segment ended |

divide keeps the newest 20 simulations, up to 64 MiB in all. Older ones are removed when a new one starts, except those open in a window. Only folders divide made are ever removed.

## Secrets and size

The trace is Runner's, with Runner's protections:

- values under keys that look secret (`password`, `token`, `api_key`, `card_number`...) are replaced by `{"$type": "redacted"}`;
- messages are left out unless you keep them;
- strings, lists and the whole trace have caps (4 MiB by default).

A trace that hit a cap says so: the window gives how many events were dropped or compacted. A context rebuilt from cut values says it is approximate. Runner's session file holds the whole simulated context, as a saved context always does. It stays in the project's ignored cache.

## How it works

For each segment, divide runs Runner's own command line in the project's folder:

```bash
php vendor/divengine/runner/bin/run.php --json --simulate doubles.json --session session.json \
    --trace trace-1.json [--context context.json] -- flow.yml
```

Runner's exit code tells how the segment ended: 0 done, 3 paused, 1 error, 2 not run. The trace (protocol `divengine.runner.trace`, version 1) has the events. divide reads only that version. It ignores fields and event types it does not know, as the protocol asks. A trace of another version is refused with a clear message.

A simulation is not a sandbox. Runner guarantees that the Flow's functions are not loaded or called, but the YAML is still compiled and run by PHP, and a doubles file can name nested Flows to compile. Flows and doubles are trusted inputs. Running and debugging real code is [[Running Flows]], [[Debugging PHP]], and Test Function in [[Flow Functions]].

## Limits

- **YAML only.** Runner simulates YAML Flows only. A nested Flow is simulated only through a `{"flow": "child.yml"}` double.
- **The board shows only the simulated Flow.** A nested Flow's events are in the playback and the panel names their scope, but its Steps are not on the board. While they run, the Step that runs the nested Flow is the current one.
- **Doubles are data, not PHP.** A condition double cannot pause.
- **Top-level changes.** Context changes compare top-level keys. A change inside a nested array shows the whole key, before and after.
- **No PHP stepping.** Simulation steps through the Flow's events, not PHP statements. For that, see [[Debugging PHP]] and Test Function.
- **One at a time.** One simulation runs at a time. A replay needs its folder: once the cache removes it, it cannot be replayed.
