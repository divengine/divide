# Supplementary Specification

The requirements that are not use cases: qualities (FURPS+) and constraints.

## Functionality (cross-cutting)

- **F1 Div is the authority.** Rendering, include resolution, data decoding,
  dialect validation and loading, tracing and translation are answered by
  Div through `run/bridge.php`. Python never reimplements a decision Div
  makes. Where the editor must work without PHP (highlighting, static
  checks), the lexer mirrors Div's matching rules, and `div.php` is the
  reference when it and the wiki disagree (see [div-language.md](div-language.md)).
- **F2 Div is never modified.** divide works with any Div 6.x installation.
  Bugs found in Div are reported upstream, not patched locally.
- **F3 Reuse before building.** divide uses existing tools: tree-sitter for
  PHP, `php -l`, Xdebug, `php -S`, LSP servers, git's file list and
  Textual's widgets.
- **F4 Plug-in languages and books.** A language is one entry in
  `divide.lang`, and a help book is one entry in `manual/books.json`.

## Usability

- **U1 Borland conventions.** Menus, keys (F2, F3, F5, F6, Alt+F3, Ctrl+F9,
  Alt+F9, Alt+F8...), dialogs, histories and colours follow Turbo
  Pascal / Turbo Vision. VS Code conventions are added only where the Borland
  IDEs had nothing (Go to file, command palette, Find in files).
- **U2 Keyboard first, mouse too.** Everything can be done from the keyboard.
  The mouse moves, resizes and clicks. Opening a file in a list or tree takes
  a double click, so a single click only selects.
- **U3 The status line tells you the next step.** It shows the key hints for
  the context and a hint about the active window.
- **U4 Context help.** F1 explains the active window, and every window has a
  help topic.
- **U5 Wizards over crowded screens.** Paths have a Browse button and
  suggested values come from what is declared.

## Reliability

- **R1 No lost work.** Closing a window or quitting asks about unsaved
  changes. Views over a buffer (data tree, dialector) edit the buffer, so
  undo and the dirty flag keep working.
- **R2 External tools fail soft.** A missing PHP, Div, Xdebug, language
  server or git disables the feature and says why. It never takes down the
  IDE.
- **R3 Long jobs can be stopped.** Renders, checks and scripts run under the
  progress box, and Esc stops them.

## Performance

- **P1 Typing stays immediate.** Highlighting is incremental through cached
  lexer results. Include resolution and checks are debounced and run in the
  background.
- **P2 Bounded algorithms on user data.** For example, the fuzzy matcher of
  Go to file is linear in the occurrences of each letter, where an
  enumeration of combinations could fill memory on long paths. Find in files
  skips binary files and files over 2 MB, and caps its matches.
- **P3 Modest memory.** divide must be comfortable on small virtual machines
  (a few GB of RAM, shared with other services). Background processes (PHP,
  language servers) are started on demand and stopped on exit.

## Supportability

- **S1 Same look in every terminal.** divide's own glyphs are ASCII or
  CP437, single width, with no Nerd Fonts and no emoji (`tests/test_glyphs.py`).
- **S2 Colour depth.** Truecolour, 256 and 16 colours. On 16-colour
  terminals each colour maps to its own ANSI slot. `--colors` can force a
  depth.
- **S3 Platforms.** Linux, macOS and Windows terminals, including over SSH
  and tmux. Python 3.11 or newer (developed on 3.14).
- **S4 Testable without a terminal.** The UI is tested headless with
  Textual's pilot. Language logic is UI-independent and unit-tested.

## Design constraints

- Python with Textual 8.2 and textual-vision 0.0.1 (pinned), tree-sitter and
  tree-sitter-php, and pygls for LSP.
- One process for the UI. External work goes to subprocesses (PHP, servers)
  or threads (file searches), never blocking the event loop.
- Configuration is a single JSON file under `$XDG_CONFIG_HOME/divide`.

## Documentation requirements

- The user manual is the wiki. It documents divide only and links to Div's
  docs. The same pages are built into the help (`tools/sync_book.py`).
- Screenshots come from the real application (`tools/wiki_shots.py`). They
  are regenerated only after a UI change has been reviewed.
- This folder holds the technical documentation (RUP artifacts).
