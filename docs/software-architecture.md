# Software Architecture Document

## 1. Introduction

This document describes divide's architecture through RUP's **4+1 views**:
use-case, logical, process, implementation and deployment views, plus a data
view. It records the decisions that shape the code and the reasons for them.
The class-level detail is in the [design model](design-model.md).

divide is an IDE for developing generators with the Divengine ecosystem
(see the [vision](vision.md)). This document describes the IDE: where
generator projects are written, configured, checked, rendered, traced and
debugged. A generator is a separate project, deployed and run without
divide, so its architecture is not described here. Which responsibilities
around orchestration and generator interfaces (CLI, API, MCP) might belong in
the IDE has not been decided; section 11 records only what the current
architecture already offers.

## 2. Architectural goals and constraints

- **Div decides, divide asks.** Anything Div decides is asked of Div through
  one PHP bridge. That keeps divide correct across Div versions and
  dialects.
- **UI-independent core.** Language logic (lexing, checks, completion,
  outline, Div JSON, search) and the runners (render, script, server, DBGp,
  trace) do not import the UI. They are pure Python with plain data in and
  out, testable without a terminal.
- **Turbo Vision on Textual.** The look and the command model come from
  textual-vision. divide adds what it lacks (shadows, frame scroll bars,
  histories, menus that open on F10) without forking it.
- **Never block the event loop.** External tools run as asyncio
  subprocesses, file searches in threads, and slow checks are debounced.
- **Extensible by data.** Languages (`divide.lang.LANGUAGES`), help books
  (`manual/books.json`), colour themes (`themes.THEMES`) and language servers
  (`lsp.SERVERS`) are tables.

## 3. Use-case view

The architecturally significant use cases (see the [use-case model](use-case-model.md)) are:

| Use case | Why it is significant |
|---|---|
| UC2 Edit a Div template | Exercises the lexer, the dialect resolution and the editor integration (highlight map, incremental cache). |
| UC3 Check a template / UC4 Render | Exercises the bridge, background workers, the Messages window and the progress box. |
| UC5 Trace a render | Needs a deeper conversation with Div (traced render) and its own window. |
| UC11 Debug PHP / UC12 Web server | Long-lived external processes, a socket protocol (DBGp) and UI state that follows them. |
| UC9 Edit PHP with a language server | A long-lived JSON-RPC server per language, synchronised on every edit. |
| UC13 Find files, text and commands | Project-wide work that must stay bounded in time and memory. |
| UC16 Work with git / UC17 Pull requests | Every change made by external programs (`git`, `gh`, `tea`) that can never ask a question, their output streamed line by line, and state (marks, margin) refreshed as files change. |
| UC1 Open and navigate a project | The project folder is optional: everything that walks the project must work, or offer to open one, with no folder. |

## 4. Logical view

divide is layered. Upper layers depend on lower ones, never the reverse.

```mermaid
flowchart TB
    subgraph Presentation["Presentation: divide.ui, divide.app"]
        App["Divide app<br/>(menus, keys, commands, layout)"]
        Mixins["Feature mixins<br/>Run, Lsp, Web, Trace, Outline, Palette,<br/>FindInFiles, Colors, Explorer, Language,<br/>Git, Forge, Composer"]
        Windows["Windows & dialogs<br/>editor, project, messages, output, help,<br/>jsontree, dialector, tracer, git, diff,<br/>forge, composer, div setup, welcome"]
    end
    subgraph Editor["Editor: divide.editor"]
        DivEditor["DivEditor<br/>(TextArea + divide's highlighting)"]
        Search["search"]
        ETheme["editor themes"]
    end
    subgraph Languages["Languages: divide.lang"]
        Div["div: lexer, dialect, diagnostics,<br/>complete, outline, dialector"]
        DivJson["divjson"]
        Php["php (tree-sitter, php -l)"]
    end
    subgraph Services["Services"]
        Run["divide.run: render, workbench, script, server,<br/>dbgp, trace, setup, git, forge,<br/>composer, children, bridge.php"]
        Mcp["divide.mcpserver: tools, protocol,<br/>http (Options > MCP server), stdio (divide --mcp)"]
        Outline["divide.outline"]
        Lsp["divide.lsp: servers, client"]
        Manual["divide.manual: help books"]
        Themes["divide.themes"]
        Config["divide.config, divide.recent"]
    end
    App --> Mixins --> Windows
    Windows --> DivEditor
    Mixins --> Run & Lsp & Manual & Outline
    DivEditor --> Div & DivJson & Php & ETheme
    ETheme --> Themes
    Windows --> Themes
    App --> Config
    Mcp --> Run
    Mixins --> Mcp
```

| Package | Responsibility |
|---|---|
| `divide.app` | The `Divide` application: menu bar, status line, key bindings, the command dispatcher (`run_command`), window layout, the glue between editors and services. It is composed from the feature mixins. |
| `divide.ui` | Turbo Vision windows, dialogs and lists. One module per feature area, usually a window or dialog plus a mixin that adds the feature to the app. |
| `divide.editor` | `DivEditor`, the text editor (Textual's TextArea with divide's highlighting for Div and Div JSON, tree-sitter for PHP), plus find/replace and the editor colour themes. |
| `divide.lang` | The languages: which files they own, and their lexers, checkers, completion and outline. UI-independent. `treesitter`: the grammars of the other files of a project (HTML, CSS, JavaScript, Markdown, SQL, XML, YAML, TOML, shell); `plain`: INI and CSV. |
| `divide.run` | Everything that runs an external program: render and resolve through the bridge, a template's engine, data file, dialect and checks as the IDE sees them (`workbench`, shared by the editor and the MCP server), scripts, the web server, the DBGp debugger, the render trace, the Div setup (`setup`), Runner Flows (`flow`: find Runner, run its bootstrap, read a saved context; `flowmodel`: a Flow's structure from its YAML, in-place edits, Runner's check; `flowedit`: the Designer's structural edits), git (`git`), the forges (`forge`, through `gh` and `tea`), Composer (`composer`), the folders watched for outside changes (`fswatch`), and the guard that no child outlives divide (`children`). UI-independent. |
| `divide.mcpserver` | divide's own MCP server, standard library only: `tools` (the seven tools, on `divide.run`), `protocol` (MCP's JSON-RPC in both eras), `http` (Streamable HTTP on `/mcp`, run by the IDE: Options > MCP server, `divide.ui.mcp`) and `stdio` (`divide --mcp PROJECT`). The project's setup, a template's checks, renders and the render trace for MCP clients, without the UI. See 4.1. |
| `divide.outline` | The outline of every language divide colours, as trees of `Node`s (one builder per family: PHP, Div, markup, code, data). Search > Outline and the project window's file members use it. UI-independent. |
| `divide.lsp` | The known language servers and the LSP client (pygls). |
| `divide.manual` | The help books: Markdown pages to help topics; `fulltext`: their search index (SQLite FTS5). |
| `divide.themes` | Every colour divide draws, as palettes with roles. |
| `divide.config` | The settings file. |
| `divide.recent` | The folders and files opened lately (the config's `recent`), for the Welcome window. |
| `divide.i18n` | The interface's language: gettext catalogues in `locale/`, `_()` and `ngettext()`. |

### 4.1 Key mechanisms

- **Command dispatch.** Menus, the status line, key bindings and the command
  palette all post a `CommandMessage(command, info)`. `Divide.run_command`
  matches it and calls the feature. A new feature adds a `CM_*` constant, a
  menu item, perhaps a binding, and a case.
- **Highlighting.** `DivEditor` replaces TextArea's tree-sitter highlight map
  builder with divide's lexers for Div and Div JSON. The lexer output is
  cached per text and dialect. PHP keeps tree-sitter. Token kinds map to
  syntax roles in `themes.TOKENS`, and each palette colours the roles.
- **Theming.** A `Palette` produces a Textual theme with `$divide-<role>`
  CSS variables, plus the editor TextArea themes. Switching themes refreshes
  every widget. On 16-colour terminals every colour snaps to its ANSI slot.
- **Views over a buffer.** The data tree and the dialector never own data.
  They parse the editor's text and write their edits back as text edits.
- **An optional project.** `Divide.folder` is the folder given or opened, or
  `None`. `Divide.root` is where relative work happens: the folder, else the
  active file's folder. Features that need a project (the project window, Find
  in files, the project's Div setup) check `folder` and offer File > Open
  folder when there is none; Go to file lists no files, and git works on the
  repository of `root`. Opening another folder closes the windows of the
  last one and stops its language servers, debug session and web server.
- **External programs that never ask.** git, `gh`, `tea` and Composer run
  with their prompts off (`GIT_TERMINAL_PROMPT=0`, no terminal; on Linux and
  macOS in a session of their own, so ssh cannot ask for a passphrase on
  divide's screen). Their output reaches the progress box line by line, and a
  failure is shown in their own words.
- **Runner Flows.** divide does not run SFM Flows itself: `run.flow` starts
  Runner's official bootstrap of the project's Composer installation (`php
  vendor/divengine/runner/bin/run.php FLOW --json [--context] [--root]
  [--save-context]`) through `run.script.run_script`, the same child process
  as a PHP script (tracked, killed on Esc and when divide ends), in the
  project's folder. The exit code is the state (0 done, 3 paused, 1 error, 2
  invocation or persistence error; anything else: PHP died; killed:
  cancelled); stdout is the resulting context (JSON), stderr the Flow's output
  and Runner's diagnostics. `read_saved` reads a context file's
  `_runner_state` and `_flow_state` only to tell the user and to decide
  whether Resume is possible: Resume passes the file back as both `--context`
  and `--save-context`, as Runner's own resume does. The file is by default
  one per Flow under the project's `.div/runner/` (`default_checkpoint`,
  kept out of Git by a `.gitignore` there); any other is the user's choice.
  divide never restarts a paused run without asking, nor replaces a file the
  user chose, and since Runner writes the
  context only at the end (atomically), a stopped run leaves it as it was.
  `ui.flow` (Ctrl+F9 on a YAML Flow, the Run Flow dialog) reuses the progress
  box, the Output and Messages windows and the config file; the run and its
  report are apart from the dialog, for a Flow workspace to come.
- **Outside changes in the project window.** `run.fswatch.FolderWatcher` watches a
  set of folders with watchdog's native observer (inotify, FSEvents,
  ReadDirectoryChangesW), each one alone, never recursively, at most 64 (watchdog
  runs a thread per watch). Created, deleted and moved entries mark their
  folder (a move, both); a burst is gathered for 0.3 s and handed over once, as
  a set without repeats and with its generation; past 128 folders a batch says
  "everything watched". `ui.windows.ProjectTree` owns one watcher for as long as
  it is mounted (the project window: closing it, switching or closing the
  folder, quitting stop it): the watched set is the root and the open folders,
  updated when folders open, close or are read again. Batches come from
  watchdog's threads through `call_from_thread`; a stale generation is dropped;
  each affected open folder is listed (in a worker thread) and read again with
  Textual's `reload_node` only when what it holds differs from what is shown,
  an ancestor covering its descendants; the scroll position and the bar stay.
  A folder the system refuses to watch is said once; Ctrl+R stays. Editor
  buffers are never reloaded. `tools/bench_watch.py` measures it.
- **The Flow window.** The YAML is the only model. `run.flowmodel` reads the
  code editor's buffer with tree-sitter-yaml (divide's highlighter) into
  Blocks and Steps that remember where each key and value is written, and
  plans edits as one replacement of the smallest span: a changed value
  replaces its characters, a new attribute is one line with its siblings'
  indentation, a removed attribute or Step its own lines; comments, key order
  and formatting elsewhere stay byte for byte; a block-style context is
  changed key by key; a plan that would remove a comment is refused (the code
  is where to make it), and each plan is verified by parsing the result again
  (undone if it reads back otherwise, a lost comment included). A Step in flow
  style, anchors, aliases, tags, block scalars and invalid YAML are shown, not
  edited. Validation is Runner's: `run/flowcheck.php` loads only Runner's
  source file and calls `runner::generateFlowCodeFromYaml()` (its parser,
  schema and call/jump targets) without evaluating the code, so nothing of
  the project runs; two lookups add what Runner's first error hides (targets
  missing from the file; activity and condition files missing where Runner's
  documented importer would look, only checked for existence, with PHP's
  `function_exists` for plain names). The diagnostics are the code editor's
  (squiggles, Messages, Alt+F8). `ui.flowmodel` is the window (Ctrl+T on a
  Flow, like the Data tree on JSON): a tree, an inspector and Runner's
  verdict; each edit is one edit of the code's buffer (undo, the modified
  mark, F2); Ctrl+F9 is `ui.flow`'s Run Flow dialog.
- **The Flow Designer.** The same buffer drawn as a board. `run.flowedit`
  plans structural edits on `run.flowmodel`'s spans: a Block's or Step's
  *unit* (its lines, the comment lines right above it at its indentation,
  the deeper comment lines after it) is what moves (two neighbours swap
  text for text) and what a deletion removes; a rename replaces the key's
  characters and those of each `call`/`jump` value that names it, in its
  quoting; references to what is deleted lose their own lines, refused when
  a comment is on them or the Step would be left empty. Each plan is one
  replacement (`chain` joins a rename and an edit into one undo step) whose
  check reads the result back as an outline of every Block's and Step's
  keys and values as written, and counts comments. `ui.flowlayout` lays the
  board out as character cells, with no Textual: lanes, cards in Runner's
  order of a Step, and connections derived from the YAML, routed in their
  own gutter tracks and band channels (greedy interval colouring) so lines
  never run over a card and crossings are drawn as crossings (CP437, calls
  single, jumps double); selection, emphasis and a playback `Overlay` (for
  divide #10) are painted over the layout. `ui.flowboard` is the window
  (Run > Flow designer; Ctrl+D flips with the tree, Ctrl+T with the code,
  which reopens the last view), a `FlowView` like the tree's, sharing its
  inspector, verdict and Step dialog; invalid YAML keeps the last design
  that parsed, read-only. Each Block is a full-height column of one of two
  alternating surfaces and each card a third, levels blended from the
  window's colours (one darker, one lighter, so they stay apart in 256 or
  16 colours and are levels of light in a monochrome theme); the panel holds
  what is going on (in reverse video, only while so), the inspector, the
  Flow's summary and the verdict. `ui.flowcontext` edits a Step's context as
  data on a copy, in the JSON editor's tree and item dialog or as JSON text in
  the code editor; `run.flowmodel.context_data`/`render_context` read it from
  YAML (Runner's scalar rules) and write it back as a flow mapping, through
  the same Step edit (a block-style context changed key by key).
- **The MCP server.** Three layers, standard library only (no MCP SDK, no
  web framework). `mcpserver.tools`: each tool calls the same functions the
  IDE calls: `workbench.check_template` (the dialect Div loads, the lexer,
  Div's answers for includes, `diagnostics.check`), `render.render`,
  `trace.trace_render`, `render.check_setup`, `render.load_dialect` and
  `render.check_dialect`, so a question gets the same answer in the IDE and
  through MCP; arguments are checked against each tool's JSON Schema.
  `mcpserver.protocol`: MCP's JSON-RPC in both eras, 2026-07-28 (stateless:
  the version in every request's `_meta`, `server/discover`, `resultType`)
  and 2024-11-05 to 2025-11-25 (`initialize`); no sessions, so a server
  restarted from the IDE keeps its clients. Transports: `mcpserver.http`
  (one `POST /mcp`, one JSON answer per request, no SSE; GET and DELETE get
  405) and `mcpserver.stdio` (one message per line). Neither imports the UI;
  `divide.ui.mcp` (Options > MCP server) starts and stops the HTTP one.
  Paths are confined to the project (symbolic links followed), PHP runs under
  the same timeouts and is killed when a call is cancelled (on HTTP: the
  client closes the connection; on stdio: `notifications/cancelled`), answers
  are bounded, traces are kept in memory (the last four) to be paged, and the
  trust of a project's `php` settings is read, never given. Over HTTP: bound
  to 127.0.0.1 by default, Host and Origin checked (no DNS rebinding, no CORS),
  a bearer token required off loopback (`mcp-token` beside `config.json`,
  0600), bodies of up to 16 MiB, 32 connections, 4 tool calls at once, 300 s
  at most per request. It works on files and on text passed in; it does not
  see the open editors.
- **Background work.** Textual workers (`@work`) run commands. Subprocesses
  use asyncio. CPU-bound project searches use `asyncio.to_thread`. Debounce
  timers (0.25-0.5 s) delay include resolution, `php -l`, LSP sync and
  dialect checks until typing pauses.

## 5. Process view

```mermaid
flowchart LR
    subgraph divide["divide process (asyncio event loop)"]
        UI["Textual UI<br/>event loop"]
        W["workers<br/>(commands)"]
        T["threads<br/>(find in files, file lists)"]
    end
    Bridge["php bridge.php<br/>(one per request)"]
    Lint["php -l<br/>(per check)"]
    Script["php script.php"]
    Server["php -S<br/>(long-lived)"]
    XD["Xdebug<br/>(inside php)"]
    LS["language server<br/>(long-lived, stdio)"]
    Git["git, gh, tea<br/>(per command)"]
    Comp["composer<br/>(per command)"]
    UI --> W
    W -- "JSON on stdin/stdout" --> Bridge
    W -- stdin --> Lint
    W --> Script
    W --> Server
    XD -- "DBGp over TCP<br/>(divide listens)" --> W
    W -- "JSON-RPC over stdio" --> LS
    T --> Git
    W -- "stdout line by line" --> Git
    W --> Comp
```

- The UI thread runs Textual's event loop. Commands run as workers on the
  same loop, so their awaits never freeze the screen.
- The **bridge** is a one-shot PHP process per request: render, resolve,
  `dialect_validate`, `dialect_load`, `trace` or `translate`. Being
  stateless, it always sees the files and the engine as they are now.
- **The MCP server over HTTP** runs inside divide, in threads of its own
  (`mcpserver.http.HttpServer`): the listener (`ThreadingHTTPServer`, a
  short-lived thread per connection) and one asyncio loop where every tool
  call runs and asks the bridge as the IDE does. A connection's thread hands
  its request to that loop and waits, watching whether the client closes the
  connection (then the call is cancelled and PHP killed). Textual's loop only
  starts and stops it, through `asyncio.to_thread`; Alt+X, File > Close
  folder and divide's end stop it (calls cancelled, connections closed,
  threads joined), and another folder restarts it there. Threads rather than a
  process: about 1 MB instead of about 29 MB, nothing to orphan (the threads
  end with divide on every system), and the tool calls are waits on PHP, not
  Python work that would hold the UI.
- **`divide --mcp`** is a process of its own, without the UI: a thread reads
  stdin line by line, each request is a task on the process's loop and asks
  the bridge as the IDE does, answers go to stdout (anything else to stderr).
  The client starts and ends it.
- **Language servers** are long-lived, one per language and project,
  started when the first file of their language opens and stopped on exit.
- **Debugging**: divide listens on a free local port. Xdebug, inside the PHP
  process of the script or of `php -S`, connects back. `DebugSession` drives
  it.
- No child outlives divide (`run.children`): on Linux the kernel ends each
  one when divide dies (`PR_SET_PDEATHSIG`), and the ones still running are
  killed when the app closes, however it ends.

## 6. Implementation view

```
src/divide/
  app.py               the application, commands, layout, the command line
  mcpserver/           divide's MCP server: tools, protocol, http, stdio
  config.py            settings file
  recent.py            recent folders and files
  themes.py            colour palettes and roles
  glyphs.py            the characters divide may draw
  editor/              DivEditor, search, editor themes
  lang/                languages: __init__ (table), php.py, divjson.py
    div/               lexer, dialect, diagnostics, complete, outline, dialector, preview
  outline/             outlines: php, div, markup, code, data
  run/                 render.py, workbench.py, script.py, server.py, dbgp.py, trace.py, setup.py,
                       git.py, forge.py, composer.py, children.py, bridge.php,
                       functest.py (+ .php), simulate.py, funcsim.py (+ .php), functrace.py
  lsp/                 server table, client
  manual/              help engine, books.json, books/<id>/ and books/<id>.<lang>/ (copied pages)
  locale/              gettext catalogues (divide.pot, <lang>/LC_MESSAGES/divide.po, .mo)
  ui/                  windows, dialogs, one module per feature
tests/                 pytest (+ pytest-asyncio), one file per area
tools/                 install.sh, sync_book.py, i18n.py, wiki_shots.py, screencast.py
packaging/             the standalone binary (PyInstaller), Linux packages, AppImage, MSI,
                       the Homebrew, Scoop and winget manifests, MSIX
releases/              VERSION's notes: one per version
.github/workflows/     tests.yml (Linux, macOS, Windows), release.yml
docs/                  this documentation
```

Dependencies are declared in `pyproject.toml`: textual, textual-vision
(pinned), tree-sitter with the grammars of PHP and the other file types, and
pygls, plus pytest, pytest-asyncio, Babel and the official MCP SDK (its
clients test divide's MCP server) for development. The MCP server itself
needs nothing beyond the standard library, so the standalone binaries have it.
The version is
the one line of `VERSION`. The console entry point is `divide =
divide.app:main`.

## 7. Deployment view

```mermaid
flowchart LR
    Term["Terminal emulator<br/>(Windows / macOS / Linux)"] -- "SSH / tmux / local" --> Host
    subgraph Host["Host running divide"]
        D["divide (Python)"]
        P["php + Div engine<br/>(+ Xdebug)"]
        L["language servers"]
        G["git, gh, tea"]
        K["composer"]
        C["~/.config/divide/config.json<br/>~/.div/setup.json"]
    end
    D --> P & L & G & K & C
    G -- HTTPS / SSH --> Remote["remotes, GitHub, Gitea"]
    Browser["Browser"] -- HTTP --> P
```

The terminal emulator may be on another machine, so fonts and key encodings
are not under divide's control. This is why divide sticks to ASCII and CP437
glyphs, and why no command depends on a Ctrl+Shift combination (Windows
Terminal keeps Ctrl+Shift+P and Ctrl+Shift+F for itself). See
[deployment.md](deployment.md) for installation and configuration.

## 8. Data view

divide has no database. Its persistent data:

| Data | Where | Owner |
|---|---|---|
| Settings: palette, colours, icons, Div engine, Xdebug, LSP choices and commands, run arguments, web server, Composer, input histories, the diff's layout, recent folders and files | `$XDG_CONFIG_HOME/divide/config.json` | `divide.config` and the feature that uses each key |
| Div setup of a project, of the user | `<project>/.div/setup.json`, `~/.div/setup.json` (`$DIV_HOME`) | the developer, through Options > Div setup (`divide.run.setup`) |
| Trusted PHP settings of projects | `~/.div/trust.json` (a hash per setup file) | `divide.run.setup` |
| Mock Simulation opt-in of projects | `$XDG_CONFIG_HOME/divide/config.json`, key `function_simulation_trust` (never in the project) | `divide.run.funcsim` |
| Mock Simulation scenarios | `<project>/.div/function-simulations/<module>/<name>.<scenario>.json` (versioned) | the developer, through `divide.run.funcsim` |
| Mock Simulation traced runs | `<project>/.div/function-simulation/<run>/` (out of Git, the retention of Flow simulations) | `divide.run.functrace` |
| Language server caches | `$XDG_CACHE_HOME/...` | `divide.lsp.client` |
| Help books | `src/divide/manual/books/<id>/` (packaged) | `tools/sync_book.py` |
| Help search index | `src/divide/manual/search.sqlite`, `search.<lang>.sqlite` per language of the books (packaged; rebuilt in memory when stale) | `tools/sync_book.py` → `divide.manual.fulltext.build` |
| Projects' files | the project folder | the developer; divide only reads and writes what is edited. The repository and `composer.json` are changed only by git and Composer. |

## 9. Size and performance

About 26,000 lines of Python in 74 modules, plus one PHP bridge, with about
360 tests in 46 files, run on Linux, macOS and Windows. The design targets small virtual machines: on-demand
processes, bounded searches, and an incremental lexer cache. See the
[supplementary specification](supplementary-specification.md).

## 10. Quality decisions

| Decision | Alternatives considered | Reason |
|---|---|---|
| A PHP bridge instead of a Python Div | Port Div's rules to Python | Div's behaviour (fixed point, dialects, includes, jsonDecode) would drift. Asking Div is always right. |
| Own Div lexer (no tree-sitter grammar) | A tree-sitter grammar | Dialects change the tags at runtime, and Div matches blocks by key and balance, which a static grammar cannot express. |
| textual-vision | Plain Textual widgets, or curses | The Borland look and command model come ready-made, and Textual gives testing (pilot), CSS and Unicode handling. |
| Mixins on the app | A plug-in registry | Each feature needs the app's windows, dialogs and commands. Mixins keep each feature in one module with no extra indirection. |
| Own fuzzy matcher | Textual's `FuzzySearch` | Textual's matcher enumerates every placement of the letters, which explodes on long paths and large projects. A linear matcher keeps memory and time bounded. |
| git's file list for project search | Walking the tree | It respects `.gitignore` and is fast. The tree walk with the project window's hidden folders is the fallback. |
| tree-sitter grammars with Textual's queries for the other files | Writing lexers; Pygments | The grammars are the packages of Textual's own `syntax` extra and Textual ships tuned highlight queries for them; their captures are renamed into divide's namespace (`ts.*`) so the palettes colour them by role, as PHP. Grammars load on first use and stay cached (a freed grammar crashes tree-sitter). INI and CSV have no grammar there and are a few lines of lexer each. |
| gettext for the interface's languages | Own JSON catalogues; Fluent | gettext is in the standard library, handles plurals, and every translation tool (Poedit, Weblate, Crowdin) reads its `.po` files. Babel is needed only to extract and compile, as a development tool. |
| The language chosen at start | Switching live | Many texts are module constants (titles, hints, theme names). Choosing at start keeps them simple values; Options > Language applies at the next start, like the colour depth. |
| SQLite FTS5 for the help search | A hand-written inverted index and ranking; an external search engine | FTS5 ships with Python's `sqlite3`: BM25 ranking, Porter stemming, prefix queries and snippets, with no dependency. |
| The help index built at sync time and shipped | Built at every start; built on the first search only | The books change only when synced, so the index is built once with them. A fingerprint of the pages detects a stale index, which is then rebuilt in memory (0.1 s), so results are never out of date. |
| Two FTS5 tables (stemmed and as written) | One stemmed table | A prefix of a stem is not a prefix of the word (*Iterations* is stored as `iter`, so `itera*` would miss it). Finished words match stems; the word being typed matches either table. |
| The system's `git` for everything | A Python git library (dulwich, pygit2) | The developer's own settings, hooks, credentials and signing keep working, and git's merges and machine formats (`status --porcelain=v2`, `for-each-ref`) are git's own. Nothing to bundle. |
| `gh` and `tea` for the forges | Calling GitHub's and Gitea's APIs | They are signed in as the developer already, and each speaks its forge; divide reads their JSON and needs no token of its own. |
| A folder only when it is given | Always the current folder | As VS Code: `divide` alone in the home folder would otherwise make it the project (its file list, its language servers); the Welcome window brings back the recent ones. |
| Standalone binaries (PyInstaller) for releases | Only `pip install` | Users get divide without Python, from Homebrew, Scoop, the MSI, Linux packages or the AppImage; one recipe builds them all on each platform's runner. |

## 11. Open questions (not designed)

**Function Mock Simulation** (one Runner Function run with dependency doubles
and a PHP line trace): the decision is in
[function-simulation.md](function-simulation.md). Its engine
(`divide.run.funcsim`, #21) and its PHP line trace (`divide.run.functrace`,
#22) are built, with no UI yet (#23). A Mock Simulation runs real PHP: it is not a sandbox, and it is not the
Flow simulation of `divide.run.simulate`, where no Function code runs.

Orchestration and interfaces such as a CLI, an HTTP API or an MCP server may
be implemented by generator projects; divide may offer tools to develop,
inspect or test them. divide's own MCP server (4.1) is the IDE's, not a
generator's: it serves divide's design-time services and does not orchestrate
generations. How responsibilities are split between the IDE and
generator projects is not decided, and the abstraction model is still to be
specified. This document defines no execution graph, pipeline format or
interface. What the current architecture already offers, whatever is
decided:

- **A UI-independent core.** Rendering, tracing, dialect checks and
  translation (`divide.run`) take plain data and return plain data, without
  importing the UI, so tools of the IDE other than its windows call them:
  divide's MCP server does.
- **One bridge to Div.** Every question to Div goes through `bridge.php` as
  one JSON request and one JSON reply, with the project's Div setup applied.
  Another caller could ask Div the same way the editor does.
- **Toward a live session.** The HTTP server already runs inside divide,
  but its tools work on files and on text passed in. Giving them the open
  editors, unsaved buffers, the active template and the IDE's diagnostics
  would give the same tools another source of text; the tools already take
  the text as an argument.
- **No hidden state in divide.** The bridge is one-shot and stateless, so
  divide adds nothing between requests. What a render depends on beyond its
  template, data, engine and setup (the time, random values, the request,
  PHP functions) is Div's; controlling it is the generator's concern.

