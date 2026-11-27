# Use-Case Model

The use cases describe what divide, the IDE, does today: the tools for
developing and debugging generator projects. Running a deployed generator is
not a use case of divide. What the IDE may offer around orchestration and
generator interfaces is not decided (see the
[vision](vision.md#9-open-questions-not-decided)). The "template" of these
use cases is a generator's template, whatever it produces: source code,
configuration, data, HTML or another template.

## 1. Actors

| Actor | Kind | Description |
|---|---|---|
| **Developer** | primary, human | Builds generators: edits, checks, renders, traces and debugs templates, their data and the PHP around them, from the keyboard (or the mouse). |
| **Div engine** | secondary, system | The Div installation, reached through PHP and the bridge. It renders, resolves includes, decodes data, validates and loads dialects, traces and translates. |
| **PHP** | secondary, system | The `php` binary: `php -l` checks, scripts, `php -S`, and the host of Div. |
| **Xdebug** | secondary, system | Debugs PHP scripts and web requests over DBGp. |
| **Language server** | secondary, system | phpactor, intelephense...: completion, hover, definitions, diagnostics over LSP. |
| **Git** | secondary, system | The system's `git`: the project's file list for Go to file and Find in files, and every change of the Git menu (status, diff, commit, log, branches, merge, stash, blame, pull, push). |
| **Forge** | secondary, system | GitHub through `gh`, Gitea (Forgejo, Codeberg) through `tea`, signed in as the developer: pull requests and issues. |
| **Composer** | secondary, system | Adds, removes, updates and installs the project's PHP packages; Packagist is searched for new ones. |
| **Browser** | secondary, system | Shows the pages of the built-in web server. |
| **Runner** | secondary, system | Divengine's engine of the Sequential Flow Model, installed in the project with Composer and independent of divide: its command line (`vendor/divengine/runner/bin/run.php`) runs, resumes and simulates a project's YAML Flows, its compiler checks them and its importer resolves their Functions. |

## 2. Use-case diagram

```mermaid
flowchart LR
    Dev([Developer])
    Div([Div engine])
    PHP([PHP])
    XD([Xdebug])
    LS([Language server])
    Git([Git])
    Forge([Forge])
    Comp([Composer])
    Br([Browser])
    Run([Runner])
    subgraph divide
        UC1(UC1 Open and navigate a project)
        UC2(UC2 Edit a Div template)
        UC3(UC3 Check a template)
        UC4(UC4 Render a template)
        UC5(UC5 Trace a render)
        UC6(UC6 Edit template data)
        UC7(UC7 Build a dialect)
        UC8(UC8 Translate a template)
        UC9(UC9 Edit PHP)
        UC9b(UC9b Edit the other files of a project)
        UC10(UC10 Run a PHP script)
        UC11(UC11 Debug PHP)
        UC12(UC12 Serve the project on the web)
        UC13(UC13 Find files, text and commands)
        UC14(UC14 Read the help)
        UC15(UC15 Configure divide)
        UC16(UC16 Work with git)
        UC17(UC17 Pull requests and issues)
        UC18(UC18 Manage Composer packages)
        UC19(UC19 Set up Div for a project)
        UC20(UC20 Run and resume a Runner Flow)
        UC21(UC21 Design a Runner Flow)
        UC22(UC22 Test a Runner Function)
        UC23(UC23 Simulate a Runner Flow)
        UC24(UC24 Mock-simulate a Runner Function)
    end
    Dev --- UC1 & UC2 & UC3 & UC4 & UC5 & UC6 & UC7 & UC8 & UC9 & UC10 & UC11 & UC12 & UC13 & UC14 & UC15 & UC16 & UC17 & UC18 & UC19
    Dev --- UC9b & UC20 & UC21 & UC22 & UC23 & UC24
    UC3 --- Div
    UC4 --- Div
    UC5 --- Div
    UC7 --- Div
    UC8 --- Div
    UC4 --- PHP
    UC9 --- PHP
    UC9 --- LS
    UC10 --- PHP
    UC11 --- XD
    UC12 --- PHP
    UC12 --- XD
    UC13 --- Git
    UC16 --- Git
    UC17 --- Forge
    UC18 --- Comp
    UC19 --- Div
    UC12 --- Br
    UC20 --- Run
    UC20 --- PHP
    UC21 --- Run
    UC22 --- Run
    UC22 --- PHP
    UC22 --- XD
    UC23 --- Run
    UC24 --- PHP
    UC24 --- XD
```

## 3. Use-case specifications

Each specification gives the main flow and the main alternatives. The keys
and screens are described in the [manual](https://github.com/divengine/divide/wiki).
This document describes behaviour and responsibilities.

A key acts in the window that has the focus, so the same key can do different
things in different windows. Ctrl+T turns a data file into its tree (UC6) and a
Runner Flow into its Flow window (UC21); F7 makes a folder in the project window
(UC1), traces a render in a template (UC5) and traces into the code in the
debugger (UC11). Each specification says the window its keys belong to.

### UC1 Open and navigate a project

**Goal:** work on the files of one folder, or on a file alone.
**Trigger:** `divide [folder] [files...]`.
1. A folder is opened only when it is given (`divide .`, `divide ~/site`), as VS Code does: it becomes the project, and divide opens the given files in editor windows, or the project window if no file is given. Files alone (`divide page.tpl`) open with no folder. With nothing, divide shows the **Welcome window**: start (a new file, open a file, open a folder, the help) and the recent folders and files, newest first.
2. File > Open folder makes another folder the project: the windows of the last one close, asking about unsaved changes. File > Close folder goes back to no folder and the Welcome window (Help > Welcome shows it again).
3. The developer opens files from the project window (Enter or a double click), File > Open (F3, with the name history) or Go to file (UC13).
4. Windows are moved, resized, zoomed (F5), tiled, cascaded, cycled (F6) and closed (Alt+F3). Unsaved changes are asked about before closing or quitting.
- *Alt:* the project window creates, renames, deletes, cuts, copies, pastes and moves files and folders (Ins, F7, F2, Del, Ctrl+X, Ctrl+C, Ctrl+V, a drag, local menu), and unfolds a file into its members (its outline).
- *Alt:* with no folder, Ctrl+B, Find in files and the project's Div setup offer to open one.
- *Alt:* Del on a recent folder or file of the Welcome window takes it off its list.

### UC2 Edit a Div template

**Goal:** write a template with Div's structure visible.
1. The editor highlights the template with the lexer built from its dialect (`@_DIALECT`, resolved like Div does).
2. As the developer types, completion offers variables from the data file, loop item fields, includes and snippets (Ctrl+Space).
3. Ctrl+Enter opens the included template under the cursor, as resolved by Div.
4. Search > Outline lists the template's constructs, nested, and follows the edits.
- *Alt:* an unknown dialect keeps the default tags and says so in the status line.

### UC3 Check a template

**Goal:** see errors before rendering.
1. While the developer types, the static checker reports unclosed or orphan blocks, conditions without a closer, broken JSON in definitions, and tags Div would leave as text.
2. Includes are resolved by Div in the background, and the unresolvable ones are reported.
3. Alt+F9 runs the check under the progress box. The Messages window lists the results and Alt+F8 / Alt+F7 walk through them.

### UC4 Render a template

**Goal:** see the output Div produces from a template and its data.
1. Ctrl+F9 sends the editor's text (unsaved edits included), its real path and its data file to the bridge.
2. Div renders it. The Output window shows the result next to the code, and warnings and fatal errors go to the Messages window.
- *Alt:* no engine is found, so divide asks for one (Options > Div engine).
- *Alt:* Esc in the progress box stops the render.

### UC5 Trace a render

**Goal:** understand how the output came to be.
1. Debug > Render trace (F7 in a template) asks the bridge for a traced render.
2. The trace window lists Div's mutations in order. Each one shows the template before and after, and where in the source it happened.

### UC6 Edit template data

**Goal:** prepare the data a template is rendered with.
1. The data file opens as Div JSON, highlighted and validated.
2. Ctrl+T switches to a tree editor over the same buffer. Its edits are text edits, so undo, save and the dirty flag work as usual.
- *Alt:* Run > Data file chooses another data file for the template.

### UC7 Build a dialect

**Goal:** a valid `.dialect` file.
1. Tools > Dialector shows the dialect's tags by section, each with an example rendered in that dialect.
2. Each change is validated by Div (`isValidCurrentDialect`) and the verdict is shown.
3. The dialect can be imported from PHP `define()`s, checked against an example and saved.

### UC8 Translate a template

**Goal:** move a template from one dialect to another.
1. Tools > Translate asks for the template, the source dialect and the target dialect.
2. Div's `translate()` produces the result, which is previewed and then saved or opened.

### UC9 Edit PHP

**Goal:** write the PHP around the templates.
1. tree-sitter's PHP grammar highlights the file. `php -l` checks it as the developer types.
2. A language server, if one is installed, adds completion, signatures, hover (Ctrl+F1), definitions (Ctrl+click) and its own diagnostics.
3. The outline lists namespaces, classes, members and functions.

### UC9b Edit the other files of a project

**Goal:** read and edit the other files a generator uses or produces, besides its templates and its PHP.
1. HTML, CSS, JavaScript, Markdown, SQL, XML (also `phpunit.xml.dist`, SVG), YAML, TOML, shell scripts and `.env`, INI (`php.ini`) and CSV files open highlighted in the palette's colours; the status line names the language.
- *Alt:* a grammar package is missing, so the file opens as plain text.

### UC10 Run a PHP script

**Goal:** run a PHP script of the project and see what it prints.
1. Ctrl+F9 runs the script with its parameters (Run > Parameters) under the progress box.
2. Its output goes to the Output window and PHP's errors to the Messages window, located.
- *Alt:* Run in terminal runs it outside divide, for interactive scripts.

### UC11 Debug PHP

**Goal:** follow a PHP script line by line and look at its state.
1. With Xdebug available, F7 / F8 / F4 start the script under the debugger. Ctrl+F8 toggles breakpoints.
2. When the script pauses, the current line is shown, along with Watches, the Call stack and Evaluate (Ctrl+F4).
3. F7 traces into, F8 steps over, Shift+F8 steps out, Ctrl+F9 goes on and Ctrl+F2 resets.

### UC12 Serve the project on the web

**Goal:** try the project's pages in a browser, and debug their requests.
1. Run > Web server starts `php -S` on the project, with a router if one is given. Its log goes to a window.
2. With Xdebug, each request pauses at the first breakpoint and is debugged as in UC11 while the browser waits.

### UC13 Find files, text and commands

**Goal:** reach any file, line of text or command quickly.
1. **Go to file** (Ctrl+P): the developer types a few letters and the project's files are matched fuzzily. Enter opens the chosen file.
2. **Command palette** (Alt+P, or `>` in Go to file): every menu entry is matched the same way. Enter runs it.
3. **Find / Replace** (Ctrl+F / Ctrl+R) work in the current file. **Find in files** (Shift+F2) searches every project file, or those matching a mask, and lists the matching lines. Enter opens each one with the match selected.

### UC14 Read the help

**Goal:** learn divide and Div without leaving the editor.
1. F1 opens the topic for the active window. Contents, Index and Topic search browse the books (divide, Div).
2. Links between topics are followed with Enter, Alt+F1 goes back, and web links open in the browser.
3. **Help > Search** finds sections of every book by words, ranked. As the developer types, the matching sections are listed best first, each with the sentence where the words are. Enter opens the help at that section.
- *Alt:* Ctrl+F1 on a word that names no topic opens Help > Search with that word.
- *Alt:* the shipped index does not match the books (copied by hand), so it is rebuilt in memory on the first search.

### UC15 Configure divide

**Goal:** set divide's look and the external tools it uses.
1. Options > Colors chooses the theme, previewed live, and the colour depth.
2. Options > Language servers, Div engine and Xdebug set the external tools. Options > File type marks changes the project tree.
3. Settings, histories and choices are kept in `config.json` (see [deployment.md](deployment.md)).

### UC16 Work with git

**Goal:** see, review and record the project's changes without leaving the editor.
1. In a git repository, the project window puts git's letter after each changed file and `•` after the folders holding changes, and dims what `.gitignore` leaves out; the editor's margin marks the lines added, changed or removed since the last commit, as the developer types.
2. Git > Changes lists the files in their areas (conflicts, staged, changes, untracked) with the focused one's diff. Space stages or unstages, Del discards, Ctrl+K commits (amend, stage everything first).
3. Git > History shows every branch as a graph and each commit's details and diff; File history, the commits of one file; Blame, each line with the commit that last changed it.
4. Git > Branches switches, creates, deletes and merges into the current branch, and brings back or applies the stashes. Pull, push and fetch run under the progress box with git's own words.
- *Alt:* a merge stops on conflicts: Git > Changes shows git's markers, our side and theirs, and Space marks a file solved.
- *Alt:* a remote needs a password or a passphrase: git cannot ask (there is no terminal for it), so it fails and says so.

### UC17 Pull requests and issues

**Goal:** work with the forge's pull requests and issues of the project.
1. Git > Pull requests and issues lists the open ones of the remote's repository (`origin`, else the first), with the one under the bar beside them.
2. Ins makes a new pull request of the current branch (pushed first if needed) or a new issue; Alt+F10 checks out a pull request, merges it on the forge or copies its address; Enter opens it in the browser.
- *Alt:* `gh` or `tea` is missing or not signed in: the window says what to install or run.

### UC18 Manage Composer packages

**Goal:** manage the project's PHP dependencies.
1. Tools > Composer packages lists what `composer.json` requires, the development packages, the dependencies installed with them and the platform, with the installed versions.
2. Ins adds a package (Packagist searched as the developer types, the newest stable version suggested), Del removes one, and update and install run Composer under the progress box, its output in the Composer window.
- *Alt:* no `composer.json`: a wizard writes one, as `composer init` would.

### UC19 Set up Div for a project

**Goal:** describe the Div that divide runs while the developer designs.
1. Options > Div setup edits `.div/setup.json` of the project (or the user's `~/.div/setup.json`) section by section: the engine, paths, file extensions, parser limits, dialect, data (globals, defaults, system variables), PHP functions and modifiers, the request's superglobals. The bridge applies it to every request, so renders, checks and completion see Div set up as the developer describes it. It is divide's design-time setup: the application's own runtime configuration of Div is its code's, and divide neither reads nor changes it.
2. Beside each section, what is in effect and where it comes from (the project, the user, Div's default); Div checks the saved setup and gives its verdict.
- *Alt:* a project's `php` section lets templates call PHP functions, so it is applied only once the developer trusts it (`~/.div/trust.json` keeps its hash; a change asks again).

### UC20 Run and resume a Runner Flow

**Goal:** run a generator's Flow as Runner runs it, and continue it after a pause.
**Trigger:** Ctrl+F9 on a Runner Flow (YAML), in its code, its Flow window or its board.
1. The Run Flow dialog takes the initial context (a JSON file, or a JSON object typed there), the function root and the file the resulting context is saved to. The three are remembered per Flow; by default the context is saved to one file per Flow under `.div/runner/`, kept out of Git.
2. Runner's own command line (`vendor/divengine/runner/bin/run.php`, 0.2.0 or newer, from the project's Composer installation) runs the Flow in a PHP process. Its Functions run for real, with their side effects.
3. The run ends done, paused, with an error, stopped or not run. The Output window shows Runner's log and the resulting context; the Messages window lists Runner's diagnostics and PHP's errors.
4. **Resume** continues a paused run from the saved context (`_flow_state`, `_flow_stack`) in a new PHP process; the Steps that already ran are not run again.
- *Alt:* **Run** while the file holds a paused run asks before starting over.
- *Alt:* Esc stops the run and leaves the saved context as it was.

### UC21 Design a Runner Flow

**Goal:** shape a Flow's Blocks, Steps and connections, and its Functions, without hand-writing YAML; the YAML file stays the Flow.
1. Ctrl+T on a Flow opens the Flow window: a tree of Blocks and Steps beside the selected one's attributes, where its `call` and `jump` lead and which function file it uses. Enter edits a Step, Ins adds one, Del deletes one.
2. Run > Flow designer draws the Flow as a board: Blocks as columns, Steps as cards, every `call` and `jump` as a line. The arrows move, C / J connect by choosing the target on the board, B / Ins add a Block or a Step, Enter edits, Ctrl+arrows reorder and Del deletes with the references that lead to it.
3. Each change is one in-place edit of the YAML (comments, key order and formatting kept, verified by reading the Flow back), undone with one Ctrl+Z.
4. Runner's compiler checks the Flow without running it: unknown keys, wrong types, missing targets and missing function files show in the tree or on the board, under the code and in the Messages window.
5. The Functions window (F on the board, Run > Flow functions) lists the function root, its Modules and Functions and the Steps that use each. Ins makes a Function and Shift+Ins a Module from a template, never over an existing file; Enter opens a Function in the PHP editor (UC9).
- *Alt:* an edit that would remove a comment is refused, and points to the code.
- *Alt:* while the YAML is invalid, the board keeps the last design, read-only.

### UC22 Test a Runner Function

**Goal:** call one Function alone, as Runner would, and see what it does.
**Trigger:** T on a Step in the Flow Designer, Ctrl+F9 on a Function in the Functions window, or Function... > Test... in the Step dialog.
1. Runner's own importer resolves the Function with the Flow's function root, its Module folders and `.div/runner.json`: the same file a run of the Flow would load.
2. The developer gives a JSON context and, optionally, an expected return and the keys the context must hold. **Save** keeps the input as a scenario in `.div/function-tests/`.
3. divide calls `$func($context)` in a PHP process, with the context by reference and `_importer` in it, under a time and a memory limit. The Function runs for real, with its real dependencies; no Flow or Step runs.
4. The report goes to the Output window: how the call ended, the expectations, the returned value and its type, the context's changes, stdout and stderr. An error's place goes to the Messages window.
- *Alt:* **Debug** makes the same call under the Xdebug debugger, debugged as in UC11; the report follows when it ends.

### UC23 Simulate a Runner Flow

**Goal:** see the path a Flow takes for given answers, without running its Functions.
**Trigger:** Shift+F9 in a Flow's code, its Flow window or its board; Run > Simulate Flow with doubles; S on the board.
1. The developer gives an initial context and a doubles file in Runner's `--simulate` format (by default `.div/simulations/<flow>.doubles.json`, a file the team can share). A double returns a value, throws, pauses, follows a sequence or runs a nested Flow.
2. Before anything runs, divide lists the Functions that still need a double and refuses an incomplete or malformed file; **Edit doubles** writes the missing ones.
3. Runner (0.3 or newer) simulates the Flow: every `condition` and `activity` is answered by its double, and no Function of the project is loaded or called.
4. The Simulation window replays Runner's trace on the Flow's board, event by event, forwards and backwards, marking each Step current, visited, skipped, waiting for its `call`, paused or failed.
- *Alt:* a paused simulation resumes with Ctrl+F9 in a new PHP process, from Runner's simulation session in `.div/simulation/`, and the playback goes on. A real run's checkpoint in `.div/runner/` is never touched.
- *Alt:* **Replay** reopens the last simulation without running PHP.
- *Alt:* a modified Flow is simulated as it is in the editor, from a copy of its YAML; the file is not written.

### UC24 Mock-simulate a Runner Function

**Goal:** run one Function's real PHP with its declared dependencies replaced, and replay its lines in its code.
**Trigger:** Shift+T on a Step in the Flow Designer, Function... > Simulate... in the Step dialog, Alt+F10 > Simulate... in the Functions window, or Run > Mock Simulation of a Function.
1. The dialog holds a scenario: the context, the doubles (`importer` for other Functions, `services` for objects under context keys, each a `returns`, `throws` or `sequence` outcome), optional expectations, limits (lines, seconds, output bytes) and options (the line trace, the pin, a tripwire, Composer autoload). **Save** keeps it in `.div/function-simulations/`.
2. A static scan of the Function's file, which runs nothing, fills in a double for each dependency it finds, answering `null`. Before such a placeholder is used, the developer keeps `null` or goes back to give it a value.
3. A scenario is refused, and nothing runs, when a field is not valid JSON, an outcome is malformed, a limit is out of range or a dependency the file uses has no double. A new scenario is pinned to the SHA-256 of the Function's file; once the file changes, the scenario is stale and runs only after the developer re-pins it.
4. The first Mock Simulation in a project asks to be allowed, after saying what it runs.
5. The Function's **real PHP** runs, in a PHP process of its own; only its declared dependencies are doubles. PHP's own functions, the file's top-level code and, if chosen, the project's Composer classes run for real: it is not a sandbox and not side-effect-free.
6. With Xdebug, in a session of its own, every PHP line it runs is recorded and replayed in the Function's file, read-only: F7 / F8 move a cursor, beside the locals, the context, the doubles' calls and the result. Nothing runs again.
- *Alt:* without Xdebug, divide asks whether to simulate without the line trace: the result comes back, with no lines.
- *Alt:* **Replay** reopens the last traced run without running PHP.

Unlike UC23, no Flow is simulated and the Function's own code runs; unlike UC22, its dependencies are doubles.
