# Project Window

**Ctrl+B** opens the project tree on the left (and raises it, or closes it when it is already on top). It opens by itself when divide starts without files.

![the local menu of the project window](images/project-menu.png)

**Enter** opens a file, or folds and unfolds a folder. **→** unfolds a folder (or a file, below) and **←** folds it, or goes up to the folder that holds the bar. With the mouse, a click puts the bar on a file and a double click opens it; a click on a folder folds or unfolds it. Version control and cache folders (`.git`, `__pycache__`, `.venv`, `node_modules`, tool caches) are hidden; `vendor/` stays visible.

## A file's members

A file in a language with an [[Outline]] (templates, PHP, HTML, Markdown, CSS, JavaScript, SQL, JSON, YAML...) has a `►` too: unfolded, it shows its members below it, the same tree as **Search > Outline**: a PHP file its classes, their methods and properties, its functions; a template its tags; a Markdown file its headings; a JSON file its keys...

- **→** or a click on the `►` unfolds the file, without opening it; a class or a block unfolds the same way. A file holding a single class or namespace shows it unfolded at once.
- **Enter** or a double click on a member opens the file with that member selected. On the file itself, Enter opens the file, as always.
- The members are read when the file is unfolded: from its window if it is open (unsaved changes too), from the disk if not. Saving the file updates them, keeping what was unfolded.
- **F2** and **Del** on a member do nothing to the file: they only rename and delete files and folders.

With file type marks (below), a file that unfolds shows its mark while folded, and `▼` in the mark's colour while unfolded; a click on the mark unfolds it.

## File type marks

The tree shows folders with Turbo Vision's `►` and `▼`. **Options > File type marks** puts a coloured mark before each file, in the cell where a folder has its arrow, so the tree keeps its width. **Options > Plain symbols** goes back. divide remembers the choice.

![the project window with file type marks](images/project-marks.png)

| Mark | Files |
|---|---|
| `{` | Div templates (`.tpl`, `.div`) |
| `%` | dialects |
| `?` | PHP (`<?php`) |
| `:` | JSON |
| `#` | Markdown |
| `<` | HTML, XML |
| `*` | CSS |
| `;` | JavaScript |
| `@` | Python |
| `$` | shell scripts |
| `^` | images |
| `&` | `composer.json`, `composer.lock` |
| `!` | `.gitignore` |
| `-` | any other file |

The marks are plain ASCII on purpose: every terminal, font and platform draws them one cell wide, so they can never shift a line or break a frame, here or over SSH.

## Working with files

| Key | |
|---|---|
| **Ins** | new file in the folder under the cursor; `parts/menu.tpl` creates `parts/` too. The file opens. |
| **F7** | new folder; nested paths like `assets/css` are fine |
| **F2** | rename; the name without its extension comes selected. Open windows follow the file. |
| **Del** | delete, after confirming. Folders go with everything in them (divide tells you how many items). |
| **Ctrl+R** | refresh from disk |
| **Alt+F10**, **Shift+F10**, right click | the local menu with all of the above |

![creating a file](images/project-new-file.png)

Good to know:

- Deleting is permanent (nothing goes to a trash can), which is why divide always asks.
- Windows of deleted files close, except those with unsaved changes: your work stays open and can be saved again.
- A data file chosen with Run > Data file stays with its template when either is renamed.
- Names that would leave the project (`../x`) are refused.
- Files created outside divide appear with Ctrl+R; files created with Save as appear by themselves.
- After any of these operations, includes are checked again (see [[Checking Templates]]).
