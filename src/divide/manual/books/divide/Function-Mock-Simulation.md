# Function Mock Simulation

A **Mock Simulation** runs one [Runner](https://github.com/divengine/runner) Function with a context you give and with **doubles** for the dependencies it declares. divide records each PHP line the Function runs, and you replay the run line by line in the Function's own code: the line about to run, its local variables, the context so far, what the doubles answered, what it printed and how it ended.

> **MOCK SIMULATION: real PHP runs; only declared dependencies are replaced.** The Function's own PHP code runs for real, in a PHP process of its own. Only what it asks its context for is replaced: other Functions (`$context['_importer']`), Runner's logger (`$context['_logger']`) and service objects under context keys. PHP's own functions (files, databases, `curl`, `mail`, `time()`), the file's top-level code and, if you opt in, the project's Composer classes run for real. **It is not a sandbox and not side-effect-free.** Simulate only code you trust.

It is not the [[Flow Simulation]]. Each way divide runs a Function does something different:

| | What runs | What you get |
|---|---|---|
| **Run** a Flow (Ctrl+F9, [[Running Flows]]) | the Flow and its Functions, for real | the context after it |
| **Test Function** (T, Ctrl+F9 in [[Flow Functions]]) | one Function, for real, with its real dependencies | its report in Output |
| **Debug** (Test Function > Debug, [[Debugging PHP]]) | the same call, for real, under the debugger | breakpoints, F7 / F8, watches |
| **Flow Simulation** (Shift+F9) | Runner's simulation of the Flow: **no Function code runs** | the Flow's events on its board |
| **Mock Simulation** (Shift+T) | one Function's **real PHP**, its declared dependencies doubled | its PHP lines, replayed in its code |

A Mock Simulation never reads or writes a Flow's saved context (`.div/runner/`) or a Flow simulation (`.div/simulation/`), and the Flow board never shows PHP lines.

## What you need

- **PHP 8.1** or newer on the `PATH`.
- **Xdebug**, for the line trace. Without it, divide asks whether to simulate without the line trace: you then get the result (the return, the context, the doubles' calls, the output), and no lines. The PHP runs for real either way. Xdebug is found as for [[Debugging PHP]]: in PHP's own `php.ini`, or `xdebug.so` given in **Options > Xdebug…**.
- A Function **written for injection**: one that takes what it depends on from its context. A Function that opens files, makes `new` services or calls static methods itself runs those parts for real, and the simulation cannot show what it did not replace.

Runner itself is not needed: the Function is called by divide's harness, not by Runner.

## Open it

Choose a Function in any of these ways:

- **Shift+T** on a Step of the [[Flow Designer]]: its activity, else its condition (**T** stays Test Function);
- **Function... > Simulate...** in the Step dialog;
- **Alt+F10 > Simulate...** in the [[Flow Functions]] window, on a Function (**Ctrl+F9** there stays Test Function);
- **Run > Mock Simulation of a Function**: the Function under the cursor in the Functions window, or the PHP file you are editing when it is one of the project's Functions.

The Function is the one a run of the Flow would load: the Flow's function root and Module folders (see [[Flow Functions]]).

Unsaved PHP files are saved first: PHP runs what is on disk.

## The dialog

The **Mock Simulation** dialog holds a scenario. Its banner always says that real PHP runs, that it is not a sandbox and that it is not a Flow simulation.

- **The first line**: the Function's file and its **pin** (below).
- **Scenario**: a name. **Save** writes the scenario in the project, in `.div/function-simulations/<module>/<name>.<scenario>.json` (`_root` for a Function with no Module), for the team in Git. **Down** offers the saved ones, and choosing one fills the dialog. Your own settings remember only the options and the name of the scenario last used for each Function, and only after the project's opt-in: never its context or its doubles, which stay in the scenario's file.
- **Context**: a JSON object, the context the Function gets, by reference. Keys starting with `_` belong to Runner and are refused.
- **Doubles**: a JSON object with `importer` (other Functions, by `module:name` or `name`) and `services` (an object per context key, one outcome per method). Each outcome is one of Runner's `--simulate` outcomes: `returns`, `throws` (a message) or `sequence` (one outcome per call), with an optional `context` merged into the context.
- **Expected return** and **Expected context keys**: optional checks, as for Test Function (the context keys are a subset the context after must hold).
- **Lines**, **Seconds**, **Output bytes**: the limits. Past the lines, the trace stops and says so; past the seconds, PHP is ended; past the output bytes, what the Function prints is cut.
- **Trace the PHP lines (Xdebug)**: on by default.
- **Pin to the file's version**: on for a new scenario (below).
- **Tripwire (not a sandbox)**: PHP's process, network and mail functions and the commonest file writes are disabled, and files outside the project are fenced off. It stops some direct side effects; others (`fopen`, PDO, static state) still happen.
- **Composer autoload (real classes)**: off by default. Without it, a class the Function needs is an error that names it, never a silent real dependency. With it, those classes are real code.
- **Edit...** opens the whole scenario as a tree or as JSON, the editor of a Step's context.

**The doubles are filled in for you.** divide reads the Function's file (it does not run it) and finds what it asks its context for: `$context['_importer']('name', 'module')` and `$context['key']->method(`, also through a variable they were assigned to. Each one it finds gets a placeholder that answers `null`, and the line under the fields names the placeholders until you change them. **Simulate** and **Save** ask before a placeholder answers `null`: **Keep null** when `null` is the answer you mean (it is a valid one), or **Back** to give it a value. A `null` in a saved scenario is what was saved, and is not asked about again. An import whose name is computed when it runs cannot be known: the line says where it is.

`unknown` is always `fail`: **a dependency with no double is never the real one**. The simulation throws when the Function asks for it.

### A scenario is refused before anything runs

**Simulate** runs nothing, and the dialog stays open with the reason, when:

- the context, the doubles or an expectation is not JSON;
- an outcome is not one of `returns`, `throws` or `sequence`, or has two of them;
- a limit is out of its range (lines up to 100,000, seconds up to 300, output up to 4 MiB);
- **a dependency the file uses has no double**.

### The pin

A scenario is **pinned** when it holds the sha256 of the Function's file. Then the simulation checks the file before calling the Function: a file that changed since is **stale**, and nothing runs.

- A new scenario is pinned to the file as it is now. Untick **Pin to the file's version** to take the pin out: the scenario then runs whatever the file is.
- A scenario without the pin is never shown as pinned: the dialog says **NOT pinned to a source version**, and so do the playback and the saved trace (`"pinned": false`).
- **A stale scenario is re-pinned only when you say so.** The dialog says **STALE** and shows **Re-pin**. Simulating it says that the file changed and asks: **Re-pin and simulate**, or **Cancel**. A saved scenario changes only when you **Save** it.

A pin says that the file is the one the scenario was written for. It says nothing about safety: a pinned Mock Simulation still runs real PHP.

### The first time in a project

The first Mock Simulation in a project asks you to allow it, after saying what it runs. Your answer is kept in your own settings, not in the project.

## Simulate

**Simulate** (Enter) runs the Function once, in a box that **Esc** stops (PHP is ended). With the line trace, divide steps through the Function with its own Xdebug session, separate from the debugger and from your breakpoints; it records only the Function's own file.

The run is kept in `.div/function-simulation/` (out of Git: divide writes its `.gitignore`), with the scenario it ran. Like Flow simulations, the last 20 runs are kept, up to 64 MiB. **Replay**, in the dialog, opens the last one of the Function without running PHP.

## The playback

The **Mock Simulation** window opens at the first line. The Function's file is on the left, read-only, with the line about to run marked. On the right (below, in a narrow window):

- **MOCK SIMULATION**, the line and the event, the warning, and the pin;
- the line's **depth** (above 0 inside a closure the Function defines) and how many more statements on the same line ran without changing a variable;
- **Changed by the lines before**: what the lines before it set;
- **Changed by a double this line calls**: what a double changed while the line ran;
- **Locals** and **Context so far**: the state **before** the line runs;
- **Double calls**, **Logger** and **Output**: what the doubles answered, in order, what was logged and what the Function printed;
- the result: what it returned and its type, or the exception or error with its place (a missing double says so), and each expectation, `[OK]` or `[!!]`.

Moving only moves a cursor: **nothing runs again**, and no file changes.

| Key | Action |
|---|---|
| **F7** / **Shift+F7** | next / previous line |
| **F8** / **Shift+F8** | next / previous line at the same depth (over a closure's lines) |
| **F4** | the next time the line under the cursor ran |
| **Ctrl+Home** / **Ctrl+End** | first / last line |
| **X** | the whole context before the line, in the Output window |
| **S** | Save as scenario |

What is shown follows how Xdebug steps:

- A line's variables are those **before** it runs.
- A branch that was not taken has no line.
- A `foreach` header shows on its first pass only.
- Values are bounded: strings over 4 KiB are cut, arrays over 1,000 items are truncated, nesting stops at depth 16; the panel says which were cut.

If the Function's file changed since the run, its lines are not marked: the panel says so.

### Save as scenario

**S** saves the scenario that ran, under a name, in `.div/function-simulations/`. **Expect this run's return and context changes** adds them as its expectations, to check later runs against. Its pin is the run's: an unpinned run is saved unpinned.

## Limits

- A double replaces only what the Function asks its context for. Nothing intercepts PHP's own functions on a standard PHP.
- `time()`, `rand()` and `uniqid()` are not controlled.
- A Function that drives the Flow (`_flow_state`, `_update_context`) belongs to the [[Flow Simulation]].
- The trace runs at about 2,000 lines a second.
