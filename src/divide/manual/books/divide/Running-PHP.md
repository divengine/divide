# Running PHP

In a PHP script, **Ctrl+F9** (Run > Run) runs it with `php`, as you would in a shell, and shows what it printed. In a template the same key renders it (see [[Rendering]]).

![Ctrl+F9 on index.php: the box with the verdict, the output behind it](images/run-php.png)

## While it runs

A box like Turbo Pascal's *Compiling* box tells what is running: the script, its parameters, how much it has printed so far and the time. **Esc** stops the script.

When it ends, the box gives the verdict: **Success**, **Warnings**, **Errors**, **Exit code N** or **Stopped**, with the exit code and the count of PHP's messages. The results are already on screen behind it, and any key closes the box. A success closes by itself after a moment.

## What you get

- **The Output window** shows what the script printed (stdout). If PHP or the script wrote to stderr, it comes below a `── stderr ──` line. The status line says the exit code, the time and the size.
- **The Messages window** lists PHP's warnings and errors with their place: `index.php(12): Warning: Undefined variable $nope`, `index.php(13): Fatal error: Uncaught Exception: boom`. **Enter** opens the file at that line, even a file of `vendor/`. PHP is asked to print its errors as plain text on stderr (`display_errors=stderr`, `html_errors=0`), so they never mix with the output.

## How it runs

- **What runs**: the active PHP script, or the last one you ran when you are in another window.
- **Saved first**: PHP runs the files on disk, so divide saves every modified PHP file before running. An untitled script has to be saved first (F2).
- **The working directory** is the script's folder, as with `cd folder && php script.php`.
- **No keyboard**: the script's standard input is closed, so a script that asks a question gets an end of file instead of waiting forever. Use *Run in terminal* for those.

## Parameters

**Run > Parameters…** sets the command line arguments of the script, as you would type them in a shell: `--verbose "two words"`. They arrive in `$argv`, and are remembered per script (in `~/.config/divide/config.json`). Ctrl+F9 and the [[debugger|Debugging PHP]] pass them.

## Run in terminal

**Run > Run in terminal** hands the real terminal over to the script: the desktop goes away, the script runs with your keyboard and screen, and **Enter** brings divide back when it ends. Use it for interactive scripts, and for scripts whose output has colours or moves the cursor.

## Rendering from PHP

A script that renders with Div (`echo new div('index.tpl', $data);`) shows the rendered page in the Output window. To look at the template alone, with its data file, open the template and press Ctrl+F9 there.

Next: [[Debugging PHP]].
