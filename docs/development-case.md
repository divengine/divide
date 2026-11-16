# Development Case

How work is done on divide: the tailoring of RUP's Configuration & Change
Management and Environment disciplines.

## 1. Roles

The project has one owner, who acts as product owner, architect and
reviewer, and one or more implementers. The owner validates every UI change
before it reaches the manual.

## 2. Workflow of a change

1. **Requirement.** The change is described as behaviour: a use case, a
   flow, or a key. If it changes a use case, [use-case-model.md](use-case-model.md)
   is updated.
2. **Design.** Reuse comes first: is there a Div operation (through the
   bridge), an external tool, or a divide module that already does it? A new
   module follows the layering in the [architecture](software-architecture.md):
   UI-independent logic in `lang/`, `run/` or `editor/`, presentation in
   `ui/` as a window or dialog plus a mixin.
3. **Implementation.** It follows the conventions below.
4. **Test.** Tests for the new behaviour are written, then the touched test
   files are run one at a time (see the [test plan](test-plan.md)).
5. **Commit and push** to `main`, code first. Tests and commits run as
   separate steps.
6. **Review of the UI** by the owner, with screenshots in a scratch folder,
   not in the wiki.
7. **Manual.** After approval, the wiki pages and screenshots
   (`tools/wiki_shots.py`) are updated, the help book is synced
   (`tools/sync_book.py`), and both are committed.

## 3. Conventions

- **Code.** Python 3.11+, type hints, `from __future__ import annotations`.
  Every module starts with a docstring that explains its feature and its
  reasons. Comments say why, not what. Names follow the Borland and Turbo
  Vision vocabulary where one exists (desktop, status line, local menu,
  history).
- **Commands.** Each command has a `CM_*` constant in `app.py`, a menu entry
  (with a `~hotkey~` that is unique in its menu), a key in `BINDINGS` if it
  has one, and a case in `run_command`. Keys that some terminals cannot send
  (Ctrl+Shift+..., Ctrl+Enter) always have an alternative.
- **Glyphs.** Only ASCII and CP437, single width: no Nerd Fonts, no emoji,
  no wide characters. `tests/test_glyphs.py` checks it.
- **Colours.** Never hard-coded in widgets. They come from a palette role
  (`$divide-<role>` in CSS, `Palette.style(role)` in code), and new roles are
  added to `themes.UI_ROLES` and to every theme.
- **Div.** Div is never modified and its behaviour is never reimplemented.
  Questions go through `run/bridge.php`.
- **Documentation.** The manual (wiki) documents divide and links to Div's
  docs. This folder documents the design.
- **Commit messages.** Describe the change as the user sees it, in one
  sentence or a few clauses.

## 4. Configuration management

- One branch, `main`. Each commit is a working state, pushed after it is
  made.
- The wiki is a separate repository (`divide.wiki`). Its pages are copied
  into `src/divide/manual/books/divide/` and committed with the code that
  needs them.
- Local files of the owner (examples in progress, scratch scripts) are never
  added to commits. Paths are listed explicitly; `git add -A` is not used.

## 5. Environment

- `.venv` in the checkout (`tools/install.sh` creates it).
- A Div checkout with `composer install` for tests and screenshots
  (`DIVIDE_DIV_PHP`).
- Xdebug and a language server are optional, for the tests and screenshots
  that use them.
- Development machines may be small VMs, so heavy jobs (tests,
  screenshots) run one at a time, at low priority, with timeouts.
