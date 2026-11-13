# Checking Templates

divide checks your template on every edit, with its dialect, and tells you what Div would trip over or silently leave as plain text.

![errors in the editor and the Messages window](images/diagnostics.png)

## What is checked

**Errors** (white on red in the editor):

- loops never closed (`[$products]` without `[/$products]`) and closings without an opening (`[/$orders]`);
- conditions `{?( … )?}` without their `{/?}`, and `{/?}` with nothing to close;
- tags whose end is missing, which Div would leave as text: `<!--{`, `{=`, `{@`, `{?(`, `(#`, `{#`, `{% `, `{%% `, `[:`, `(( `, `{txt}`, `{strip}`, `<!--|`, `{ignore}`;
- a `@_DIALECT` that Div cannot find or cannot decode (Div loads the dialect itself: see [[Editing Templates]]).

**Warnings** (on brown):

- includes that Div cannot resolve (see below);
- malformed JSON in a template variable, `{= shipping: {"days": } =}`, at the exact character.

## Seeing them

- In the editor, the problem is painted where it is.
- The **status line** shows the message under the cursor, or the counts: `Div · 2 errors, 1 warning (Alt+F8)`.
- **Alt+F9** (Run > Check) opens the **Messages** window at the bottom, Turbo Pascal style: `checkout.tpl(3,1): Error: loop [$cart.lines] is never closed with [/$cart.lines]`. It follows the active template while you type, and the messages of the last render are listed below. **Enter** or a double click jumps to the place.
- **Alt+F8** / **Alt+F7** jump to the next / previous problem, even with the Messages window closed.

## Includes are resolved by Div

Div finds included templates its own way: relative to the working directory, to the including template's folder, to the templates included before, adding `.tpl` when it is missing. divide does not imitate that. It asks the engine: Div's own `getTplPath()`, called through PHP with the template's path, the same working directory a render uses (the project folder) and, as include history, the last template you rendered. Only what Div answers "not found" is reported.

So include warnings need PHP and Div (see [[Installation]]). Without them nothing is reported about includes, rather than guessing. Includes built from variables (`{% parts/{$name} %}`) are only known at render time and are not checked.

The answers are asked again when the includes of the template change, when you come back to the template, after saving, and after creating, renaming or deleting files in the [[Project Window]].

### Go to the included template

Put the cursor on an include and press **Ctrl+Enter**, or Ctrl+click it, or use Search > Go to included template. The file Div would include opens. If Div cannot find it, divide offers to create it next to the current template, which is the first place Div looks.

Many terminals send Ctrl+Enter as a plain newline; divide also accepts it as **Ctrl+J**, so it works either way.

## Save first: a convention

Div can take a template as a string, without a file. divide could pass it an unsaved buffer, but a template without a file has no folder: Div would not find its includes the way it will in production, and divide would not know its data file (`page.tpl` → `page.json`). So divide follows a simple convention: **templates are saved before Div sees them.** An untitled template is checked for everything else, but its includes are not resolved, and Render and Go to include ask you to save it first (F2).

Once a template has a file, its unsaved edits are fine: rendering and checking always use what is in the editor.
