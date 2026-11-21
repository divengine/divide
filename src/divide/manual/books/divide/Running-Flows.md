# Running Flows

divide runs, pauses and resumes the Flows of [Divengine Runner](https://github.com/divengine/runner), the engine of the Sequential Flow Model (SFM): a Flow of Blocks, each with its Steps, which `call` and `jump` to other Blocks and `pause`. **Runner runs them, not divide**: divide starts Runner's own command line from your project's Composer installation and shows what it says. Runner parses the YAML, runs the Steps, follows the calls and saves the context.

![Ctrl+F9 on a Flow: paused inside two calls, Runner's log and the context in the Output window](images/run-flow.png)

## What you need

- **PHP 8.1** or newer on the `PATH`.
- **Runner 0.2.0** or newer installed in the project with Composer:

  ```bash
  composer require divengine/runner
  ```

  divide runs `php vendor/divengine/runner/bin/run.php` (the folder of `config.vendor-dir` when composer.json moves it). Without it, Ctrl+F9 on a Flow says how to install it.

The repository's `examples/runner` is a project ready to try: `composer install` in it, open it in divide and press Ctrl+F9 on `flows/order.yml`.

## Run a Flow

A Flow is a YAML file (`.yml`, `.yaml`) whose root has `blocks`. In one, **Ctrl+F9** (Run > Run) opens **Run Flow**; in a PHP script the same key still runs the script, and in a template it renders it. **Run > Parameters...** opens the same dialog. A modified Flow is saved first.

![The Run Flow dialog, with a paused run saved: Enter resumes it](images/run-flow-dialog.png)

- **Initial context**: the context the Flow starts with (Runner's `--context`): a JSON file, or a JSON object typed in the field (`{"name": "Ana"}`). Empty: an empty context. It must be a JSON object; divide checks it before running.
- **Function root**: the folder of the activity and condition files (Runner's `--root`). Empty: the project's folder. Modules are folders in it (`<root>/billing/total.php` for `module: billing`), or the `_modules` of the context.
- **Save context to**: the file Runner writes the resulting context to (`--save-context`), by default one file per Flow in the project's `.div/runner/` folder (`flows/order.yml` saves to `.div/runner/flows/order.yml.context.json`). divide makes that folder, with a `.gitignore` that keeps the checkpoints out of Git. Any other file is yours to choose. Empty: nothing is saved, and a paused run cannot be resumed.
- Below, what that file holds now: nothing yet, a paused run (where it stopped), or the end of the last run.
- **Run** starts the Flow. **Resume** continues the paused run saved in the file; it is the default button (Enter) when there is one. **Browse...** chooses a file or folder for the field you were in.

The three fields are remembered per Flow. Relative paths are the project's: Runner runs in the project's folder, so the `_root_folder` and `_modules` of a context are taken from there too.

## While it runs

A progress box tells the Flow, the context, where it is saved and how much the Flow has printed. **Esc** stops it: PHP is killed.

When it ends, the box gives the verdict:

| Verdict | Means |
|---|---|
| **Done** | The Flow finished (Runner's exit code 0). |
| **Paused** | A Step paused it (exit code 3). It is not a failure: Resume continues it. |
| **Error** | A Step or the Flow failed (exit code 1): the error is in the report and in Messages. |
| **Not run** | Runner refused the invocation (exit code 2): a missing file, a context that is not a JSON object, an invalid option. The Flow did not run. |
| **Context not saved** | The Flow ran, but its context could not be saved or encoded as JSON (an object or a closure in it). The saved file is as it was. |
| **PHP ended** | PHP died before Runner could answer (`exit()`, a fatal error). Nothing was saved. |
| **Stopped** | You stopped it. Nothing was saved. |

## What you get

The **Output window** shows the report:

- **State**: `done`, `paused at approval.ask (inside 2 call(s))`, `error`... and, for a resumed run, `resumed, done`.
- **Result** and, after an error, **Error**: Runner's `_runner_result` and `_runner_error`.
- Where the context was saved, or why nothing was.
- **── log ──**: Runner's log of the run (each Step, call, return and pause).
- **── context ──**: the resulting context, as JSON (with `_flow_state` and `_flow_stack` when paused).
- **── stderr ──**: what the Flow printed and Runner's diagnostics. Runner's command line keeps them apart from the context.

The **Messages window** lists Runner's diagnostics (`runner: ...`) and PHP's warnings and errors, with their place when PHP gives one.

## Pause and resume

A paused run's position is in the saved context: `_flow_state` (the Block and Step where it stopped) and `_flow_stack` (the return frames of the calls it was inside). **Resume** runs the Flow again, in a new PHP process, with that file as its context and the same file to save to, as Runner's own resume does:

```bash
php vendor/divengine/runner/bin/run.php flows/order.yml --context .div/runner/flows/order.yml.context.json --save-context .div/runner/flows/order.yml.context.json
```

The run continues after the Step that paused and returns through every pending call; Steps that already ran are not run again. The Initial context field is not used on a resume.

divide keeps a paused run safe:

- **Resume needs a paused run.** When the file is missing, holds a finished run or is not a context of Runner's, Resume is off and says why. divide never starts the Flow over instead.
- **Starting over asks.** **Run** while the file holds a paused run asks first, and so does Run on a file you chose (outside `.div/runner/`) that already exists. A finished or failed run in divide's own checkpoint is replaced without asking. Either way, the file is replaced only when the new run ends.
- **A stopped run changes nothing.** Runner writes the context only when the run ends, replacing the file at once; a run you stop with Esc leaves the saved context as it was, so the paused run can still be resumed.
- **A context that cannot be saved is said**, and the file keeps the last good one.

## Limits

- Flows are trusted PHP code: activities and conditions run with your rights. Runner is not a sandbox, and neither is divide.
- divide runs a Flow from start to its end or pause: it does not step through Blocks and Steps, show the Flow as a diagram or edit it visually.
- YAML Flows only: a Flow written in PHP is a PHP script, and Ctrl+F9 runs it as one.
- One run at a time, and no scheduler, queue or job history: a run's report stays in the Output window until the next run.
- The context goes through JSON, as Runner's command line saves it: an empty object `{}` comes back as `[]`.
