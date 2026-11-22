# Flow Functions

A Step of a [Runner](https://github.com/divengine/runner) Flow does its work through **Functions**: its `condition` and its `activity` name them. A Function is a PHP file that returns a callable, and Runner calls it with the Flow's shared context:

```php
<?php

declare(strict_types=1);

return function (array &$context): mixed {
    $context['seen'] = true;   // what you set in the context stays for the next Steps
    return 'done';             // an activity's result: Runner keeps it in $context[<the Step's id>]
};
```

- A **condition** returns true or false: true runs the Step's activity, call or jump, and false skips them.
- An **activity** does the work. What it returns is kept under the Step's id.
- A **Module** is a folder of Functions, named by a Step's `module`. It applies to the Step's condition and activity, not to its call or jump. A Module is not a Block, and a Function is not a Step.
- Inside, a Function is ordinary PHP: Composer's autoload, `require` of other files, and other Functions through Runner's importer, `$context['_importer']('name', 'module')`, which returns that Function's callable.

The **Functions window** shows where a Flow's Functions are, the Modules and the Functions in each, which Steps use each one and which references lead nowhere. From it, and from the Step dialog, you make Modules and Functions without writing the folders or the `return function (...)` yourself. The files are ordinary PHP files, opened in the [[PHP editor|Editing PHP]], with its lint, language server and [[debugger|Debugging PHP]].

## Open it

- **F** on the [[Flow Designer]]'s board.
- **Run > Flow functions**, from a Flow's code, its [[Flow window|Flow Structure]] or its board: the window of that Flow. From anywhere else: the project's.

The window has the Functions as a tree on the left and what the selected item is on the right. At 80 columns, the right part goes under the tree.

| Row | What it is |
|---|---|
| **Function root** `functions/` | The root, and where it comes from (see below). Under it, the Functions of the root: `load_model` is `functions/load_model.php` |
| **`render/`** | A Module: `render:php_class` is `functions/render/php_class.php`. A Module mapped elsewhere shows `-> its folder`; one outside the project, **(outside: read-only)** |
| **`php_class`** `activity · 1 Step(s)` | A Function, how the Steps use it, and how many. **→** unfolds the Steps |
| **! Not found** | The references of Steps that resolve to no file. **?**: an unqualified name Runner may still find as a PHP callable (`strlen`, `ns\fn`, `Cls::method`) |

On the right, for a Function:
- its file and Module;
- what the file returns, read without running it: a closure and its parameters, an arrow function, or another callable, which is not read further;
- the Steps that use it (`main.load (activity)`), in every Flow of the project, the open ones as they are in their editor, unsaved changes included;
- the Functions it imports with `$context['_importer']('lint', 'quality')` and those that import it. An import whose name is computed is shown as `?`, unknown, never as a problem;
- what Runner could not do with it (see Problems).

On the root's row, the contract above and where Runner looks.

## Keys

| Key | What it does |
|---|---|
| **↑ ↓ ← →** | Move, fold, unfold |
| **Enter** | On a Function: open it in the PHP editor, at its `return`. On a Step: that Step in the Flow Designer. On a missing reference: make it (below). On a Module: fold or unfold |
| **Ins** | A new Function, in the Module under the cursor (else in the root) |
| **Shift+Ins** | A new Module |
| **Alt+F10** (Shift+F10) | The window's menu: Function..., Module..., Settings (`.div/runner.json`) |
| **Ctrl+R** | Read the disk again (also done when a PHP file, a Flow or the settings are saved) |
| typing | Filter the rows |

## Make a Module

**Shift+Ins** asks for its name: letters, digits, `_` and `-`, as Runner's `module` allows. It is made as a folder of the root (`functions/publish/`), or as the folder `_modules` gives it. A Module that is already there is not made again.

## Make a Function

**Ins** opens **New Function**:
- **Module**: the Module (**Down** offers the ones there are). Empty: the root.
- **Name**: letters, digits, `_` and `-`. In a Module, also `folder/name` (`tax/compute`), as Runner allows. Without `.php`: Runner adds it.
- **Use**: **Activity** or **Condition**.

Under them, the dialog says where the file will be and what a Step will say to use it (`module: render, activity: slug`), or why it cannot be made. **OK** writes the file, making its folders if they are not there, and opens it in the PHP editor at its callable.

The file is a minimal, valid PHP 8.1 Function: a condition returns `bool` (`true`), an activity returns `mixed` (`null`), each with a comment that says what the context and the return value are. It is a start, not a form to keep: write any PHP there. divide never rewrites a Function, generated or not.

What is never done:
- writing over a file that is there (open it instead);
- writing outside the project, in Composer's `vendor` folder or in a hidden folder. A Module mapped there is shown, and is read-only here;
- running a Function's PHP to list or read it.

**Enter on a missing reference** opens the same dialog with its Module, its name and its use filled in. The Step already names it, so the Flow does not change.

## From a Step

In the Step dialog (Enter on a card, Ins for a new Step, in the Flow Designer and in the Flow window):
- **Down** on Module offers the Modules, and on Condition or Activity the Functions of that Module (or of the root).
- **Function...** is about the Step's activity, or its condition when that is the field you were in:
  - **Open**: its file in the PHP editor, once the Step is written (as **OK**).
  - **New...**: the New Function dialog, with the Step's Module. Its **OK** fills the Step's `module` and `activity` (or `condition`) and says that the file will be made. Nothing is written yet: the Step dialog's **OK** writes the Step, as one edit of the YAML (one Ctrl+Z), makes the file and opens it. **Cancel** writes and makes nothing. If the Step cannot be written, the new file is removed.

A Step has one `module`, for both its condition and its activity: a new Function in another Module than the Step's other Function is refused.

**Ctrl+Enter** on a Step (on the board, in the Flow window or on its line in the code) opens its Function's file. When there is none, it says where Runner looked.

## Where Runner looks

The root and the Modules' folders are Runner's rules, the same as a run's ([[Running Flows]]). The first that gives one counts:

| | |
|---|---|
| **The root** | the Run Flow dialog's **Function root** (`--root`); else the initial context's `_root_folder`; else the project's `.div/runner.json` `root`; else the project's folder (Runner's own default, `./`) |
| **A Module's folder** | the initial context's `_modules`; else `.div/runner.json` `modules`; else `<root>/<module>` |
| **An unqualified name** | `<root>/<name>.php`; else `<name>.php` from the project's folder; else a PHP callable of that name |

With a `module`, Runner looks only in that Module's folder: the same name in two Modules is two Functions, and a root Function of that name is a third.

## The project's settings: .div/runner.json

Without anything else, the Run Flow dialog's fields are remembered per Flow and per user. For a project whose Functions are always in the same folder, `.div/runner.json` says it once, for everyone who clones the project:

```json
{
    "root": "functions",
    "modules": {"shared": "../shared/functions"}
}
```

- Both keys are optional, and the file too. Paths are relative to the project.
- It is the project's default, under what a Flow or a context says (above). The context stays the Flow's business input: nothing has to be in it for divide to find the Functions.
- A run gives Runner what the file adds: its `root` as `--root` when neither the Flow nor the context gives one, and its `modules` added to the context's `_modules`, where the context does not map them. Runner itself does not read the file.
- **Alt+F10 > Settings** makes it, after asking, with the root the window shows now, and opens it.
- `examples/generator` has one: `"root": "functions"`.

## Problems

What the window marks with **!** is also marked in the Flow, at the Step's `activity` or `condition`, in the code, on the board and in Messages (**Alt+F9**):
- a reference with no file where Runner looks (an error, or a warning when Runner may still find a PHP callable of that name);
- a file that returns nothing (no `return` at its top level): Runner needs a callable;
- a closure that needs more than one argument (Runner passes only the context), or whose first parameter is typed as something else than an array.

Only the window says, as a note, that a closure takes the context by value (`array $context`). That is fine for one that only reads it, but what it changes there is lost.

Any other callable is not judged: an invokable object, a function's name, `require` of another file. PHP's own errors in a Function are the PHP editor's, as in any PHP file.

## Limits

- The window makes Modules and Functions; it does not rename, move or delete them. That is the [[Project Window]]'s, and the Flow's references are then yours to change.
- It does not run a Function on its own, nor simulate one or a Flow. Running is Runner's, with the whole Flow ([[Running Flows]]).
- References are read where they are written literally. An import whose name is computed at run time is unknown.
