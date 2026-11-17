# The Desktop

divide is a Turbo Vision desktop: a menu bar on top, overlapping windows in the middle, a status line at the bottom. If you used Turbo Pascal or Borland C++, your fingers already know it.

![Window > Tile with the project, a template and a component](images/window-tile.png)

![windows tiled, zoomed and cascaded; the themes previewed on the whole desktop](images/desktop.gif)

## Menus

**F10** opens the first menu, **Alt + the red letter** opens a menu directly (Alt+F File, Alt+R Run, Alt+T Tools, Alt+W Window…). Inside a menu, the arrows move, the red letter or **Enter** chooses, **Esc** closes. The mouse works too.

![the Run menu](images/menu-run.png)

| Menu | What is there |
|---|---|
| **File** | New, Open (F3), Save (F2), Save as, Save all, Exit (Alt+X) |
| **Edit** | Undo, Redo, Cut, Copy, Paste, Select all, Complete (Ctrl+Space) |
| **Search** | Find, Replace, Search again, Find in files (Shift+F2), Go to line, Go to included template, Outline (Ctrl+O: see [[Outline]]), Go to file (Ctrl+P), Command palette (Alt+P): see [[Finding Files and Commands]], Previous / Next error |
| **Run** | Run (Ctrl+F9: render a template, run a PHP script), Step over (F8), Trace into (F7), Step out, Go to cursor (F4), Program reset (Ctrl+F2), Parameters, Run in terminal, Web server, Check (Alt+F9), Output, Data file, Edit data, Data tree (Ctrl+T) |
| **Debug** | Evaluate (Ctrl+F4), Watches, Call stack (Ctrl+F3), Add watch (Ctrl+F7), Toggle breakpoint (Ctrl+F8): see [[Debugging PHP]]; Render trace: see [[Render Trace]] |
| **Tools** | Dialector, Translate a template, [[Composer packages\|Composer]] |
| **Window** | Project (Ctrl+B), Messages, Tile, Cascade, Zoom, Next, Previous, Close, Close all |
| **Options** | Colors (the theme and the colour depth), Language (of the interface), plain symbols or file type marks, language servers, Div engine, [[Div setup\|Div Setup]], Xdebug |
| **Help** | Contents, Books, Index (Shift+F1), Topic search (Ctrl+F1), Search (the books by words, ranked), Previous topic (Alt+F1), Using help (F1), About: see [[Help]] |

## Windows

Every window has a number on its top border (**Alt+1…9** goes to it) and, for editors, `* line:col` on the bottom border, where `*` means unsaved changes.

- **F6** / **Shift+F6** (also Ctrl+PgDn / Ctrl+PgUp): next / previous window.
- **F5**: zoom the window to the whole desktop and back.
- **Alt+F3** or **Ctrl+W**: close it (divide asks about unsaved changes).
- Drag a window by its title, resize it from a bottom corner, click `[■]` to close, `[▲]` to zoom.
- **Window > Tile** arranges every window in a grid; **Cascade** stacks them.

The scroll bars are on the border of the active window, as in Turbo Pascal: the vertical one on the right border (`▲ ▒ ■ ▼`), the horizontal one on the bottom border after the `line:col` (`◄ ▒ ■ ►`), so the text keeps the column and the row a bar inside the window would take. An arrow moves a line, a click on the track a page, and the `■` can be dragged; the focus stays in the text. Windows in the background show a plain border, and a bar only shows when there is something to scroll.

Kinds of windows: editors (templates, data, PHP, and the [[other files|Other Files]] of a project: HTML, CSS, JavaScript, Markdown, YAML, CSV…), the [[Project Window]], the Output of a render or a script, the Messages window, the Watches and Call stack windows of the [[debugger|Debugging PHP]], the log of the [[Web Server]], the data tree, the [[Dialector]] and the [[Help]] window.

## Status line

The left side shows the keys that matter. The right side tells you about the window you are in:

- in a template, `Div` (plus the dialect's name when it is not the default), or the error or warning under the cursor, or the count of problems;
- in a data file, `JSON ok` or the JSON error with its line and column;
- in any other file, its language (`Markdown`, `YAML`, `CSV`…);
- in the Output window, which template and data file were rendered, or which script ran and its exit code, and how long it took;
- while debugging, where the script is paused and the debugger's keys;
- in the project window, the dialector and the help window, their keys;
- while something runs in the background (a render, for example), a turning spinner (`|` `/` `-` `\`) and what is running.

## Dialogs

Dialogs work as in Turbo Vision: **Tab** / **Shift+Tab** go from one control to the next, **Alt + the yellow letter** jumps to a control, **Enter** presses the default button (also from an input line or a group of options), **Esc** cancels.

**File > Open** (F3) and **Save as** are laid out like Turbo Pascal's: the name line at the top, the files of the folder below it on cyan with their own scroll bar, the buttons in a column at the right, and a pane at the bottom with the folder (and its wildcard) and the file under the bar, with its size and date. Type a wildcard (`*.php`) to list other files, a folder name or `..` to go there, or a full path.

![File > Open](images/open-file.png)

### Input line history

Input lines remember what you accepted in them, as in Turbo Pascal: the `▐↓▌` at the right of a line opens the earlier entries, newest first. **↓** in the line (or a click on the arrow) opens the list, **Enter** or a click puts an entry back in the line, **Esc** closes the list. Each kind of line has its own history: file names, texts to find and to replace, line numbers, the parameters of a program, watch expressions… An entry is remembered when the dialog ends with OK, not with Cancel, and the histories are kept in the config for the next session.

![the history of the file name](images/open-history.png)

## Colours

**Options > Colors** chooses the colour theme:

| Theme | Look |
|---|---|
| **Turbo Pascal** (the default) | Turbo Vision's colours: gray menus and dialogs, blue windows, yellow text |
| **Turbo C** | the same, with Turbo C 2.01's white-on-black menu hotkeys |
| **Free Pascal** | Turbo Vision's layout in Windows Terminal's Campbell colours, as Free Pascal's IDE looks on Windows today |
| **Modern dark** | deep grays, light text and a blue accent, high contrast |

Moving through the themes with the arrows paints the whole desktop in each one (the dialog and its sample of a template too). **OK** keeps the theme, also for the next start; **Cancel** goes back to the one you had. `divide --palette modern-dark` starts with a theme without changing the one chosen. The pictures in this manual use the Free Pascal theme.

![Options > Colors, previewing Modern dark](images/colors-dialog.png)

![Modern dark](images/theme-modern-dark.png)

![Turbo Pascal](images/theme-turbo-pascal.png)

![Turbo C colours and the Window menu](images/palette-turbo-c.png)

### Colour depth

divide sends its colours as the terminal says it can show them: true colour when it announces it (`COLORTERM=truecolor`, Windows Terminal, iTerm2, most Linux terminals), the 256-colour palette otherwise (`TERM=xterm-256color`), and the 16 ANSI colours on a basic terminal. In 16 colours each colour goes to the one it stands for in its theme (a light green stays light green). The operating system plays no part, only what the terminal says.

Over ssh or inside tmux `COLORTERM` is often lost and the terminal looks like a 256-colour one. If it can do better, choose **True colour** under **Colour depth** in **Options > Colors** (it applies from the next start), or start with `divide --colors truecolor`. The dialog says what the terminal gets now.

## Language

divide speaks English and Spanish. It takes the language of the system (`LANG`, `LC_ALL`…) when it has it, English otherwise. **Options > Language** chooses another one, and divide remembers it; it applies from the next start.

![Options > Language](images/language-dialog.png)

Menus, dialogs, hints, messages and the status line are translated, with hotkeys of their own in each language (**Alt+A** opens *Archivo*, **Alt+J** opens *Ejecutar*). The keys of the commands stay the same: **F2** saves and **Ctrl+F9** runs in any language. The help follows the interface: in Spanish, the manual and Div's documentation are shown in Spanish (see [[Help#the-help-in-spanish]]).

![the Run menu in Spanish](images/interface-spanish.png)

To use another language for one run only, start with `divide --language es` (or `--language en`); the variable `DIVIDE_LANGUAGE` does the same and wins over everything else.
