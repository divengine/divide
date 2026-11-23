# Flow Designer

The **Flow Designer** draws a [Runner](https://github.com/divengine/runner) Flow as a board you work on with the keyboard:
- its Blocks as **lanes**: columns side by side in the order they are written, in two alternating colours, the first one marked **ENTRY** (where the Flow starts);
- each Block's Steps as **cards** down its lane, in the order they run;
- every `call` and `jump` as a **line** from the Step that has it to the Step it leads to.

From the board you create Blocks and Steps, rename, reorder and delete them, edit what a Step does, and connect Steps by choosing the target on the board. You never type a `block.step` target. Like the [[Flow window|Flow Structure]], it checks the Flow with Runner and runs it ([[Running Flows]]).

![The Flow Designer on the generator's generate_php_dto.yml at 120 columns: main.current selected, its jump over generation to main.verify chosen, the inspector on the right](images/flow-designer-120.png)

**The YAML file is the Flow.** The board has no model of its own. Nothing about the board, such as its layout or selection, is saved anywhere:
- The board draws the buffer of the code window that has the Flow open. The lines are worked out from the `call` and `jump` values each time.
- Each change made on the board is one edit of that buffer. Undo (Ctrl+Z), Redo (Ctrl+Y), the modified mark and F2 work as in the code.
- Typing in the code redraws the board.
- Nothing reaches the disk until you save.

## The example: a generator

The pictures on this page are of `examples/generator`, a small generator developed in divide:
- **The model:** `model/package_info.json` describes a PHP class (a DTO) and its fields.
- **The rules:** two Div templates, `templates/dto.tpl` and `templates/readme.tpl`, generate the class's source code and its README from the model.
- **The outputs:** everything is written in `build/`, and nothing outside it.
- **The Flow:** `flows/generate_php_dto.yml` orders the stages in four Blocks:

  | Block | What it does |
  |---|---|
  | `main` | Loads the model, validates it, checks whether the outputs are current, generates, verifies and writes the report |
  | `validate` | Checks the model's schema and its identifiers. If the model is not valid, it ends the run before anything is written |
  | `generate` | Renders the PHP class and the README with Div, and writes a manifest of their hashes |
  | `quality` | Runs `php -l` on the class, and checks that the outputs say what the model says |

  - `main` **calls** `validate.`, `generate.` and `quality.lint`. Each of those Blocks runs and comes back to `main`, which goes on with its next Step.
  - When the model, the templates and the outputs have not changed since the last run, `main.current` **jumps** to `.verify`. A second run without changes skips generation.

To try it:
1. Run `composer install` in `examples/generator`.
2. Run `divide examples/generator`, open `flows/generate_php_dto.yml` and use **Run > Flow designer**.
3. Press **Ctrl+F9** to run it, with `generate.json` as the initial context and `functions` as the function root.

The Output window shows the resulting context, and `build/report.json` says what the run did. The example's README has the details.

Runner is one way to order a generator's stages. This example uses it because the Designer draws Runner Flows. A generator does not need Runner or any particular pipeline: a PHP script that renders a template with Div is a generator too.

## Open it

In a Flow's code window (a YAML file whose root has `blocks`), use **Run > Flow designer**. It opens in the code's place, at the Step under the cursor.
- **Ctrl+T** goes to the code, with the selected Step or Block selected. Ctrl+T in the code comes back to the board: it reopens the Flow view you used last.
- **Ctrl+D** switches between the board and the [[Flow window|Flow Structure]]'s tree, keeping the selected Step or Block.

## The board

![The same board at 160 columns: the generator's four Blocks (main, validate, generate, quality), the calls from main to each of the others and the jump from main.current to main.verify](images/flow-designer-160.png)

- **The lanes.** Each Block is a column from the top of the window to the bottom, in a colour of its own: neighbours alternate between two colours, neither of them the window's, one darker and one lighter. The colours alone tell one Block from the next, with no frame or line between them. They stay two colours when the terminal has only 256 or 16, and in the monochrome themes they are two levels of light.
- **A lane's title** is the Block's number and id, with **ENTRY** on the first one, and its description (or how many Steps it has) under it. The titles stay at the top while the cards scroll.
- **A card** is a Step, on a surface of its own above its lane's colour. Its top edge holds its number and id, and its rows say what it does, in the order Runner does it:

  | Row | What it is |
  |---|---|
  | `IF outputs_current()` | `condition`: the Step does anything only when it returns true |
  | `SET regenerated: false` | `context`: the values the Step sets |
  | `CALL quality.lint` | `call`: go there and come back |
  | `DO render:php_class()` | `activity`, with its `module` before the colon |
  | `JUMP .verify` | `jump`: go on from there, without coming back |
  | `PAUSE` | `pause`: the Flow pauses after the Step |

  Each row's word is in its own colour and in bold. A card without any of these says *(nothing to do)*.
  - Marks on its top edge: **!E** means the Step has an error, **!W** a warning, **RO** that it is written in a way the board shows but does not edit.
  - On its bottom edge, **◄2** says how many calls and jumps lead to it.
- **The lines.** Each `call` and `jump` starts at its card's `CALL` or `JUMP` row and ends in an arrow (`►` or `◄`) at the target card. They are told apart without colour:
  - a **call** is a single line (`─ │`, port `├`) and returns to the calling Step when the called Block ends;
  - a **jump** is a double line (`═ ║`, port `╞`) and goes on from its target without returning;
  - a target the Flow does not have ends in **`?`**.

  Lines run between the lanes and between the rows of cards, never over a card. Where two lines cross, the crossing is drawn as a crossing (`┼ ╫ ╪ ╬`). A `call` or `jump` to `block.` (the Block's first Step) leads to that first Step, or to the lane's title when the Block has no Steps.
- **The selection.** The selected card (or title) is drawn in reverse video and its lines in bold. The connection you choose with Tab is drawn in reverse video too. This works the same in every theme, the monochrome phosphor themes included.

  ![The board in the Phosphor Green theme: main.validate selected, its call to validate.schema chosen, told apart by light levels alone](images/flow-designer-phosphor.png)
- **The panel**, at the right (under the board when the window is narrower than 100 columns), has three parts:
  - **at its top, what is going on**, in reverse video and only while it is so: choosing a call's or jump's target, the YAML not parsing (read-only), or Blocks and Steps not drawn;
  - **the inspector**: the selected item, as in the Flow window;
  - **under it, the Flow**: how many Blocks and Steps it has, where it starts, and what the lines mean.

  The inspector shows
  - a Step's attributes, where its call and jump lead, and the function file of its activity or condition;
  - a Block's Steps and which Steps lead into it;
  - the problems found;
  - with a connection chosen, what it is: a call or a jump, from where, to where.
- **At the bottom of the panel: Runner's verdict.**

At 80 columns the board shows two or three lanes and the inspector goes under it. Wider terminals show more lanes and wider cards. The board scrolls with the selection.

![The board at 80 columns: main.validate's call to validate.schema chosen, the panel under the board](images/flow-designer-80.png)

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
| **X** | Edit the selected Step's context, as a tree or as JSON |
| **F** | The Flow's Modules and Functions ([[Flow Functions]]) |
| **T** | Test the Step's Function: run or debug it with a JSON context ([[Flow Functions]]) |
| **S** | Simulate the Flow with test doubles, its Functions never run ([[Flow Simulation]]) |
| **Ins** | A new Step after the selected one (on a lane's title: at the end of the Block) |
| **B** | A new Block after the selected one's, with its first Step |
| **Del** | Delete the Step or Block (asked first), or remove the chosen connection |
| **Ctrl+↑ / Ctrl+↓** (Alt too) | Move the Step up or down in its Block |
| **Ctrl+← / Ctrl+→** (Alt too) | Move the Block left or right |
| **Ctrl+D** | The Flow window's tree, at the same item |
| **Ctrl+T** | The YAML, at the selected Step or Block |
| **Alt+F9** | Check the Flow, with the problems in Messages |
| **Ctrl+F9** | Run the Flow for real, its Functions with their side effects ([[Running Flows]]) |
| **F2** | Save |
| **Ctrl+Z / Ctrl+Y** | Undo / redo, the code's |

The mouse is optional: a click selects a card or a title, and a double click edits it.

## Build a Flow

A new Flow needs only an `id` and an empty `blocks:` in its YAML file. On the board:

1. **B** creates a Block. Give its id, an optional description, the id of its first Step and that Step's activity (**Down** offers the function files). It is written after the selected Block, indented like the others.
2. **Ins** adds a Step after the selected one, with the same dialog as in the Flow window: module, condition, activity, call, jump, context, pause. **Function...** there opens the Step's Function, or makes a new one for it ([[Flow Functions]]).
3. **C** (or **J**) on a Step starts a connection. The top of the panel says `CALL from main.greet` and what Enter, Del and Esc do. Move to the target card and press **Enter**: divide writes `call: check.mark`, the explicit `block.step` form. On a lane's title, Enter writes `check.`, which leads to that Block's first Step, whichever it is. **Del** instead removes the Step's call (or jump), and **Esc** cancels.
4. **Alt+F9** asks Runner to check it, **F2** saves it and **Ctrl+F9** runs it.

![Choosing the target of main.current's jump, here main.verify: the top of the panel says what Enter, Del and Esc do](images/flow-designer-connect.png)

## Edit, rename, reorder, delete

- **Enter on a Step** opens its dialog with its **id** first. Changing the id renames the Step. Every `call` and `jump` that leads to it changes with it, in the quoting each is written in, and so does `.step` written in its own Block. An activity's result is stored in the context under its Step's id, so code that reads `$context['old_id']` must change too; the dialog says so.
- **Enter on a lane's title** edits the Block: its id (a rename that changes every `call` and `jump` naming it) and its description.

  ![Editing the generate Block: its id and description](images/flow-designer-block.png)
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
- **A rename** replaces the characters of the id and of each target that names it, and nothing else. `call: 'quality.lint'   # php -l` becomes `call: 'quality.php_lint'   # php -l`.
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

A Block or Step whose id is already taken by an earlier one is not drawn, and the top of the panel names it: Runner refuses it too, so fix it in the code.

## Edit a context

**X** on a card, or **Edit context...** in the Step dialog (in the board and in the [[Flow window|Flow Structure]]), opens the Step's context as data, in two views of the same value:

![The context of main.current as a tree, with the JSON editor's item dialog adding a key](images/flow-designer-context.png)

- **Tree** (Alt+R): the [[Data Files]] tree and its item dialog (key, type, value). **Enter** edits an item, **Ins** adds one, **Del** deletes one, **Ctrl+↑ / Ctrl+↓** moves one. Objects and lists can be nested; values are strings, numbers, booleans or null.
- **JSON** (Alt+J): the same value as JSON text, in divide's code editor. Going back to the tree, or OK, reads the text again. If it is not a JSON object, you are told and stay in the text.

The dialog works on a copy: **Cancel** changes nothing. **OK** writes the context as a YAML mapping, `{regenerated: false, reason: "outputs current", stages: [lint, verify]}`:
- From **X**, it is one edit of the Flow, undone by one Ctrl+Z.
- From the Step dialog, it goes into its Context field, applied with the rest of the dialog.

A context written one key per line is changed key by key, as in the Flow window: the keys keep their order and their comments, and what cannot be changed that way is refused. A context with something divide does not read, such as a block scalar or an anchor, is edited in the code.

## When the YAML does not parse

![The YAML broken in the code: the board keeps the last design that parsed, read-only](images/flow-designer-readonly.png)

If the code stops being valid YAML (half typed, or a bracket left open), the board keeps showing **the last design that parsed** and says **READ-ONLY** at the top of the panel. The inspector lists the problems.
- Nothing on the board edits the Flow: each key that would edit says *Fix the YAML in the code first*. Your unsaved text is never touched.
- **Ctrl+T** goes to the code, at the first problem. Once the YAML parses again, the board follows it and can edit again.

## Problems

The board, the code (as marks under the text) and Messages (**Alt+F9**) show the same problems. A card or lane with an error says **!E**, and one with a warning **!W**. They are found as in the Flow window:
- Runner's own compiler, run without running anything;
- divide's lookups of missing targets, missing function files, and files that do not give Runner a callable it can call ([[Flow Functions]]).

See [[Problems|Flow Structure]].

## Limits

- The board is a design workspace, not a debugger. It does not simulate a Flow, play it back, step through it or stop it at breakpoints. Running is Runner's, through [[Running Flows]].
- Steps move only within their Block, and Blocks are created with their first Step.
- A Step's `call` and `jump` targets are chosen on the board, and its context in the context dialog. Its other attributes are edited in the Step dialog.
- The layout is fixed: lanes in the YAML's order and cards in their Steps' order. Nothing about the board is stored.
