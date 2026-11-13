# Dialector

A Div dialect changes the tags of the language: `{$name}` can become `<%$name%>`, `[$list]` can become `<% each $list %>`. Writing one by hand means getting about 120 tags right, and making sure none of them clash. The dialector is an assistant for that. It is the terminal version of the [web dialector](https://github.com/divengine/dialector), with a live preview, and Div itself checks every change.

![the dialector: sections, preview and Div's verdict](images/dialector.png)

## Opening it

**Tools > Dialector...** opens it on:

- the `.dialect` file you are editing;
- or the dialect of the template you are editing (its `@_DIALECT`);
- or a new dialect file. divide asks for a name (`my.dialect`); **Browse...** picks an existing file.

The dialector is a view of the `.dialect` file, like the data tree is of a JSON file. **F2** saves the file, **Ctrl+Z / Ctrl+Y** undo and redo, and closing the file closes the dialector. The file keeps only the tags that differ from Div's defaults, as standard JSON.

Div reads the file: the dialector decodes it with Div's own `jsonDecode()`, as Div does when a template loads the dialect, so single quotes and unquoted keys work. If Div cannot decode it, the title says `[invalid JSON]` and the verdict box gives Div's reason; fix it in the code. Before the first change, if the file has something that standard JSON would lose (comments, single quotes, keys that are not Div tags), the dialector asks before rewriting it. Without Div, divide reads the file itself.

## The window

- **Left: the sections of the language.** The sections are Replacements, Modifiers, Multiple modifiers, Template variables, Loops and iterations, Conditions, Includes and locations, Formats and formulas, Aggregate functions, Blocks, Capsules and sub-parsers, and Special characters. Each row says how many of its tags you changed (`4/11`) and carries a mark:
  - `•`: the section has changes;
  - `!`: Div rejects a tag of this section;
  - `≠`: Div reads this section back differently from what you wrote (see below).
- **Right: the preview.** An example template that uses every construct, written in your dialect and highlighted by divide in your dialect. The tags of the selected section are marked. Moving through the sections scrolls the preview to them.
- **Below the sections:** what the section is about, and Div's verdict.

Lines divide the window into these three boxes and the preview. The panels use the editor's colours; the selected section is marked like its tags in the preview.

## Editing a section

**Enter** (or a double click) opens the section in a dialog:

- one field per tag, with Div's default beside it;
- a preview of the section's example that follows what you type, with the tag of the current field marked;
- Div's verdict for that section, live.

**OK** applies the changes, **Defaults** puts back Div's tags in the dialog, and **Cancel** discards the changes. **Tab** moves between the fields.

![editing a section](images/dialector-section.png)

**Del** puts the selected section back to Div's defaults (Ctrl+Z undoes it).

## Div's verdict

divide does not decide whether a dialect works: Div does, in two steps.

1. **Is it valid?** The tags are given to Div before it loads, and Div's own `isValidCurrentDialect()` judges them. It checks that the required tags are present and that the tags that must be unique are unique. If a tag is wrong, Div says why, for example `DIV_TAG_BREAK must be unique and not equal to DIV_TAG_EMPTY`, and the section that holds the tag gets a `!`.
2. **Does Div read it?** The example, written in your dialect, is translated back by Div's `translateFrom()` and compared, section by section, with the same example in Div's default dialect. The verdict says how many sections come back exactly. For the first one that does not, it shows the line you wrote and what Div read.

The verdict appears below the sections and in each section dialog, and it is updated after every change. It needs PHP and Div (see [[Installation]]).

## The local menu

**Alt+F10** (or Shift+F10):

![the local menu](images/dialector-menu.png)

| Item | |
|---|---|
| **Edit section...** | the section dialog (Enter) |
| **Restore section defaults** | the section back to Div's tags (Del) |
| **Transform all tags...** | replace a piece of text in every tag at once, e.g. `{` → `{{`. The dialog lists the tags that change before you accept. |
| **Restore all defaults** | every tag back to Div's defaults |
| **Import tags...** | take the tags of another dialect file (decoded by Div's own `jsonDecode()`, single quotes included, so files saved by the web dialector work), or of a PHP file with `define('DIV_TAG_…', '…')` lines. Tags the file does not mention go back to Div's defaults. |
| **Export as PHP code** | the dialect as PHP `define()` lines, in a new window. Include that file before `div.php` to make the dialect the default one for a whole PHP project. |
| **Save example template...** | writes the example in your dialect as a template that starts with `@_DIALECT = your.dialect`, and opens it. Your dialect file is saved first. |
| **Translate a template...** | the [[Translating Templates]] wizard, with this dialect as the target |
| **Check with Div** | ask Div again now |

## Using a dialect

A template uses a dialect by naming it in its first lines:

```
@_DIALECT = erb.dialect
<h1><%$title%></h1>
```

divide highlights, checks and completes the template with that dialect. Div translates the template when it renders it. The repository's `examples/shop/erb.dialect` is a small dialect in this style.
