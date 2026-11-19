# Keyboard Reference

## Everywhere

| Key | Action |
|---|---|
| **F10** | menu bar (opens the first menu) |
| **Alt+letter** | open that menu (Alt+F, Alt+E, Alt+S, Alt+R, Alt+D, Alt+W, Alt+T, Alt+O, Alt+H; in Spanish the red letters of its menus: see [[The Desktop#language]]) |
| **F2** / **Ctrl+S** | save |
| **F3** | open a file (File > Open folder: a folder) |
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

## Lists and trees

Every tree and list has a filter line above it, see [[The Desktop#filtering-a-list-or-a-tree]].

| Key | Action |
|---|---|
| a letter, a digit, a sign | add it to the filter: only the items that hold it stay (upper or lower case alike) |
| **Backspace** | take a letter back |
| **Esc** | empty the filter (with an empty filter, Esc does what it always does) |

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
| **F2** | rename (a path moves it: `../name`) |
| **Del** | delete |
| **Ctrl+X** / **Ctrl+C** / **Ctrl+V** | cut / copy / paste in the folder under the bar (**Esc** forgets what was cut) |
| drag onto a folder | move there, after asking |
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

## Composer window

| Key | Action |
|---|---|
| **Ins** | add a package |
| **Del** | remove the package |
| **Enter** / double click | its folder in the project window (on a group or a vendor: fold or unfold) |
| **Space** / **→** / **←** | fold / unfold a group or a vendor |
| **Ctrl+R** | read composer.json and composer.lock again |
| **Alt+F10** / **Shift+F10** | local menu: update, install, newer versions, validate, autoloader, new composer.json |

See [[Composer]].

## Welcome window

| Key | Action |
|---|---|
| **Enter** / double click | do it: a new file, open a file or a folder, the help; open the recent folder or file |
| **Del** | take a recent folder or file off its list |
| typing | filter the rows |

See [[The Desktop#a-folder-a-file-or-nothing]].

## Git windows

| Key | Action |
|---|---|
| **Space** | Changes: stage or unstage the file (a conflict: mark it solved) |
| **Enter** | Changes: open the file · History: the commit's diff · Branches: switch to it (a stash: bring it back) · Pull requests and issues: open in the browser |
| **Del** | Changes: discard the file's changes · Branches: delete the branch, drop the stash |
| **Ins** | Branches: a new branch · Pull requests and issues: a new pull request (on the issues, a new issue) |
| **Ctrl+K** | Changes: commit |
| **Tab** | Changes: to the diff and back |
| **Ctrl+R** | read again |
| **Alt+F10** / **Shift+F10** | local menu: stage everything, amend, stash, merge, new branch here, copy the hash, pull, push, fetch... |
| **Ctrl+Enter** | in the commit message: commit |

In a diff: **N** / **P** the next / previous change, **S** side by side or unified, **← →** scroll a long line, **Enter** open the file at that line. In Blame: **Enter** the commit of the line.

See [[Git]].

## Div setup window

| Key | Action |
|---|---|
| **↑ ↓** | choose a section (its settings in effect show beside) |
| **Enter** / double click | edit the section |
| **Del** | the section back to Div's defaults |
| **Ctrl+Z / Ctrl+Y** | undo / redo |
| **Ctrl+T** | the setup file as JSON |
| **Alt+F10** / **Shift+F10** | local menu: user's or project's setup, JSON, dialect, trust, check with Div |
| **F2** | save the setup file |

See [[Div Setup]].

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
