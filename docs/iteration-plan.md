# Iteration Plan and History

divide follows RUP's phases in short iterations. Each iteration ends with
working, tested software pushed to `main`, with the manual updated once the
UI has been reviewed. Dates are commit dates.

## Phases

| Phase | Goal | Milestone | State |
|---|---|---|---|
| **Inception** | Is an IDE that speaks Div through Div worth building, and feasible on Textual? | Lifecycle Objectives: lexer prototype, TV shell, render through PHP | done (2026-11-12) |
| **Elaboration** | Prove the architecture: bridge, background checks, layered core, plug-in tables | Lifecycle Architecture: check while typing, includes by Div, help books, LSP | done (2026-11-13) |
| **Construction** | Build the features on that architecture | Initial Operational Capability: run and debug PHP, web server, trace, themes, navigation | in progress |
| **Transition** | Release to Div users: packaging, installation, feedback | Product Release | planned |

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
| C4 | Construction | 2026-11-15 to 16 | Outline of Div templates; Go to file and the command palette; Find in files; double click to open in the project window; technical documentation (this folder). |

## Current iteration (C5): plan

| Item | Kind | Notes |
|---|---|---|
| Review of the template outline | validation | Pending the owner's feedback before the wiki's Outline page changes. Open questions: kind markers, `@else@` / `@empty@` as separators, following the cursor, doc comments. |
| Folders before files in File > Open | change request | Offered, not decided. |
| Static members marked in the PHP outline | enhancement | |
| Live stepping in the render trace | enhancement | |
| A test runner that runs one file at a time with a memory guard | environment | For small VMs. |

## Risk list

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| textual-vision is young (0.0.1) and may change or stall | medium | high | Pinned version; divide's additions are subclasses, not patches; divide could vendor it if needed. |
| Div's internals used by the bridge (trace, translate, dialect checks) change between versions | medium | medium | Ask through public API where possible; the bridge reports Div's version; tests with a real Div checkout. |
| Terminals differ in keys (Ctrl+Shift, Ctrl+Enter) and glyphs | high | medium | Every combination has an alternative (`>` in Go to file, Ctrl+J); ASCII/CP437 only; tested through SSH and tmux. |
| Memory on small VMs (language servers, PHP, tests) | high | medium | On-demand processes, bounded algorithms, tests run one file at a time. |
| Lexer drift from Div's real matching rules | low | high | `div.php` as the reference; design note [div-language.md](div-language.md); lexer tests; render and checks by Div itself. |
| Scope creep (an IDE for everything) | medium | medium | The vision's scope; languages and books as plug-ins, so the core stays small. |
