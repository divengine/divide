# Project Window

**Ctrl+B** opens the project tree on the left (and raises it, or closes it when it is already on top). It opens by itself when divide starts without files.

![the local menu of the project window](images/project-menu.png)

**Enter** opens a file, or folds and unfolds a folder. Version control and cache folders (`.git`, `__pycache__`, `.venv`, `node_modules`, tool caches) are hidden; `vendor/` stays visible.

## Icons

The tree shows folders with Turbo Vision's `▸` and `▾`. **Options > Nerd Font icons** adds an icon for each folder and file type: Div templates, dialects, PHP, JSON, Markdown, HTML, `composer.json`… **Options > Plain symbols** goes back. divide remembers the choice.

The icons are glyphs of the [Nerd Fonts](https://www.nerdfonts.com/), fonts patched with icons. The terminal must use one of them (JetBrains Mono Nerd Font, FiraCode Nerd Font…); with an ordinary font they show as boxes, which is why they are off by default.

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
