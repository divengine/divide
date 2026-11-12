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
bottom border (`*` = modified) and their number on the top border.

| Key | Action |
|---|---|
| `F10`, `Alt+letter` | menu |
| `F2` / `Ctrl+S` | save (untitled files ask for a name) |
| `F3` | open file dialog (wildcards, `Enter` on a folder enters it) |
| `Alt+F3` / `Ctrl+W` | close window (asks about unsaved changes) |
| `F5` | zoom window |
| `F6` / `Shift+F6`, `Ctrl+PgDn/PgUp` | next / previous window |
| `Alt+1`…`Alt+9` | go to window *n* |
| `Ctrl+B` | project window (open, raise, close) |
| `Alt+X` / `Ctrl+Q` | exit |

## Layout

- `src/divide/lang/div/` — the language, UI-independent
  - `dialect.py` — `DIV_TAG_*` defaults (mirrors `div.php`), lenient dialect JSON, `@_DIALECT` resolution
  - `lexer.py` — dialect-aware lexer → `Token(start, end, kind)`
- `src/divide/editor/` — `DivEditor` (Textual `TextArea` fed by the lexer instead of tree-sitter) and theme
- `src/divide/ui/` — Turbo Vision pieces on [textual-vision](https://pypi.org/project/textual-vision/):
  editor / project windows, message boxes, file dialog
- `src/divide/app.py` — the application: menus, status line, commands, window management
- `docs/div-language.md` — notes on Div as understood by the editor

## textual-vision

`textual-vision` is pinned to `0.0.1` (young, single maintainer). Things divide
works around, to revisit on upgrades:

- nested sub-menus get no keyboard focus → menus are kept one level deep;
- `DeskTop` has no API to reorder windows → `Divide._cycle` uses `_z_order`;
- `TextArea` binds `F6` (select line) and `Ctrl+W` → those bindings are `priority`.

If the project stalls, its code (Apache-2.0, ~4.7k lines) can be vendored.
