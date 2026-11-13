# The Desktop

divide is a Turbo Vision desktop: a menu bar on top, overlapping windows in the middle, a status line at the bottom. If you used Turbo Pascal or Borland C++, your fingers already know it.

![Window > Tile with the project, a template and a component](images/window-tile.png)

## Menus

**F10** opens the first menu, **Alt + the red letter** opens a menu directly (Alt+F File, Alt+R Run, Alt+T Tools, Alt+W Window…). Inside a menu, the arrows move, the red letter or **Enter** chooses, **Esc** closes. The mouse works too.

![the Run menu](images/menu-run.png)

| Menu | What is there |
|---|---|
| **File** | New, Open (F3), Save (F2), Save as, Save all, Exit (Alt+X) |
| **Edit** | Undo, Redo, Cut, Copy, Paste, Select all, Complete (Ctrl+Space) |
| **Search** | Find, Replace, Search again, Go to line, Go to included template, Previous / Next error |
| **Run** | Render (Ctrl+F9), Check (Alt+F9), Output, Data file, Edit data, Data tree (Ctrl+T) |
| **Tools** | Dialector, Translate a template |
| **Window** | Project (Ctrl+B), Messages, Tile, Cascade, Zoom, Next, Previous, Close, Close all |
| **Options** | colour palette, Div engine |
| **Help** | Contents, Index (Shift+F1), Topic search (Ctrl+F1), Previous topic (Alt+F1), Using help (F1), About: see [[Help]] |

## Windows

Every window has a number on its top border (**Alt+1…9** goes to it) and, for editors, `* line:col` on the bottom border, where `*` means unsaved changes.

- **F6** / **Shift+F6** (also Ctrl+PgDn / Ctrl+PgUp): next / previous window.
- **F5**: zoom the window to the whole desktop and back.
- **Alt+F3** or **Ctrl+W**: close it (divide asks about unsaved changes).
- Drag a window by its title, resize it from a bottom corner, click `[■]` to close, `[▲]` to zoom.
- **Window > Tile** arranges every window in a grid; **Cascade** stacks them.

Kinds of windows: editors (templates, data, any text file), the [[Project Window]], the Output of a render, the Messages window, the data tree, the [[Dialector]] and the [[Help]] window.

## Status line

The left side shows the keys that matter. The right side tells you about the window you are in:

- in a template, `Div` (plus the dialect's name when it is not the default), or the error or warning under the cursor, or the count of problems;
- in a data file, `JSON ok` or the JSON error with its line and column;
- in the Output window, which template and data file were rendered, and how long it took;
- in the project window, the dialector and the help window, their keys.

## Colours

Turbo Pascal's palette (yellow on blue) is the default. **Options** switches to Turbo C's; start with `divide --palette turbo-c` to make it the first one.

![Turbo C colours and the Window menu](images/palette-turbo-c.png)
