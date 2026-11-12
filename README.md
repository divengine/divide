# divide

Terminal IDE (TUI) for the Divengine projects. First milestone: the official
editor for [Div](https://github.com/divengine/div) templates.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/divide [--palette turbo-pascal|turbo-c] [folder] [files...]
.venv/bin/python -m divide.lang.div.preview [--kinds] file.tpl   # highlighted dump / token list
.venv/bin/pytest
```

The interface is a Turbo Vision desktop (menu bar, overlapping windows, dialogs,
status line) in the Turbo Pascal colours by default; `--palette turbo-c` or
the Options menu switches to Turbo C. Editor windows show `* line:col` on the
bottom border (`*` = modified) and their number on the top border. Windows,
dialogs and menus cast the Turbo Vision drop shadow (2 columns right, 1 row
down; what is underneath stays readable in dark gray on black).

| Key | Action |
|---|---|
| `F10`, `Alt+letter` | menu (F10 opens the first one; ←/→ walk the bar) |
| `F2` / `Ctrl+S` | save (untitled files ask for a name) |
| `F3` | open file dialog (wildcards, `Enter` on a folder enters it) |
| `Alt+F3` / `Ctrl+W` | close window (asks about unsaved changes) |
| `F5` | zoom window |
| `F6` / `Shift+F6`, `Ctrl+PgDn/PgUp` | next / previous window |
| `Alt+1`…`Alt+9` | go to window *n* |
| `Ctrl+B` | project window (open, raise, close) |
| `Ctrl+F` / `Ctrl+R` | find / replace (case, whole words, regex with `\1` groups, direction, origin, prompt) |
| `Ctrl+L` | search again (repeats the last find or replace) |
| `Ctrl+G` | go to line number |
| `Ctrl+F9` | Run > Render: template + data through PHP and Div (unsaved edits included) |
| `Alt+F5` | show the Output window |
| `Alt+F9` | Run > Check: Messages window with the template's Div errors |
| `Alt+F8` / `Alt+F7` | next / previous Div error (Turbo Pascal's next / previous message) |
| `Ctrl+T` | data tree ⇄ code: visual editor of the JSON data (from a template: its data) |
| `Alt+X` / `Ctrl+Q` | exit |

## Div errors while you type

Templates are checked on every edit (`divide.lang.div.diagnostics`, with the
template's dialect): unclosed loops and orphan `[/$x]`, `{?( )?}` without
`{/?}` (and orphan `{/?}`), begin tags that Div would leave as text because
their end is missing (`<!--{`, `{=`, `{@`, `{?(`, `(#`, `{#`, `{% `, `{%% `,
`[:`, `(( `, `{txt}`, `{strip}`, `<!--|`), includes that do not exist, a broken
`@_DIALECT`, and malformed JSON in `{= x: {...} =}`. Errors are painted red and
warnings brown in the editor; the status line shows the message under the
cursor or the counts. The Messages window (Alt+F9, or Window > Messages) lists
them as `page.tpl(12,5): Error: ...`, follows the active template live, and
Enter jumps to the place; render messages follow below.

## Rendering

Run > Render renders a template with its data: by Div's convention `page.tpl`
takes `page.json` (Run > Data file picks another one, Run > Edit data opens
or creates it). The editor buffers are used, saved or not, and the template's
real path is passed so relative includes work. Output goes to an Output
window; Div's warnings, PHP notices and data problems to a Messages window.
While the Output window is open, saving the template or its data re-renders.

It needs `php` and Div. divide looks for Div in `$DIVIDE_DIV_PHP`, then the
path set in Options > Div engine (stored in `~/.config/divide/config.json`),
then `vendor/autoload.php` (with `vendor/divengine/div`) above the template or
the project. Data is decoded by Div's own `jsonDecode`, so the warnings match
what the template sees.

Tests that render need `DIVIDE_DIV_PHP` (an `autoload.php`, or a Div checkout's
`src/div.php` with its `vendor/` installed); they are skipped otherwise.

## Data: Div JSON, as code or as a tree

Data files (`.json`, also `.dialect`) are Div JSON: what Div's `jsonDecode`
accepts, i.e. JSON plus `$name` / `$person.name` references as values, single
quotes, unquoted keys and comments. The code editor highlights and validates
it as you type (the status line shows the error's line and column).

`Ctrl+T` opens the same buffer as a tree. Enter edits an item (key, type:
String, Number, True, False, Null, Reference, Object, Array, and value), Ins
adds (inside an object / array, or after a plain value), Del deletes,
Ctrl+↑/↓ moves, Ctrl+Z / Ctrl+Y undo through the code editor, F2 saves.
Every tree edit rewrites the buffer as standard JSON (references stay bare);
divide asks first when that would drop comments, single quotes or unquoted
keys. Typing in the code rebuilds the tree.

Note on references: Div decodes a data file before any variable exists, so
`$refs` in `page.json` come out empty (rendering says so). They work in JSON
inside templates, e.g. `{= card: {"who": $person.name} =}`.

## Layout

- `src/divide/lang/divjson.py` — Div JSON: tokens, parser with positions, writer, tree edits
- `src/divide/lang/div/` — the language, UI-independent (lexer, dialects, diagnostics)
  - `dialect.py` — `DIV_TAG_*` defaults (mirrors `div.php`), lenient dialect JSON, `@_DIALECT` resolution
  - `lexer.py` — dialect-aware lexer → `Token(start, end, kind)`
- `src/divide/editor/` — `DivEditor` (Textual `TextArea` fed by the lexer instead of tree-sitter) and theme
- `src/divide/ui/` — Turbo Vision pieces on [textual-vision](https://pypi.org/project/textual-vision/):
  editor / project windows, message boxes, file dialog
- `src/divide/run/` — rendering: `bridge.php` (runs Div, replies JSON) and `render.py`
- `src/divide/app.py` — the application: menus, status line, commands, window management
- `docs/div-language.md` — notes on Div as understood by the editor

## textual-vision

`textual-vision` is pinned to `0.0.1` (young, single maintainer). Things divide
works around, to revisit on upgrades:

- nested sub-menus get no keyboard focus → menus are kept one level deep;
- `DeskTop` has no API to reorder windows → `Divide._cycle` uses `_z_order`;
- `TextArea` binds `F6` (select line) and `Ctrl+W` → those bindings are `priority`;
- `F10` only highlights the bar, leaving focus in the editor → `DropMenuBar` opens the menu;
- handlers of every class in the MRO run unless `prevent_default()` → overrides never call `super()`;
- no shadows → `divide.ui.shadow` restyles the composited lines (Textual compositor subclass).

If the project stalls, its code (Apache-2.0, ~4.7k lines) can be vendored.
