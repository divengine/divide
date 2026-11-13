# Rendering

**Ctrl+F9** (Run > Render) renders the template through PHP and the real Div engine, and shows the result next to the code.

![template and output side by side](images/hero.png)

## What is rendered

- **The template**: the active one; or, from a data file, the template it belongs to; or the last rendered one. Its **unsaved edits are included**, and its real path is given to Div so that relative includes work. Untitled templates are not rendered: see *Save first* in [[Checking Templates]].
- **The data**: by Div's convention `page.tpl` takes `page.json`, next to it. **Run > Data file…** chooses another file; **Run > Edit data** opens it (creating it if needed). The editor buffer is used if the data file is open.
- **The working directory** is the project folder, as for include checks.

The first render places the template on the left and the Output on the right. The Output window is read-only and highlighted, so Div tags that were left unprocessed stand out. Its status line says what was rendered: `index.tpl + index.json · Div 6.1.2 · 0.08s`.

## Rendering again

While the Output window is open, **saving the template or its data re-renders** in the background, without moving your focus. **Alt+F5** brings the Output window back; if there is none, it renders.

## Messages

Div's own warnings, PHP notices and problems with the data go to the [[Messages window|Checking Templates]], below the template's checks. For example `DATA: Div could not decode the data as an object; rendering without data` when the JSON is broken; the data is decoded with Div's own `jsonDecode()`, so what you see is what the template gets.

One Div behaviour worth knowing: a data file is decoded before any variable exists, so `$references` inside `page.json` come out empty. divide adds a note when that happens. References do work in JSON inside templates, e.g. `{= card: {"who": $person.name} =}`.

## Choosing the engine

See [[Installation]]: `DIVIDE_DIV_PHP`, **Options > Div engine…**, or the project's `vendor/`. When Div cannot be found, Render tells you how to install it.
