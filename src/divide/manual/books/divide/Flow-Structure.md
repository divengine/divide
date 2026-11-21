# Flow Structure

The **Flow window** shows a [Runner](https://github.com/divengine/runner) Flow as what it is made of: its Blocks, each with its Steps, and what each Step does (`condition`, `activity`, `module`, `call`, `jump`, `context`, `pause`). From it you can edit a Step, add one or delete one, go to a `call` or `jump` target, open an activity's file, check the Flow with Runner, and run it ([[Running Flows]]). Everything is done with the keyboard.

![The Flow window on order.yml: Blocks and Steps on the left, the selected Step on the right, Runner's verdict below](images/flow-window.png)

**The YAML file is the Flow.** The window has no model of its own and nothing is saved besides the YAML. It shows the buffer of the code window that has the Flow open, and each change made in it is an edit of that buffer:
- Undo (Ctrl+Z), Redo (Ctrl+Y), the modified mark and F2 work as in the code.
- Typing in the code updates the window.
- Nothing reaches the disk until you save.

## Open it

A Flow is a YAML file (`.yml`, `.yaml`) whose root has `blocks`. In its code window, **Ctrl+T** (Run > Flow structure) opens the Flow window in the code's place, at the Step under the cursor. Ctrl+T again goes back to the code, with the selected Step or Block selected there. On other YAML files Ctrl+T does nothing; on JSON it is the [[Data Files]] tree.

## The window

- **Left: the tree.** The Flow, its Blocks in the order they are written (the first one is where the Flow starts), and each Block's Steps with what they do: `activity compute_total`, `call -> review.check`, `condition needs_approval, context, pause`. A Step or Block with a problem has a **!** in front. Typing filters the tree.
- **Right: the selected item.**
  - For a Step: its attributes, its line, where a `call` or `jump` leads (`-> Block review, Step check (line 14)`), the file an activity or condition comes from (`-> functions/needs_approval.php`), and its problems.
  - For a Block: its Steps, and which Steps call or jump into it.
  - For the Flow: its id, description, Blocks and Steps.
- **Below: Runner's verdict.** Either "the Flow compiles", or Runner's message, with the number of errors and warnings.

## Keys

| Key | What it does |
|---|---|
| **↑ ↓** | Move in the tree |
| **← →** | Close or open a Block; ← from a Step goes up to its Block, → from an open Block into its first Step |
| **Enter** | Edit the Step (on a Block: open or close it) |
| **Ins** | A new Step after the selected one (on a Block: at its end) |
| **Del** | Delete the Step (asked first, saying which Steps lead to it) |
| **Ctrl+Enter** (Ctrl+J) | Go to the `call` or `jump` target; on a Step without one, open its activity's or condition's file |
| **Ctrl+T** | The YAML, at the selected Step or Block |
| **Alt+F9** | Check the Flow, with the problems in Messages |
| **Ctrl+F9** | Run the Flow ([[Running Flows]]) |
| **F2** | Save |
| **Ctrl+Z / Ctrl+Y** | Undo / redo, the code's |

## Edit a Step

**Enter** opens the Step's attributes:

![The Step dialog of approval.ask](images/flow-step.png)

- **Module**: the folder the activity and condition come from (optional).
- **Condition**: a function; the Step runs only when it returns true.
- **Activity**: the function that does the work.
- **Call** `block.step`: go there and come back. **Jump** `block.step`: go on from there. An empty Block (`.step`) means the Step's own Block; an empty Step (`block.`) means the Block's first Step.
- **Context**: values the Step sets, as a mapping, `{approved: true, by: ana}`.
- **Pause**: pause the Flow after the Step.

**Down** in a field offers what the project already has:
- the function files of the function root (or of the Module's folder) for the activity and the condition;
- the Module folders;
- the Flow's `block.step` targets for call and jump.

**An empty field removes the attribute.** **Ins** opens the same dialog with a **Step id** first. The new Step is written after the selected one, with the indentation of its siblings.

### Only what you change is written

divide changes the YAML text in place. It never writes the file again from a model:
- **A changed value** replaces only the value. A comment after it on the same line stays: `activity: compute_total   # sums` becomes `activity: compute_sum   # sums`.
- **A new attribute** is one new line after the Step's last one, indented like the others.
- **A removed attribute** removes only its lines. Comments on lines of their own stay.
- **A context written as a block** (one key per line) stays a block.
- **Everything else** stays exactly as you wrote it: comments, the order of the keys, blank lines, quotes, indentation, and keys divide does not know.
- **Quotes:** a value is written plain when YAML reads it back as the same text. Otherwise it is double-quoted: `true`, `12`, `a: b`, `x #y`, `Class::run`.

All the changes of one dialog are one edit: one Ctrl+Z undoes them. divide reads the result again before keeping it. If the Step does not hold exactly what you asked for, the edit is undone and you are told.

### What is edited in the code

Some things cannot be changed in place, so the window shows them but does not edit them. It says why, and Ctrl+T takes you to them:
- a Step written in flow style (`after: {jump: main.receipt}`): its tree line says *(read-only)*;
- a Step or attribute with an anchor, an alias or a tag;
- an attribute written as a block scalar (`|`, `>`);
- a Flow file with several YAML documents.

**When the YAML does not parse**, the tree says *[YAML errors]*, the window edits nothing, and the problem is in Messages and under the code. The file stays as it is until you fix it in the code.

## Problems

![A call to a Step that does not exist and an activity without its file: in the tree, the selected Step and Messages](images/flow-problems.png)

The window, the code (as marks under the text) and Messages (**Alt+F9**; **Alt+F8**/**Alt+F7** go through them, Enter goes to the line) show the same problems.

**Runner's own compiler checks the Flow.** divide asks the Runner installed in the project (Runner 0.2.0 or newer, see [[Running Flows]]) to compile the Flow, without running it:
- Runner's parser and its schema: unknown keys such as `activty:`, wrong types, Module names.
- Its resolution of `call` and `jump` targets.
- Only Runner's source file is loaded, not your project's code. **No condition and no activity runs.**

Runner stops at its first error, so divide also looks up two things itself, to mark every place at once:
- **Targets**: a `call` or `jump` to a Block or Step that is not in the file.
- **Function files**: an activity or condition whose file is not where Runner's importer would look for it. That is:
  - with a Module: `<module folder>/<name>.php`, where the folder is the context's `_modules` entry, else `<function root>/<module>`;
  - without one: `<function root>/<name>.php`, else `<name>.php`.

  A missing Module function is an error. A missing plain one is an error unless PHP has a function of that name, such as `strlen`. When divide cannot tell, it is a warning, because Runner then tries the name as a PHP callable.

The function root and the Modules are the ones the [[Run Flow dialog|Running Flows]] would give Runner: its **Function root**, else the `_root_folder` of its **Initial context**, else the project's folder; the Modules come from the context's `_modules`. Run > Parameters changes them.

Without Runner installed, the verdict says so and only divide's own lookups are made.

## Run the edited Flow

**Ctrl+F9** in the Flow window opens the [[Run Flow dialog|Running Flows]] for that Flow, as in its code. A modified Flow is saved first, then Runner runs the file.

## Limits

- The window edits Steps: their attributes, adding and deleting them. Blocks are added, renamed and reordered in the code, and so is a Step's id.
- It shows the structure as a tree, not as a diagram. It does not simulate a Flow, play it back, step through it, or stop it at breakpoints. Running is Runner's, through [[Running Flows]].
- Function files are found by name and only checked for existence. divide never loads them. Whether they return what Runner expects is found out when the Flow runs.
