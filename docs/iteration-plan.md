# Iteration Plan and History

divide follows RUP's phases in short iterations. Each iteration ends with
working, tested software pushed to `main`, with the manual updated once the
UI has been reviewed. Dates are commit dates.

## Phases

| Phase | Goal | Milestone | State |
|---|---|---|---|
| **Inception** | Is an IDE that speaks Div through Div worth building, and feasible on Textual? | Lifecycle Objectives: lexer prototype, TV shell, render through PHP | done (2026-11-12) |
| **Elaboration** | Prove the architecture: bridge, background checks, layered core, plug-in tables | Lifecycle Architecture: check while typing, includes by Div, help books, LSP | done (2026-11-13) |
| **Construction** | Build the features on that architecture | Initial Operational Capability: run and debug PHP, web server, trace, themes, navigation | done (2026-11-18) |
| **Transition** | Release to Div users: packaging, installation, feedback | Product Release: 0.1.0 (2026-11-18) | in progress |

## Iteration history

| # | Phase | Dates | Delivered |
|---|---|---|---|
| I1 | Inception | 2026-11-12 | Dialect-aware Div lexer and editor; Turbo Vision interface on textual-vision; drop shadows; Search menu; render through PHP and Div. |
| E1 | Elaboration | 2026-11-12 | Div JSON (highlighting, validation, references) and its tree editor; diagnostics while typing and the Messages window. |
| E2 | Elaboration | 2026-11-13 | Completion (variables, loops, includes, tags); project window file operations; includes resolved by Div, Ctrl+Enter; demo project and wiki screenshots. |
| E3 | Elaboration | 2026-11-13 | Dialector; template translation between dialects; dialects loaded and validated by Div; Browse buttons. |
| E4 | Elaboration | 2026-11-13 | Built-in help as books (divide's manual, Div's docs); PHP editor (tree-sitter, `php -l`); generic LSP client (phpactor, intelephense), signatures and docs; `tools/install.sh`. |
| C1 | Construction | 2026-11-14 | Run PHP scripts; Xdebug debugger; progress box; built-in web server with per-request debugging. |
| C2 | Construction | 2026-11-14 | Render trace (Div's mutations up to the fixed point); outline of PHP files; Turbo Pascal colours; ASCII/CP437-only screen. |
| C3 | Construction | 2026-11-15 | Progress bar; frame scroll bars; colour themes (turbo-pascal, turbo-c, free-pascal, modern-dark) and colour depth; File > Open as Turbo Pascal's; input line histories. |
| C4 | Construction | 2026-11-15 to 16 | Outline of Div templates; Go to file and the command palette; Find in files; double click to open in the project window; technical documentation (this folder); the manual's screenshots in the Free Pascal theme; Alt+P and Shift+F2 instead of Ctrl+Shift+P / Ctrl+Shift+F, which Windows Terminal keeps; Help > Search (full-text, ranked, SQLite FTS5) with its index built at sync time; Free Pascal dialogs readable (frame, title and label hotkeys); the progress box fixed (frame, full bar, closes by itself); the interface translatable (gettext) and in Spanish, Options > Language; highlighting of HTML, CSS, JavaScript, Markdown, SQL, XML, YAML, TOML, shell, INI and CSV. |
| C5 | Construction | 2026-11-16 | The help books in the interface's language (the manual and Div's docs in Spanish); the outline of every language divide colours, as a tree; the project window unfolds a file into its members; no child process outlives divide; Alt+letter in real terminals; `tools/screencast.py` (GIFs from the real app). |
| C6 | Construction | 2026-11-17 | The Div setup of a project (`.div/setup.json`, `~/.div/setup.json`, trust of `php` settings) and Options > Div setup; Tools > Composer packages; the data tree edits in place; Div's block-clash rule for dialects (divengine/div#36); a filter over every list and tree; the manual's GIFs. |
| C7 | Construction | 2026-11-18 | Cut, copy, paste and move in the project window; CI on Linux, macOS and Windows; Windows fixes (paths with `/`, phars, `php -S` ports, Xdebug paths, the project window's bar). |
| T1 | Transition | 2026-11-18 | Standalone binaries (PyInstaller) and the Release workflow: archives, deb, rpm, apk, Arch, AppImage, MSI, Homebrew tap, Scoop; `VERSION` and `releases/<v>.md`; GPL-3.0-or-later. **0.1.0**. |
| T2 | Transition | 2026-11-18 to 19 | Git: marks in the project window and the editor's margin, Changes, diffs as a code review, commit, history with its graph, branches, merge, stash, blame, pull, push; pull requests and issues (GitHub, Gitea). winget and the Microsoft Store wired, then turned off until their accounts are ready. **0.2.0**. |
| T3 | Transition | 2026-11-19 | A folder only when it is given, the Welcome window (recent folders and files), File > Open folder and Close folder, files with no folder; the mouse wheel on the Turbo Vision lists; the technical documentation brought up to date. **0.3.0**. |

## Next: plan

| Item | Kind | Notes |
|---|---|---|
| winget, Microsoft Store, PyPI | deployment | Wired in the Release workflow and off: winget needs the `WINGET_TOKEN` secret, the Store a product in Partner Center (`MSSTORE_*`), PyPI the project's account. Turned on when the owner says so. |
| Signed binaries | deployment | macOS and Windows ask before the first run of an unsigned binary. |
| Folders before files in File > Open | change request | Offered, not decided. |
| Static members marked in the PHP outline | enhancement | |
| Live stepping in the render trace | enhancement | |
| A test runner that runs one file at a time with a memory guard | environment | For small VMs. |

## Risk list

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| textual-vision is young (0.0.1) and may change or stall | medium | high | Pinned version; divide's additions are subclasses, not patches; divide could vendor it if needed. |
| Div's internals used by the bridge (trace, translate, dialect checks) change between versions | medium | medium | Ask through public API where possible; the bridge reports Div's version; tests with a real Div checkout. |
| Terminals differ in keys (Ctrl+Shift, Ctrl+Enter) and glyphs | high | medium | No command depends on Ctrl+Shift (Windows Terminal keeps Ctrl+Shift+P and Ctrl+Shift+F: Alt+P and Shift+F2 instead); Ctrl+J for Ctrl+Enter; ASCII/CP437 only; tested through SSH and tmux. |
| Memory on small VMs (language servers, PHP, tests) | high | medium | On-demand processes, bounded algorithms, tests run one file at a time. |
| Lexer drift from Div's real matching rules | low | high | `div.php` as the reference; design note [div-language.md](div-language.md); lexer tests; render and checks by Div itself. |
| Scope creep (an IDE for everything) | medium | medium | The vision's scope; languages and books as plug-ins, so the core stays small. |
| External programs change their output (git, `gh`, `tea`, Composer) | low | medium | Their machine formats (`--porcelain=v2`, `--json`) where they have them; parsers tested on recorded output; a failure shows the program's own words. |
| Distribution channels depend on third parties (stores, package indexes, signing) | medium | low | Every channel is optional in the workflow; a release publishes only files that work without them. |
