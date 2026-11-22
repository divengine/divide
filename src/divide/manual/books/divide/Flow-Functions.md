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

![From the Flow Designer: F, a new Module and a Function in it from a template, its PHP written and saved, a new Step that uses it, and the Flow run by Runner with the Step's result in the context](images/flow-functions.gif)

## Open it

- **F** on the [[Flow Designer]]'s board.
- **Run > Flow functions**, from a Flow's code, its [[Flow window|Flow Structure]] or its board: the window of that Flow. From anywhere else: the project's.

The window has the Functions as a tree on the left and what the selected item is on the right. At 80 columns, the right part goes under the tree.

![The Functions window of the generator's Flow at 120 columns: the root functions/ from .div/runner.json, its Modules, render:php_class selected and the Step that uses it](images/flow-functions-120.png)

![The same window at 80 columns: the Module validate selected, what it is under the tree](images/flow-functions-80.png)

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
| **Ctrl+F9** | Test the Function under the cursor: run or debug it with a JSON context (below) |
| **Ctrl+R** | Read the disk again (also done when a PHP file, a Flow or the settings are saved) |
| typing | Filter the rows |

## Make a Module

**Shift+Ins** asks for its name: letters, digits, `_` and `-`, as Runner's `module` allows. It is made as a folder of the root (`functions/publish/`), or as the folder `_modules` gives it. A Module that is already there is not made again.

## Make a Function

**Ins** opens **New Function**:
- **Module**: the Module (**Down** offers the ones there are). Empty: the root.
- **Name**: letters, digits, `_` and `-`. In a Module, also `folder/name` (`tax/compute`), as Runner allows. Without `.php`: Runner adds it.
- **Use**: **Activity** or **Condition**.

![New Function in the Module render: the name slug, its use, and where it will be written and what a Step says to use it](images/flow-functions-new.png)

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
  - **Test...**: the Test Function dialog for it, once the Step is written (see Test a Function).
  - **New...**: the New Function dialog, with the Step's Module. Its **OK** fills the Step's `module` and `activity` (or `condition`) and says that the file will be made. Nothing is written yet: the Step dialog's **OK** writes the Step, as one edit of the YAML (one Ctrl+Z), makes the file and opens it. **Cancel** writes and makes nothing. If the Step cannot be written, the new file is removed.

![The Step dialog after Function... > New...: module and activity filled in, and the note that OK writes the Step and makes functions/render/publish.php](images/flow-functions-step.png)

A Step has one `module`, for both its condition and its activity: a new Function in another Module than the Step's other Function is refused.

**Ctrl+Enter** on a Step (on the board, in the Flow window or on its line in the code) opens its Function's file. When there is none, it says where Runner looked.

## Test a Function

**Test Function** calls one Function on its own, with a context you give, and shows what it did: what it returned, how it changed the context, what it printed, and any exception or error with its place. It does not run a Flow or a Step.

![T on a Step of the Flow Designer: its Function tested with a JSON context, run and then debugged, stopped in the Function, and its report in Output](images/function-test.gif)

> **It runs the project's real PHP code.** The Function and whatever it calls may write files, use a database or the network. The test runs in a PHP process of its own, with a time limit and a memory limit, but that is not a sandbox, and the debugger is not one either. Test only code you trust.

Open it with:
- **Ctrl+F9** on a Function in the Functions window (on one of its Steps: as that Step uses it);
- **T** on a Step in the Flow Designer: its activity, else its condition;
- **Function... > Test...** in the Step dialog: the activity, or the condition if that was the field you were in.

The Function is the one a run of the Flow would load: Runner's own importer resolves it, with the Flow's function root and Module folders (see Where Runner looks, below), `_modules` mappings included. With a Module, nothing outside that Module's folder is tried: the same name in another Module is never run instead.

The dialog:
- **Context**: a JSON object, the context the Function gets, by reference. **Edit...** opens it as a tree or as JSON text, the editor of a Step's context. The last input of each Function is remembered in your own settings, never in the project.
- **Scenario**: a name for this input. **Save** writes it in the project, in `.div/function-tests/<module>/<name>.json`, as a fixture the team can use; nothing is saved there unless you save it. **Down** offers the saved ones, and choosing one fills the fields.
- **Expected return** (JSON) and **Expected context after** (a JSON object: the keys the context must hold afterwards, a subset): optional checks.
- **Time limit**, in seconds (30 by default): past it, PHP is ended.
- **Run** (Enter) runs it, in a box that **Esc** stops. **Debug** runs it in the debugger.

Unsaved PHP files are saved first: PHP runs what is on disk.

![The Test Function dialog for validate:identifiers: the context as JSON, a scenario, the expected return 2, the time limit and the warning that this is real PHP code](images/function-test-dialog.png)

### The report

The Output window has, each part apart:
- the file Runner's importer loaded, and how the call ended: returned, exception, fatal error, `exit()`, not found, time limit, stopped;
- the expectations, `ok` or `FAIL`;
- **the returned value**, as JSON (objects, closures and resources described), and its type. This is a direct call: in a Flow, Runner would keep an activity's result in `$context[<the Step's id>]`; here no Step runs, so it is only returned. For a condition, the report says what the value would do to a Step (true runs it, false skips the rest);
- an exception's class, message, file and line, and its trace; a fatal error's message and place;
- **the context's changes**, key by key (`+` added, `~` changed, `-` removed), then the context before and after;
- **stdout** and **stderr**, what the Function printed, never mixed with the result.

An exception's or a fatal error's place, PHP's warnings, and a failed expectation go to Messages, where Enter opens the file at that line.

![The report in Output beside the Flow Designer: the file loaded, returned in 0.06s, the expectation ok, the returned value, the context's changes and the context before](images/function-test-report.png)

### Debug a Function

**Debug** makes the same call under the [[debugger|Debugging PHP]], with Xdebug. When the Function's file has no breakpoint, the debugger stops at the Function's first line; otherwise it runs to your breakpoints, in the Function or in any PHP file it calls. Then **F7**, **F8**, **Shift+F8**, **F4**, watches, the call stack and **Ctrl+F4** work as for any PHP script, **Ctrl+F9** goes on, and **Ctrl+F2** ends it. When it ends, the same report appears in Output.

![Debug: the debugger stopped in functions/validate/identifiers.php, in the Function's body](images/function-test-debug.png)

### How it calls the Function

A small PHP harness that ships with divide, in the project's folder:
1. loads the project's Composer autoload (`vendor/autoload.php`) and Runner;
2. resolves the Function with `runner::importer()`;
3. calls it as Runner calls a condition or an activity, `$func($context)`, with `$context['_importer']` in the context so it can import other Functions;
4. writes the result to a temporary file of its own.

It never writes a Flow's saved context (`.div/runner/`), the Function, or any file of yours.

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
- A Function test runs real PHP, once; it does not simulate a Function with mocks, nor a Flow. Running a Flow is Runner's ([[Running Flows]]).
- References are read where they are written literally. An import whose name is computed at run time is unknown.
