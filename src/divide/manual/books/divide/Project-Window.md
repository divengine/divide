# Project Window

**Ctrl+B** opens the project tree on the left (and raises it, or closes it when it is already on top). It opens by itself when divide starts with a folder and no files. Without a folder, Ctrl+B offers to open one (**File > Open folder**).

![the local menu of the project window](images/project-menu.png)

**Enter** opens a file, or folds and unfolds a folder. **→** unfolds a folder (or a file, below) and **←** folds it, or goes up to the folder that holds the bar. With the mouse, a click puts the bar on a file and a double click opens it; a click on a folder folds or unfolds it. Version control and cache folders (`.git`, `__pycache__`, `.venv`, `node_modules`, tool caches) are hidden; `vendor/` stays visible.

Type with the tree focused and only the files and folders whose name holds it stay, from the whole project, also from folders you never opened (see [[The Desktop#filtering-a-list-or-a-tree]]). **Esc** empties the filter.

![the project window: a folder unfolded, a new file, the file type marks](images/project.gif)

In a git repository each changed file has a letter after its name (`M`, `A`, `?`...), a folder holding changes has `•`, ignored files are dimmed, and the bottom border shows the branch: see [[Git]].

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
| **F2** | rename; the name without its extension comes selected. A path moves it too: `../name`, `parts/name`. Open windows follow the file. |
| **Del** | delete, after confirming. Folders go with everything in them (divide tells you how many items). |
| **Ctrl+R** | refresh from disk (changes made outside divide show by themselves; see below) |
| **Ctrl+X**, **Ctrl+C**, **Ctrl+V** | cut, copy, paste (see Moving files and folders, below) |
| **Alt+F10**, **Shift+F10**, right click | the local menu with all of the above |

![creating a file](images/project-new-file.png)

Good to know:

- Deleting is permanent (nothing goes to a trash can), which is why divide always asks.
- Windows of deleted files close, except those with unsaved changes: your work stays open and can be saved again.
- A data file chosen with Run > Data file stays with its template when either is renamed.
- Names and paths that would leave the project are refused.
- After any of these operations, includes are checked again (see [[Checking Templates]]).

## Changes made outside divide

Files and folders created, deleted, renamed or moved by other programs show in the project window by themselves, usually within half a second. That covers git, Composer, a generator, a shell, or another editor. A file moved from one open folder to another leaves the first and appears in the second.

- **What is watched**: the project's folder and the folders you have open in the tree, each one on its own, not their subfolders. A closed folder is read when you open it, so it always shows what it holds then.
- **Your place stays**: the bar stays on the same file, open folders stay open, the view does not scroll, and a filter you typed stays.
- **Nothing is polled**: divide uses the system's own notifications (inotify on Linux, FSEvents on macOS, directory-change notifications on Windows). Nothing happens while nothing changes. A burst of changes, such as a checkout or a `composer install`, is gathered and each affected folder is read once.
- **Open editors are not touched**: a file changed outside divide does not reload its editor window, so unsaved changes are never overwritten.
- **Limits**:
  - At most 64 folders are watched at a time. With more open, divide says so, and the rest refresh with **Ctrl+R**.
  - If the system refuses to watch a folder, divide says so once, and **Ctrl+R** refreshes. That happens when the inotify limits are reached on Linux (`fs.inotify.max_user_watches`, `max_user_instances`), or on a filesystem without notifications, such as many network shares, SSHFS, some Docker volumes and WSL's view of Windows drives.
  - Over SSH nothing changes: divide watches the machine it runs on.

## Moving files and folders

![cut and paste, Move to... and a drag onto a folder](images/moving.gif)

Three ways, whichever comes first to hand:

- **Cut and paste.** **Ctrl+X** on a file or a folder cuts it: it stays dim in the tree until it goes somewhere. **Ctrl+V** with the bar on a folder moves it into that folder; on a file, into that file's folder. **Esc** forgets what was cut.
- **Copy and paste.** **Ctrl+C** copies, **Ctrl+V** pastes a copy; what was copied can be pasted again, in as many folders as you like. Pasted in its own folder, the copy is called `name copy` (`name copy 2`...).
- **Move to...** in the local menu (**Alt+F10**): type a folder of the project or choose it with **Browse**; a folder that does not exist yet is made. **F2** does the same with a path: `../card.tpl`, `parts/card.tpl`.
- **With the mouse.** Drag a file or a folder onto a folder: the folder lights up as you go, and the tree scrolls when you reach its top or bottom. When you let go, divide asks before moving it, since a drag in a terminal is easy to slip. **Esc** during a drag cancels it. Your terminal has to report the mouse moving with the button held (most do).

The local menu and **Edit > Cut / Copy / Paste** do the same when the project window is the active one.

Good to know:

- A folder never goes inside itself, and two folders are never merged: if a folder with that name is already there, divide says so and does nothing.
- A file with that name already there is replaced only after asking. A file with unsaved changes open in a window is never replaced.
- Open windows, the data file chosen for a template, and breakpoints follow what moved; the bar follows it too.
- Moving never leaves the project.
