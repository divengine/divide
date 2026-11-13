# Editing Templates

Files ending in `.tpl` (and `.div`) are Div templates; untitled windows are treated as templates too.

## Highlighting that knows Div

Every construct of the language has its own colour: replacements and their modifiers (`{$x}`, `{^^title}`, `{html:body}`, `{$body:~25}`), loops and their item names, conditions, template variables and their JSON, includes, formulas, number and date formats, comments and documentation blocks, macros, ignored blocks… Div code nested inside other Div code is highlighted too, and the HTML between tags is coloured lightly so that the Div stays in front.

### Dialects

Div lets a template change its tags with `@_DIALECT = file.dialect`. divide highlights, checks and completes with **your** tags, and the status line shows the dialect's name.

Which file that is, and what it says, is Div's business: divide asks Div to load the dialect as it does when it renders. Div finds the file with `getTplPath()` (relative to the working directory, to the template's folder, to the templates included before) and decodes it with its own `jsonDecode()`. If Div cannot find the file or cannot decode it, the `@_DIALECT` line is reported as an error. Until Div answers, or without PHP and Div, divide guesses the file only to colour the template and reports nothing about it. Like includes, the dialect is resolved from the template's folder, so it is checked once the template is saved (see *Save first* in [[Checking Templates]]). To build a dialect, use the [[Dialector]]; to move a template to another dialect, [[Translating Templates]].

## Find and replace

| Key | |
|---|---|
| **Ctrl+F** | Find |
| **Ctrl+R** | Replace |
| **Ctrl+L** | Search again (repeats the last find or replace) |
| **Ctrl+G** | Go to line number |

The dialogs are the classic ones: case sensitive, whole words only, regular expressions (with `\1` groups in the replacement), forward or backward, from the cursor or the entire file, and *prompt on replace* to confirm each change. The selected text, or the word under the cursor, is proposed as what to find.

![the Replace dialog](images/replace.png)

## Editing keys

The usual ones work: arrows, Home/End, PgUp/PgDn, Shift to select, **Ctrl+Z** / **Ctrl+Y** undo and redo, **Ctrl+X/C/V** cut, copy and paste, **F7** select all, **Tab** indents. **Ctrl+Space** opens [[Completion]], **Ctrl+Enter** goes to the template an include points to (see [[Checking Templates]]).

## Other files

Data files (`.json`, `.dialect`) are Div JSON: see [[Data Files]]. PHP files have their own editor: see [[Editing PHP]]. Any other file opens as plain text.
