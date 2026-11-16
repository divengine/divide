# Keyboard Reference

## Everywhere

| Key | Action |
|---|---|
| **F10** | menu bar (opens the first menu) |
| **Alt+letter** | open that menu (Alt+F, Alt+E, Alt+S, Alt+R, Alt+D, Alt+W, Alt+T, Alt+O, Alt+H; in Spanish the red letters of its menus: see [[The Desktop#language]]) |
| **F2** / **Ctrl+S** | save |
| **F3** | open a file |
| **Alt+F3** / **Ctrl+W** | close the window |
| **F5** | zoom the window |
| **F6** / **Shift+F6** | next / previous window (also Ctrl+PgDn / Ctrl+PgUp) |
| **Alt+1 … Alt+9** | go to window *n* |
| **Ctrl+B** | project window |
| **Ctrl+P** | go to file (a `>` first: the commands), see [[Finding Files and Commands]] |
| **Alt+P** | command palette |
| **Shift+F2** | find in files |
| **Ctrl+F9** | run: render the template, run the PHP script (in the debugger: go on; with the [[Web Server]] running: open the page in the browser) |
| **Alt+F5** | Output window |
| **Alt+F9** | check: progress box, then the Messages window |
| **Alt+F8** / **Alt+F7** | next / previous error |
| **Ctrl+T** | data tree ⇄ code |
| **F1** | help on the active window |
| **Shift+F1** / **Ctrl+F1** / **Alt+F1** | help index / topic search: the topic of the word under the cursor, else Help > Search with it (in PHP with a language server: what the symbol is) / previous topic |
| **Alt+X** / **Ctrl+Q** | exit |

## Editor

| Key | Action |
|---|---|
| **Ctrl+Space** | completion |
| **Ctrl+A** | select all |
| **Ctrl+O** | outline of the template or the PHP file, see [[Outline]] |
| **Ctrl+Enter** / **Ctrl+J** / Ctrl+click | go to the included template; in PHP, open the file a string names, or go to the definition (with a language server) |
| **Ctrl+F** / **Ctrl+R** | find / replace |
| **Ctrl+L** | search again |
| **Ctrl+G** | go to line |
| **Ctrl+Z** / **Ctrl+Y** | undo / redo |
| **Ctrl+X** / **Ctrl+C** / **Ctrl+V** | cut / copy / paste |
| **F7** | in a template: the [[Render Trace]]; in PHP: trace into, see below |

## Debugger (PHP)

| Key | Action |
|---|---|
| **F8** | step over (the first one starts the script; with the [[Web Server]] running, in one of its pages: the next request stops) |
| **F7** | trace into |
| **Shift+F8** | step out |
| **F4** | go to cursor |
| **Ctrl+F9** | run to the next breakpoint |
| **Ctrl+F2** | program reset |
| **Ctrl+F8** | toggle breakpoint |
| **Ctrl+F7** | add watch |
| **Ctrl+F4** | evaluate |
| **Ctrl+F3** | call stack |

## Progress box

| Key | Action |
|---|---|
| **Esc** | stop the render or the script while it runs |
| any key | close the box after the verdict (it also closes by itself: after 2 seconds on a success, 5 with warnings or errors) |

## Completion list

| Key | Action |
|---|---|
| **↑ ↓ PgUp PgDn** | move |
| **Enter** / **Tab** | insert |
| **Esc** | close |

## Project window

| Key | Action |
|---|---|
| **Enter** / double click | open a file / fold a folder (a click puts the bar on a file, and opens or folds a folder); on a member of a file, open the file there |
| **→** / **←** | unfold / fold a folder, or a file into its members (on a folded one, **←** goes up to what holds it) |
| **Ins** | new file |
| **F7** | new folder |
| **F2** | rename |
| **Del** | delete |
| **Ctrl+R** | refresh |
| **Alt+F10** / **Shift+F10** / right click | local menu |

## Data tree

| Key | Action |
|---|---|
| **Enter** | edit item |
| **Ins** | add item |
| **Del** | delete item |
| **Ctrl+↑ / Ctrl+↓** | move item |
| **Ctrl+Z / Ctrl+Y** | undo / redo |
| **F2** | save |

## Dialector

| Key | Action |
|---|---|
| **↑ ↓** | choose a section (the preview follows) |
| **Enter** / double click | edit the section |
| **Del** | section back to Div's defaults |
| **Ctrl+Z / Ctrl+Y** | undo / redo |
| **Alt+F10** / **Shift+F10** | local menu: transform, import, export, example, translate |
| **F2** | save the dialect file |

## Dialogs

| Key | Action |
|---|---|
| **Tab** / **Shift+Tab** | next / previous control |
| **Alt + yellow letter** | go to that control |
| **Enter** | the default button (also from an input line or a group of options) |
| **Esc** | cancel |
| **↓** in an input line with `▐↓▌` | its history: **↑ ↓** choose, **Enter** puts it in the line, **Esc** closes it |

In dialogs with a path, the **...** / **Browse...** button opens the file dialog. See [[The Desktop#dialogs]].

## Messages window

| Key | Action |
|---|---|
| **Enter** / double click | go to the message's place |

## Go to file and command palette

| Key | Action |
|---|---|
| letters | keep what has them, in that order |
| **↑ ↓** / **PgUp PgDn** | move the bar (the keys stay in the line) |
| `>` at the start | the commands (deleting it: the files) |
| **Enter** / double click | open the file / run the command |
| **Esc** | close |

## Find in files window

| Key | Action |
|---|---|
| **Enter** / double click | open the file at the match, selected |

## Outline window

| Key | Action |
|---|---|
| **Enter** / double click | go to the part under the bar |
| **Space** / click on **►** **▼** | fold or unfold it |
| **← / →** | fold / unfold (to the part that holds it / to the first one it holds) |

See [[Outline]].

## Watches and Call stack windows

| Key | Action |
|---|---|
| **Ins** | add a watch |
| **Del** | remove the watch under the cursor |
| **Enter** (Call stack) | show that call; Watches and Evaluate look from there |

## Render trace window

| Key | Action |
|---|---|
| **↑ / ↓** | previous / next row |
| **F8** | next row of the same parse (over sub-parses) |
| **F7** | next row (into sub-parses) |
| **Shift+F8** | out to the parse that started this one |
| **Space** | the template before / after the mutation |

See [[Render Trace]].

## Help window

| Key | Action |
|---|---|
| **Tab** / **Shift+Tab** | next / previous cross reference |
| **Enter** / click | follow it (a web page opens in the browser) |
| **Alt+F1** / **Backspace** | previous topic |
| **Esc** | close |

## Help > Search

| Key | Action |
|---|---|
| words | the sections that have them, best first |
| **↑ ↓** / **PgUp PgDn** | move the bar (the keys stay in the line) |
| **Enter** / double click | open the help at that section |
| **Esc** | close |
