# Translating Templates

Div can rewrite a template from one dialect to another. **Tools > Translate a template...** makes that a wizard. It is also in the [[Dialector]]'s local menu, with the dialector's dialect as the target.

![translating index.tpl into an ERB-like dialect](images/translate.png)

## The three fields

- **Template:** the template to translate. The active template is proposed. If the template is open, its editor text is used, saved or not.
- **From dialect:** the dialect the template is written in. This is normally known: a template written in another dialect says so with `@_DIALECT`, and one that says nothing is in Div's default dialect. So divide **suggests** it. It reads the template's `@_DIALECT` and lets Div find the file the same way it does when rendering (`getTplPath()`), or it suggests Div's default when there is none. A note under the field says where the suggestion comes from. You can still type another dialect; once you do, divide stops suggesting.
- **To dialect:** the dialect to translate into. Leave it empty for Div's default dialect.

Paths are relative to the project, and an empty dialect means Div's default. Each field has a **...** button that opens the file dialog and writes the chosen file's **absolute** path. Shorten it to a relative one if you prefer. Choosing a file with **...** previews straight away.

## Preview, save, open

- **Preview** (Enter) asks Div to translate (`div::translate()`, with the dialect files decoded by Div's own `jsonDecode()`). The result is highlighted in the target dialect.
- **Save as...** writes the translation next to the template (`index.erb.tpl` is proposed; **Browse...** chooses another place) and opens it.
- **Open** puts the translation in a new, unsaved window.

The original template is never changed. The translation's `@_DIALECT` follows the target: it names the target dialect, relative to where the file is saved, or disappears when the target is Div's default.

## What Div does not translate

The translation is Div's own, as Div does it today. Two things are worth checking in the preview:

- `{%% path:data %%}` pre-processed includes lose their `:` separator.
- Includes inside a loop or a condition are left in the source dialect.

The [[Dialector]]'s verdict shows the first one as a section that Div reads otherwise (`≠`).
