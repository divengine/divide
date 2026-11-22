# A generator: a PHP DTO class from a JSON model

A small generator to develop in divide. It reads a model of a PHP class, a DTO, and generates the class's source
code and a README for it with [Div](https://github.com/divengine/div) templates. A
[Runner](https://github.com/divengine/runner) Flow orders the stages: validation, a check that skips generation
when nothing changed, rendering, a PHP lint and checks that the outputs say what the model says.

```bash
composer install          # divengine/div and divengine/runner, in vendor/
divide .
```

## What is where

| Path | What it is |
|---|---|
| `model/package_info.json` | The model: a namespace, a class, a description and the fields, each with a `name`, a `type` (`string`, `int`, `float` or `bool`), `nullable` and a `description` |
| `templates/dto.tpl` | The class: promoted readonly properties, `fromArray()` and `toArray()` |
| `templates/readme.tpl` | Its README: a table of the fields |
| `flows/generate_php_dto.yml` | The Flow: four Blocks, the order of the stages |
| `functions/` | What each Step does, as Runner functions: one PHP file that returns a callable each. `validate/`, `render/` and `quality/` are the Modules of the Blocks with those names |
| `lib/generator.php` | What the functions share: paths, the model as the templates read it, rendering with Div, hashes, writing |
| `generate.json` | The initial context: which model, and the output folder |
| `build/` | The outputs, made by the generator and not kept in Git: `src/PackageInfo.php`, `README.md`, `manifest.json` and `report.json` |

## The Flow

| Block | Steps |
|---|---|
| `main` | `load` the model, `validate` (call), `current` (a jump when the outputs are current), `generate` (call), `verify` (call), `report` |
| `validate` | `schema`, `identifiers`, and `reject`, which ends the run in error if either found a problem, before anything is written |
| `generate` | `php` and `readme` rendered by Div, and the `manifest` of the inputs' and outputs' hashes |
| `quality` | `lint` (`php -l` on the class) and `verify` |

- The **calls** come back. `main.validate`, `main.generate` and `main.verify` each run another Block from its
  first Step, and `main` goes on with its next Step when that Block ends.
- The **jump** does not come back. `main.current` asks `outputs_current`, which compares the manifest with the
  hash of the model, the templates and the rendering code, and with the outputs on disk. When nothing changed,
  `main.current` jumps to `.verify`, over `generate`.
- `quality.verify` renders both templates again in memory and compares them with the files, byte for byte. It
  then loads the class and checks its namespace, its name, its constructor's parameters (names, order, types,
  nullability) and that `fromArray()` gives back the data `toArray()` returns. Finally, it checks that the README
  lists every field.

Open the Flow and use **Run > Flow designer** to see it as a board. **Ctrl+F9** runs it: give `generate.json` as
the initial context and `functions` as the function root. The same without divide:

```bash
php vendor/divengine/runner/bin/run.php flows/generate_php_dto.yml --context generate.json --root functions
php vendor/divengine/runner/bin/run.php flows/generate_php_dto.yml --context generate.json --root functions  # again: skipped
```

The first run says `done` and writes `build/`. The second one says `done` too and only rewrites
`build/report.json`, with `"regenerated": false` and without the `php`, `readme` and `manifest` stages. Any change
to the model, to a template, or to a file in `build/` makes the next run generate again.

Change the model and try:
- a field with `"type": "integer"`, or a field twice: `validate` stops the run and lists the problems;
- `"nullable": true` on a field: `?string` in the class and `?? null` in `fromArray()`;
- a template that writes broken PHP: `quality.lint` stops the run.

## Determinism and safety

- The outputs depend only on the model and the templates. No dates, random values or request data are rendered,
  and the report has no time in it, so a run on the same inputs writes the same bytes.
- Paths are relative to this folder, whatever the working directory. A path in the context that leaves it (an
  absolute path, `..`) is refused. The output must be `build/` or a folder inside it: the generator writes nowhere
  else and never touches its model, templates or code.

This is one way to build a generator, not the way. Runner orders its stages here because the Flow Designer draws
Runner Flows, but a generator needs no Runner or pipeline: a PHP script that renders a template with Div is one
too.

Flows and their functions are trusted PHP code: Runner is not a sandbox.
