# Finding Files and Commands

Three ways to get somewhere without the menus or the project tree: **Go to file** opens a file by typing a few letters of its name, the **command palette** runs any menu entry the same way, and **Find in files** looks for a text in every file of the project.

## Go to file

**Ctrl+P** (or **Search > Go to file**) opens a line to type in, with the project's files below it. Type a few letters of the name and the list keeps the files that have them, in that order, best first. The letters you typed show up highlighted, and the folders are dimmed so the file names stand out.

![Go to file](images/go-to-file.png)

- The letters do not have to be next to each other: `phd` finds `parts/header.tpl`. A file whose name has them, at the start of its words or one after another, comes first.
- With nothing typed, the files open in editors come first, the one on top first.
- **↑ ↓** (and **PgUp PgDn**) move the bar while you keep typing. **Enter** or a double click opens the file, **Esc** closes.
- When the project is a git repository, the list is git's own: the tracked files and the new ones git does not ignore. Otherwise it holds every file except the folders the [[Project Window]] hides (`.git`, `node_modules`, `.venv`, caches).

## Command palette

**Alt+P** (or **Search > Command palette**) holds every entry of the menu bar, named by its menu (`Run > Check`), with its key on the right. It works like Go to file: type a few letters and **Enter** runs the command, as if you had chosen it in the menu.

![the command palette](images/command-palette.png)

- A `>` at the start of the line in Go to file turns it into the command palette, and deleting the `>` goes back to the files.
- VS Code opens its palette with Ctrl+Shift+P, but Windows Terminal keeps that key for its own palette, and many terminals send it as Ctrl+P. That is why divide uses Alt+P. Where the terminal does pass Ctrl+Shift+P on, it works too.
- With nothing typed, the commands you ran from the palette most recently come first.

## Find in files

**Search > Find** looks in the file you are editing. **Search > Find in files** (**Shift+F2**, the key of Borland Pascal's Tools > Grep) looks in all of the project's files: the same list as Go to file. VS Code's Ctrl+Shift+F is Windows Terminal's own find, so it is only an alternative, for the terminals that pass it on.

![Find in files](images/find-in-files-dialog.png)

- **Text to find**: what to look for. When text is selected on one line, it is filled in.
- **Files**: which files to look in, with wildcards separated by `;` (`*.tpl;*.php`). Leave `*` for all of them. A wildcard can include folders too: `components/*`.
- **Options**: case sensitive, whole words only and regular expression, as in **Find**.

Both lines remember what you typed in them (see [[The Desktop#input-line-history]]). The files open in editors are searched as they are, saved or not. Binary files and files over 2 MB are skipped.

What it finds goes to the **Find in files** window at the bottom of the desktop, as Turbo Pascal's grep put it in the Messages window. The first line says how many matches it found and in how many files. Then there is one row per line with a match: `file(line): the line`. **Enter** or a double click opens the file there, with the match selected. Running another search replaces the list.

![the Find in files window](images/find-in-files.png)
