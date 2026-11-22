# Flow Designer

The **Flow Designer** draws a [Runner](https://github.com/divengine/runner) Flow as a board you work on with the keyboard:
- its Blocks as **lanes**, side by side in the order they are written, the first one marked **ENTRY** (where the Flow starts);
- each Block's Steps as **cards** down its lane, in the order they run;
- every `call` and `jump` as a **line** from the Step that has it to the Step it leads to.

From the board you create Blocks and Steps, rename, reorder and delete them, edit what a Step does, and connect Steps by choosing the target on the board. You never type a `block.step` target. Like the [[Flow window|Flow Structure]], it checks the Flow with Runner and runs it ([[Running Flows]]).

![The Flow Designer on fulfil.yml at 120 columns: main.review selected, its call to review.check chosen, the inspector on the right](images/flow-designer-120.png)

**The YAML file is the Flow.** The board has no model of its own. Nothing about the board, such as its layout or selection, is saved anywhere:
- The board draws the buffer of the code window that has the Flow open. The lines are worked out from the `call` and `jump` values each time.
- Each change made on the board is one edit of that buffer. Undo (Ctrl+Z), Redo (Ctrl+Y), the modified mark and F2 work as in the code.
- Typing in the code redraws the board.
- Nothing reaches the disk until you save.

## Open it

In a Flow's code window (a YAML file whose root has `blocks`), use **Run > Flow designer**. It opens in the code's place, at the Step under the cursor.
- **Ctrl+T** goes to the code, with the selected Step or Block selected. Ctrl+T in the code comes back to the board: it reopens the Flow view you used last.
- **Ctrl+D** switches between the board and the [[Flow window|Flow Structure]]'s tree, keeping the selected Step or Block.

## The board

![The same board at 160 columns: four lanes, the call and jump lines between them](images/flow-designer-160.png)

- **The top line** says how many Blocks and Steps the Flow has, and what the lines mean.
- **A lane's title** is the Block's number and id, with **ENTRY** on the first one, and its description (or how many Steps it has) under it. The titles stay at the top while the cards scroll.
- **A card** is a Step. Its top edge holds its number and id, and its rows say what it does, in the order Runner does it:

  | Row | What it is |
  |---|---|
  | `IF needs_approval()` | `condition`: the Step does anything only when it returns true |
  | `SET approved: true` | `context`: the values the Step sets |
  | `CALL review.check` | `call`: go there and come back |
  | `DO billing:total()` | `activity`, with its `module` before the colon |
  | `JUMP .reserve` | `jump`: go on from there, without coming back |
  | `PAUSE` | `pause`: the Flow pauses after the Step |

  A card without any of these says *(nothing to do)*.
  - Marks on its top edge: **!E** means the Step has an error, **!W** a warning, **RO** that it is written in a way the board shows but does not edit.
  - On its bottom edge, **◄2** says how many calls and jumps lead to it.
- **The lines.** Each `call` and `jump` starts at its card's `CALL` or `JUMP` row and ends in an arrow (`►` or `◄`) at the target card. They are told apart without colour:
  - a **call** is a single line (`─ │`, port `├`) and returns to the calling Step when the called Block ends;
  - a **jump** is a double line (`═ ║`, port `╞`) and goes on from its target without returning;
  - a target the Flow does not have ends in **`?`**.

  Lines run between the lanes and between the rows of cards, never over a card. Where two lines cross, the crossing is drawn as a crossing (`┼ ╫ ╪ ╬`). A `call` or `jump` to `block.` (the Block's first Step) leads to that first Step, or to the lane's title when the Block has no Steps.
- **The selection.** The selected card (or title) is drawn in reverse video and its lines in bold. The connection you choose with Tab is drawn in reverse video too. This works the same in every theme, the monochrome phosphor themes included.
- **The inspector**, at the right (under the board when the window is narrower than 100 columns), shows the selected item, as in the Flow window:
  - a Step's attributes, where its call and jump lead, and the function file of its activity or condition;
  - a Block's Steps and which Steps lead into it;
  - the problems found;
  - with a connection chosen, what it is: a call or a jump, from where, to where.
- **Below the inspector: Runner's verdict.**

At 80 columns the board shows two or three lanes and the inspector goes under it. Wider terminals show more lanes and wider cards. The board scrolls with the selection.

## Keys

| Key | What it does |
|---|---|
| **↑ ↓** | The previous or next Step in the lane; ↑ from the first Step selects the lane's title (the Block) |
| **← →** | The lane to the left or right, at the same height |
| **Home / End** | The lane's title, its last Step |
| **PgUp / PgDn** | Scroll |
| **Tab / Shift+Tab** | The selected item's connections, one by one: first those it has, then those leading to it |
| **Enter** | On a chosen connection: go to its other end. On a Step: edit it. On a lane's title: edit the Block |
| **Esc** | Leave the chosen connection, or stop choosing a target |
| **Backspace** | Back to where you were before following a connection |
| **Ctrl+Enter** (Ctrl+J) | Go to the chosen connection's other end, else to the Step's call or jump target; on a Step without one, open its activity's or condition's file |
| **C / J** | Connect the selected Step with a `call` / `jump`: choose its target on the board |
| **Ins** | A new Step after the selected one (on a lane's title: at the end of the Block) |
| **B** | A new Block after the selected one's, with its first Step |
| **Del** | Delete the Step or Block (asked first), or remove the chosen connection |
| **Ctrl+↑ / Ctrl+↓** (Alt too) | Move the Step up or down in its Block |
| **Ctrl+← / Ctrl+→** (Alt too) | Move the Block left or right |
| **Ctrl+D** | The Flow window's tree, at the same item |
| **Ctrl+T** | The YAML, at the selected Step or Block |
| **Alt+F9** | Check the Flow, with the problems in Messages |
| **Ctrl+F9** | Run the Flow ([[Running Flows]]) |
| **F2** | Save |
| **Ctrl+Z / Ctrl+Y** | Undo / redo, the code's |

The mouse is optional: a click selects a card or a title, and a double click edits it.

## Build a Flow

A new Flow needs only an `id` and an empty `blocks:` in its YAML file. On the board:

1. **B** creates a Block. Give its id, an optional description, the id of its first Step and that Step's activity (**Down** offers the function files). It is written after the selected Block, indented like the others.
2. **Ins** adds a Step after the selected one, with the same dialog as in the Flow window: module, condition, activity, call, jump, context, pause.
3. **C** (or **J**) on a Step starts a connection. The top line says `CALL from main.greet: choose the target...`. Move to the target card and press **Enter**: divide writes `call: check.mark`, the explicit `block.step` form. On a lane's title, Enter writes `check.`, which leads to that Block's first Step, whichever it is. **Del** instead removes the Step's call (or jump), and **Esc** cancels.
4. **Alt+F9** asks Runner to check it, **F2** saves it and **Ctrl+F9** runs it.

![Choosing the target of stock.short's jump: the top line says what Enter, Del and Esc do](images/flow-designer-connect.png)

## Edit, rename, reorder, delete

- **Enter on a Step** opens its dialog with its **id** first. Changing the id renames the Step. Every `call` and `jump` that leads to it changes with it, in the quoting each is written in, and so does `.step` written in its own Block. An activity's result is stored in the context under its Step's id, so code that reads `$context['old_id']` must change too; the dialog says so.
- **Enter on a lane's title** edits the Block: its id (a rename that changes every `call` and `jump` naming it) and its description.

  ![Editing the stock Block: its id and description](images/flow-designer-block.png)
- **Ctrl+↑ / Ctrl+↓** moves a Step in its Block, which changes the order its Steps run in.
  - Moving a Step to the first place, or away from it, changes what `block.` leads to. If any `call` or `jump` is written that way, you are asked first.
  - A Step stays in its Block. To move a Step to another Block, cut and paste it in the code.
- **Ctrl+← / Ctrl+→** moves the Block. The first Block is where the Flow starts, so moving a Block into the first place, or out of it, is asked first, naming the new entry Block.
- **Del** deletes the selected Step or Block, after saying:
  - which Steps lead to it with a `call` or `jump`;
  - that the Flow will start elsewhere, when it is the entry Block;
  - how many comments are written in it.

  Deleting removes those `call` and `jump` lines too, in the same edit. One Ctrl+Z brings everything back. A Flow keeps at least one Block.
- **Del on a chosen connection** (Tab first) removes that `call` or `jump`.

Each of these is one edit: one Ctrl+Z undoes it, references and all.

### Only what must change is written

The board changes the YAML text in place, as the Flow window does ([[Only what you change is written|Flow Structure]]). It never writes the file again from a model:
- **A move** swaps two neighbouring Steps (or Blocks) text for text. Each keeps its lines exactly as written: its comments, the comment lines right above it, quotes and blank lines inside it. The blank lines and comments between the two stay where they were.
- **A rename** replaces the characters of the id and of each target that names it, and nothing else. `call: 'review.check'   # back here` becomes `call: 'review.inspect'   # back here`.
- **A new Block or Step** is new lines, indented like its siblings (two spaces, four...).
- **A deletion** removes the item's own lines, with the comment lines right above it. Each `call` or `jump` that led to it loses only its own line.

divide reads the result again before keeping it. If anything else would change (another value, a Block's order, a comment that is not the deleted item's own), the edit is undone and you are told.

**What is refused**, with a message saying why and nothing changed. You make these in the code (Ctrl+T):
- removing a `call` or `jump` line that has a comment on it;
- removing the only thing a Step does: a Step left empty is not a valid Step, so change or delete that Step first;
- moving two items that are indented differently, or that have something else written on the same line as their key;
- renaming to an id that the Flow already has, or that starts with `_` or has a dot (Runner's rules for ids);
- deleting the only Block;
- renaming or deleting while a Block's Steps are written in flow style (`steps: {a: {jump: main.s}}`): a `call` or `jump` there could not be followed.

A Block or Step whose id is already taken by an earlier one is not drawn, and the top line names it: Runner refuses it too, so fix it in the code.

## When the YAML does not parse

![The YAML broken in the code: the board keeps the last design that parsed, read-only](images/flow-designer-readonly.png)

If the code stops being valid YAML (half typed, or a bracket left open), the board keeps showing **the last design that parsed** and says **READ-ONLY** on its top line. The inspector lists the problems.
- Nothing on the board edits the Flow: each key that would edit says *Fix the YAML in the code first*. Your unsaved text is never touched.
- **Ctrl+T** goes to the code, at the first problem. Once the YAML parses again, the board follows it and can edit again.

## Problems

The board, the code (as marks under the text) and Messages (**Alt+F9**) show the same problems. A card or lane with an error says **!E**, and one with a warning **!W**. They are found as in the Flow window:
- Runner's own compiler, run without running anything;
- divide's lookups of missing targets and missing function files.

See [[Problems|Flow Structure]].

## Limits

- The board is a design workspace, not a debugger. It does not simulate a Flow, play it back, step through it or stop it at breakpoints. Running is Runner's, through [[Running Flows]].
- Steps move only within their Block, and Blocks are created with their first Step.
- A Step's `call` and `jump` targets are chosen on the board. Its other attributes are edited in the Step dialog. A `context` is one line there, `{key: value, ...}`.
- The layout is fixed: lanes in the YAML's order and cards in their Steps' order. Nothing about the board is stored.
