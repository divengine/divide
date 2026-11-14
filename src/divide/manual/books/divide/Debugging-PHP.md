# Debugging PHP

divide debugs PHP scripts the way Turbo Pascal debugged programs: you step through the code line by line, the line about to run is a cyan bar, breakpoints are red bars, and the Watches window shows what your variables hold.

![paused on a breakpoint in index.php, with the Watches and Call stack windows](images/debug.png)

## What it needs

The debugger is [Xdebug](https://xdebug.org), the PHP extension. Install it:

- Debian / Ubuntu: `sudo apt install php-xdebug`
- elsewhere: `pecl install xdebug`, or your system's package (see [Xdebug's installation guide](https://xdebug.org/docs/install)).

When `php -m` lists Xdebug, divide uses it as it is. If you would rather not load Xdebug in every PHP you run, leave it out of `php.ini` and give the path of `xdebug.so` in **Options > Xdebug…**: divide loads it only for the scripts it debugs.

Nothing else needs setting up. divide starts the script with Xdebug in debug mode, pointed at a free port of its own on `127.0.0.1`, whatever your `php.ini` says about `xdebug.mode` or the client port.

## Keys

These keys belong to the debugger in PHP files. In templates F7 still selects all.

| Key | Menu | Action |
|---|---|---|
| **F8** | Run > Step over | run the line; calls run whole. The first F8 starts the script and stops on its first line |
| **F7** | Run > Trace into | run the line, going into the functions it calls (even into `vendor/`) |
| **Shift+F8** | Run > Step out | run until the current function returns |
| **F4** | Run > Go to cursor | run until the line of the cursor |
| **Ctrl+F9** | Run > Run | run until the next breakpoint, or to the end |
| **Ctrl+F2** | Run > Program reset | end the script now |
| **Ctrl+F8** | Debug > Toggle breakpoint | a breakpoint on the cursor's line, or remove it |
| **Ctrl+F7** | Debug > Add watch | an expression for the Watches window |
| **Ctrl+F4** | Debug > Evaluate | the value of any PHP expression, where the script stopped |
| **Ctrl+F3** | Debug > Call stack | the calls that led to this line |

Without breakpoints, Ctrl+F9 runs the script to its end; with one, it starts the debugger and stops there. Every way of starting passes the [[parameters|Running PHP]] of Run > Parameters.

![the Debug menu](images/menu-debug.png)

## Breakpoints

**Ctrl+F8** on a line paints it red. They can be set before starting or while the script is paused, and they stay on their line numbers (editing lines above them does not move them). They live until divide closes.

## Watches and variables

**Debug > Watches** opens the Watches window at the bottom left. At every stop it shows:

- your watch expressions and their values: `count($data['products']) = 3`. **Ins** (or Ctrl+F7) adds one, **Del** removes the one under the cursor;
- below `── local variables ──`, every variable of the function where the script stopped, with the first level of arrays and objects: `$data = array(6)`, `  title = 'the divide shop'`.

**Ctrl+F4** evaluates an expression once, in a box: `$sum + $x * 10 = 10`. It starts with the word under the cursor. Expressions run in the script, so a call with side effects really happens.

## Call stack

**Ctrl+F3** opens the Call stack window at the bottom right: the function where the script stopped first, `{main}` last. **Enter** on a call shows its line, and from then on Watches and Evaluate look at that call's variables. The next step goes back to the innermost one.

## Output and errors

What the script prints appears in the Output window as it prints it. When the script ends, the Output and the Messages windows are filled as after [[Ctrl+F9|Running PHP]].

## Limits

- One script at a time, run from the command line (`php script.php`). Debugging pages served by a web server is not supported yet.
- Values are shown one level deep; ask for a deeper one with a watch or Evaluate (`$data['products'][0]`).
