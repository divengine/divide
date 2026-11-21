# divide

**An IDE for developing generators with the Divengine ecosystem.**

divide is a specialised development environment for building, testing,
debugging and maintaining generators that use the
[Divengine](https://github.com/divengine) libraries. A generator is a project
of its own that transforms input models into source code, configuration,
templates or other artifacts through explicit, reusable rules, for example
with [Div](https://github.com/divengine/div) templates and their data.
divide is where you develop it; the finished generator is deployed and runs
without divide.

You can write the same software in VS Code, a JetBrains IDE or Neovim, and
divide does not compete with them on general programming. What it adds is
knowledge of the ecosystem: Div-aware editing in each template's dialect,
the project's design-time Div setup, rendering and checking through the real
engine, and the render trace of how Div reached its output. Deterministic
code generation is a central use case; [below](#generators-and-what-is-not-decided)
is what that means and what is still open.

The interface is keyboard first, in the spirit of the Borland IDEs:
overlapping windows, drop-down menus, dialogs with shadows and a status line
that always tells you the next key. It understands Div the way Div does: it
reads each template's dialect, checks templates as you type, completes
variables from your real data, and renders through the real Div engine, side
by side with the code. Its name is *div* + *ide*, and the English word
*divide*.

![divide in under a minute: completion from the data, errors before rendering, a render with Div, the render trace, the data tree, the outline and the dialector](https://raw.githubusercontent.com/wiki/divengine/divide/images/tour.gif)

## What it does today

The examples below generate HTML because it is the easiest output to read; the same tools work for templates that generate code or any other text.


- **Speaks Div.** Every construct of the language is highlighted, in the
  template's own dialect (`@_DIALECT`).
- **Errors before you render.** Unclosed loops, orphan `[/$x]`, conditions
  without `{/?}`, tags Div would leave as text, broken JSON in `{= x: … =}`,
  includes Div cannot resolve. They are painted in the editor and listed in a
  Turbo Pascal–style Messages window, and Alt+F8 walks through them.
- **Completion from your data.** `{$` offers the keys of `page.json`. Inside
  `[$products]` you get a product's fields, the item name and Div's `_index`,
  `_is_last`… `[$` closes the loop for you, `{% ` lists your templates, and
  Ctrl+Space offers every Div construct as a snippet.
- **The real engine.** Ctrl+F9 renders through PHP and Div, unsaved edits
  included. Includes are resolved by Div's own `getTplPath()` and data is
  decoded by Div's own `jsonDecode()`. Ctrl+Enter opens the template an
  include points to.
- **Data as code or as a tree.** Div JSON (references, comments, single
  quotes) is highlighted and validated, and Ctrl+T edits the same buffer as a
  tree.
- **Your own dialects.** Tools > Dialector builds a Div dialect section by
  section, with a live preview and Div's verdict on every change: Div's
  `isValidCurrentDialect()` validates it and Div's translator reads it back.
  It can import and export dialects, and a wizard translates templates from
  one dialect to another with Div's own `translate()`.
- **PHP next to the templates.** `.php` files are highlighted with
  tree-sitter's PHP grammar and checked by PHP itself (`php -l`) as you type.
  Ctrl+Enter on `new div('page.tpl')` opens the template.
- **Outline.** Search > Outline (Ctrl+O) shows the shape of the file as a tree:
  a template's loops, conditions, includes and capsules; a PHP file's classes
  with their methods and properties; and the parts of HTML, Markdown, CSS,
  JavaScript, SQL, JSON, YAML... Enter goes to one. The project window unfolds
  each file into the same members, without opening it.
- **Render trace.** Debug > Render trace (F7 in a template) replays how Div mutated the template
  into its output: every change, in Div's own words, with what it wrote and
  took away, sub-parses and fixed points; F7 / F8 step through them.
- **Run and debug PHP.** Ctrl+F9 runs the script under a Turbo Pascal–style
  progress box (renders and checks get it too); its output goes to the Output
  window and PHP's errors to the Messages window, with their place. With
  Xdebug, F7 / F8 step through the code with breakpoints, watches, evaluate
  and the call stack. Run > Web server serves the project with `php -S`, and
  its requests stop at the same breakpoints.
- **Language servers.** With phpactor or intelephense (in the project or the
  PATH), PHP gets completion (with the classes of `vendor/`, like Div's, and
  their `use` lines added for you, and the documentation of each item),
  the signature of the call you type, hover (Ctrl+F1), go to definition
  (Ctrl+Enter) and the server's diagnostics. divide is a generic LSP client (pygls), so
  other languages are one entry away.
- **Div set up for design time.** `.div/setup.json` (and your own
  `~/.div/setup.json`) tells divide how to set up the Div it runs while you
  work: template folders, extensions, dialect, globals, defaults, PHP
  functions and a simulated request. Every render, check and include in
  divide goes through it, and Options > Div setup edits it section by
  section, with Div's verdict. It does not configure the Div your
  application runs in production, which keeps its own setup in its code.
- **Composer without leaving it.** Tools > Composer packages lists what the
  project requires and what is installed, adds packages with an assistant
  (Packagist searched as you type, the version suggested), removes, updates,
  installs and finds newer versions, all run by composer itself; a project
  without `composer.json` gets one, with Div in it.
- **Version control.** The Git menu shows what changed (in the project
  window, the editor's margin and Git > Changes), diffs as a code review shows
  them, commits, history, branches, merges, stashes and blame, and the pull
  requests and issues of GitHub or Gitea.
- **Runner Flows.** Ctrl+F9 on a [Runner](https://github.com/divengine/runner)
  Flow runs it with Runner's own command line: an initial context, the state
  it ended in (done, paused, error), Runner's log and the resulting context.
  A paused run is saved and resumed from its context
  ([Running Flows](https://github.com/divengine/divide/wiki/Running-Flows)).
  Ctrl+T shows its Blocks and Steps as a tree you edit with the keyboard: only
  what you change is written in the YAML, Runner's own compiler checks it, and
  missing targets and function files are marked
  ([Flow Structure](https://github.com/divengine/divide/wiki/Flow-Structure)).
- **An MCP server for agents.** Options > MCP server starts it on
  `http://127.0.0.1:8765/mcp`: an AI coding agent gets the same checks,
  renders and render trace through the real Div engine, with the project's
  Div setup. `divide --mcp PROJECT` serves it over stdio too. Nothing to
  install beyond divide ([MCP Server](https://github.com/divengine/divide/wiki/MCP-Server)).
- **A project window that does things.** You can create, rename and delete
  files and folders without leaving the IDE, and what git, Composer or a
  shell changes outside it shows by itself (the system's own file
  notifications, nothing polled).
- **Works in any terminal.** It runs over SSH, inside tmux, and on the server
  where the templates live.

## Generators and what is not decided

divide is the IDE, not the generator, and not where generators run in
production. A generator project may use Div, Nodes, Ways, PHP or anything
else it needs, and may implement its own orchestration of stages, CLI
commands, an HTTP API or an MCP server; tools and AI coding agents then use
the deployed generator through those interfaces. divide's PHP development
server can help while developing an HTTP generator, but it is not a
generator API or an MCP platform.

divide has an MCP server of its own, for developing: Options > MCP server
(HTTP, started and stopped in the IDE) or `divide --mcp PROJECT` (stdio) lets
an AI coding agent use the IDE's design-time services on the open project
(the Div setup, the editor's checks, renders and the render trace through the
real Div engine). It is not a generator's MCP and does not see divide's open
editors. See [MCP Server](https://github.com/divengine/divide/wiki/MCP-Server).

Not decided yet: what a generator is as a unit, and which responsibilities
around orchestration and generator interfaces belong in divide (tools to
develop, inspect, debug or test them) and which in generator projects.

divide is meant to complement AI coding agents such as Claude Code, Codex or
OpenCode, not to be one: an agent should not have to write large amounts of
predictable code that a validated generator can produce.

Generation with Div is reproducible when its inputs and execution conditions
are controlled: the same template and data give the same output only if
everything else that takes effect is controlled too (Div can also read the
time, the request, random values and the PHP functions it may call). And
reproducible is not the same as correct: a generator is only as good as its
rules, models and checks.

**Div is integrated in divide**, and [Runner](https://github.com/divengine/runner)'s Flows run
through Runner's own command line. [Nodes](https://github.com/divengine/nodes)
(file-based structured data) and [Ways](https://github.com/divengine/ways)
(execution control points, routing, hooks and rules) are independent PHP
libraries that a generator may use; their role in generator development is
not decided. See the [vision](docs/vision.md).

## Quick start

Ready to run, with nothing else to install ([all the options](https://github.com/divengine/divide/wiki/Installation)):

```bash
brew install divengine/tap/divide          # macOS and Linux
scoop install https://github.com/divengine/divide/releases/latest/download/divide.json   # Windows
divide ~/sites/my-project                  # a folder as the project (divide . for this one)
divide page.tpl                            # a file on its own; divide alone: the Welcome window
```

The [latest release](https://github.com/divengine/divide/releases/latest) also has an
installer for Windows (`.msi`), `.deb`, `.rpm`, `.apk` and Arch packages, an
AppImage, and the binary alone for Linux and macOS.

From the source code, with Python 3.11+:

```bash
git clone https://github.com/divengine/divide.git && cd divide
tools/install.sh                           # the `divide` command, in ~/.local/bin
```

`tools/install.sh` installs divide in the checkout's `.venv` (editable) and
links the command, so `git pull` updates it. Or, isolated:
`pipx install git+https://github.com/divengine/divide.git`.

Rendering and include checks need `php` and Div in your project
(`composer require divengine/div`). divide finds the engine there, in
`$DIVIDE_DIV_PHP`, or in Options > Div engine.

| | |
|---|---|
| `F10` / `Alt+letter` | menus |
| `Ctrl+B` | project window: `Ins` new file, `F7` new folder, `F2` rename, `Del` delete |
| `Ctrl+Space` | completion |
| `Alt+F9` · `Alt+F8` | check the template · next error |
| `Ctrl+F9` | render the template with its data (`page.tpl` + `page.json`), or run the PHP script |
| `F8` · `F7` · `Ctrl+F8` | PHP debugger: step over · trace into · breakpoint |
| `Ctrl+T` | data tree ⇄ code |
| `Ctrl+Enter` | go to the included template |
| `Alt+T` | Tools: Dialector, Translate a template |
| `F1` · `Shift+F1` | help on the active window · help index |
| `F2` · `F3` · `Alt+X` | save · open · exit |

## Manual

The **[wiki](https://github.com/divengine/divide/wiki)** is the user manual,
with screenshots. divide carries its documentation as books: this manual and
[Div's documentation](https://github.com/divengine/div/tree/master/docs).
`F1` opens the help at the topic of the window you are in, in a help window
with Borland's help colours; each book has its contents, an index and cross
references.

- [Installation](https://github.com/divengine/divide/wiki/Installation)
- [Getting Started](https://github.com/divengine/divide/wiki/Getting-Started)
- [The Desktop](https://github.com/divengine/divide/wiki/The-Desktop)
- [Editing Templates](https://github.com/divengine/divide/wiki/Editing-Templates)
- [Editing PHP](https://github.com/divengine/divide/wiki/Editing-PHP)
- [Language Servers](https://github.com/divengine/divide/wiki/Language-Servers)
- [Completion](https://github.com/divengine/divide/wiki/Completion)
- [Checking Templates](https://github.com/divengine/divide/wiki/Checking-Templates)
- [Rendering](https://github.com/divengine/divide/wiki/Rendering)
- [Render Trace](https://github.com/divengine/divide/wiki/Render-Trace)
- [Running PHP](https://github.com/divengine/divide/wiki/Running-PHP)
- [Debugging PHP](https://github.com/divengine/divide/wiki/Debugging-PHP)
- [Web Server](https://github.com/divengine/divide/wiki/Web-Server)
- [Data Files](https://github.com/divengine/divide/wiki/Data-Files)
- [Project Window](https://github.com/divengine/divide/wiki/Project-Window)
- [Finding Files and Commands](https://github.com/divengine/divide/wiki/Finding-Files-and-Commands)
- [Dialector](https://github.com/divengine/divide/wiki/Dialector)
- [Translating Templates](https://github.com/divengine/divide/wiki/Translating-Templates)
- [Keyboard Reference](https://github.com/divengine/divide/wiki/Keyboard-Reference)
- [Troubleshooting](https://github.com/divengine/divide/wiki/Troubleshooting)
- [Help](https://github.com/divengine/divide/wiki/Help)

### One convention: save first

Div can take a template as a string, without a file, but then it has no folder.
Its includes would not resolve the way they will in production, and divide
would not know its data file. So **templates are saved before Div sees them**.
An untitled template is still highlighted, completed and checked, but its
includes are not resolved, and Ctrl+F9 and Go to include ask you to save it
first. Once a template has a file, its unsaved edits are always what Div gets.

## Development

The technical documentation (vision, use cases, architecture, design, test
plan, iterations), organised as Rational Unified Process artifacts, is in
[docs/](docs/README.md).

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                                                  # render tests need DIVIDE_DIV_PHP
.venv/bin/python -m divide.lang.div.preview [--kinds] file.tpl    # highlighted dump / token list
```

`examples/shop` is a small Div project (one template broken on purpose, and an
ERB-like `erb.dialect`) used by
the manual. `tools/wiki_shots.py --out <wiki clone>/images` retakes the
manual's screenshots from the real app on it, so they follow UI changes.
`tools/screencast.py --out <folder> tour` records the GIF above (and an MP4)
the same way, scene by scene.
`src/divide/manual/books.json` lists the help's books and where each is
written; `tools/sync_book.py <book> <checkout>` copies a book's pages into
`src/divide/manual/books/<book>/`, which the help window reads: run it after
the wiki (or Div's `docs`) changes.

Tests that render need `DIVIDE_DIV_PHP` (an `autoload.php`, or a Div checkout's
`src/div.php` with its `vendor/` installed); they are skipped otherwise.

### How divide relies on Div

What the engine decides is asked to the engine. The PHP bridge
(`src/divide/run/bridge.php`) runs Div for renders and answers questions
about it, such as where an include leads (`getTplPath()` with the template's
path, the render's working directory and the include history), which
dialect a template's `@_DIALECT` loads (`getTplPath()`, `getFileContents()`,
`jsonDecode()`, as `prepareDialect()` does), whether a dialect is valid
(`isValidCurrentDialect()`) and how a template reads in another dialect
(`translate()`). The Python side highlights, completes and checks the syntax
the lexer sees; until Div answers (or without Div) it guesses the dialect
file only to colour, and reports nothing about it.

### Layout

- `src/divide/lang/__init__.py` — the languages divide edits, by extension (name, help topic, checked or not)
- `src/divide/lsp/` — the Language Server Protocol client: known servers, positions, the session (pygls)
- `src/divide/ui/lsp.py` — language servers in the IDE: lifecycle, completion, hover, definitions, Options dialog
- `src/divide/lang/php.py` — PHP: tree-sitter-php's grammar for colours, `php -l` for errors
- `src/divide/lang/divjson.py` — Div JSON: tokens, parser with positions, writer, tree edits
- `src/divide/lang/div/` — the language, UI-independent (lexer, dialects, diagnostics)
  - `dialect.py` — `DIV_TAG_*` defaults (mirrors `div.php`), lenient dialect JSON, `@_DIALECT` resolution
  - `lexer.py` — dialect-aware lexer → `Token(start, end, kind)`
  - `diagnostics.py` — Div errors and warnings for the editor and the Messages window
  - `complete.py` — completion of variables, loops, include paths and tags
- `src/divide/editor/` — `DivEditor` (Textual `TextArea` fed by the lexer instead of tree-sitter) and theme
- `src/divide/ui/` — Turbo Vision pieces on [textual-vision](https://pypi.org/project/textual-vision/):
  editor / project windows, message boxes, file dialog, completion list, project file operations,
  the dialector, the help window; `HRule` / `VRule` divide a window and join its frame in Ts
- `src/divide/run/` — rendering: `bridge.php` (runs Div, replies JSON) and `render.py`
- `src/divide/run/composer.py`, `src/divide/ui/composer.py` — Composer: the project's packages, composer run under the progress box, the assistants
- `src/divide/run/setup.py` — the project's Div setup (`.div/setup.json`, and the user's `~/.div/setup.json`): constants before Div loads and Div's static API, applied by the bridge to every request
- `src/divide/manual/` — the built-in help: books (copies of a wiki or a docs folder) laid out as topics with cross references
- `src/divide/app.py` — the application: menus, status line, commands, window management
- `docs/div-language.md` — notes on Div as understood by the editor

### textual-vision

`textual-vision` is pinned to `0.0.1` (young, single maintainer). Things divide
works around, to revisit on upgrades:

- nested sub-menus get no keyboard focus → menus are kept one level deep;
- `DeskTop` has no API to reorder windows → `Divide._cycle` uses `_z_order`;
- `TextArea` binds `F6` (select line) and `Ctrl+W` → those bindings are `priority`;
- `F10` only highlights the bar, leaving focus in the editor → `DropMenuBar` opens the menu;
- handlers of every class in the MRO run unless `prevent_default()` → overrides never call `super()`;
- no shadows → `divide.ui.shadow` restyles the composited lines (Textual compositor subclass).

If the project stalls, its code (Apache-2.0, ~4.7k lines) can be vendored.

## License

divide is free software under the [GNU General Public License](LICENSE), version 3 or (at your option) any later version, like Div.
