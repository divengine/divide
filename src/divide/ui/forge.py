"""Git > Pull requests and issues: the repository's forge (GitHub with gh, Gitea with tea).

``ForgeMixin`` is part of the app. The window lists the open pull requests and
issues of the remote's repository; beside them, the one under the bar. Enter
opens it in the browser; Ins makes a new pull request of the current branch
(pushed first when it has to be) or, on the issues, a new issue; Alt+F10 checks
out a pull request's branch, merges it on the forge, copies its address.
"""

from __future__ import annotations

from divide.i18n import _, ngettext

from pathlib import Path

from rich.style import Style
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.cluster import CheckBoxes
from textual_vision.constants import Command
from textual_vision.input_line import InputLine
from textual_vision.label import Label

from divide import themes
from divide.run import forge, git
from divide.ui.dialogs import _Dialog, confirm, information
from divide.ui.filter import Filtered
from divide.ui.git import HASH, PATH, WHEN, WHO, MessageView, Row, _GitWindow, where
from divide.ui.windows import HRule

CM_FORGE = Command.USER + 190
CM_FG_OPEN = Command.USER + 191
CM_FG_CHECKOUT = Command.USER + 192
CM_FG_MERGE = Command.USER + 193
CM_FG_SQUASH = Command.USER + 194
CM_FG_REBASE = Command.USER + 195
CM_FG_NEW_PR = Command.USER + 196
CM_FG_NEW_ISSUE = Command.USER + 197
CM_FG_COPY = Command.USER + 198


class ForgeWindow(_GitWindow):
    """Pull requests and issues | the one under the bar."""

    HINT = _('Enter open in the browser · Ins new pull request (on the issues: new issue) · Alt+F10 more')
    REMOTE = True
    BINDINGS = [Binding("insert", "new", show=False)]
    DEFAULT_CSS = """
    ForgeWindow .git-left { width: 1fr; height: 1fr; }
    ForgeWindow .git-state { height: 1; }
    ForgeWindow .git-right { width: 1fr; height: 9; }
    """

    def __init__(self, root: Path, number: int = 0) -> None:
        super().__init__(_('Pull requests and issues'), root, number=number)
        self.info = Static("", classes="git-info", markup=False)
        self.forge: forge.Forge | None = None
        self.pulls: list[forge.PullRequest] = []
        self.issues: list[forge.Issue] = []

    def compose_content(self) -> ComposeResult:
        with Vertical():
            with Vertical(classes="git-left"):
                yield Filtered(self.git_tree)
            yield HRule()
            yield self.state
            with VerticalScroll(classes="git-right"):
                yield self.info

    def show_state(self, *lines: str) -> None:
        self.state.update(" · ".join([where(self.status), *lines] + ([self.last] if self.last else [])))

    @property
    def item(self) -> forge.PullRequest | forge.Issue | None:
        row = self.row
        return row.item if row is not None and row.kind in ("pr", "issue") else None  # type: ignore[return-value]

    def label_of(self, row: Row) -> Text:
        palette = themes.current()
        it = row.item
        out = Text.assemble((f"#{it.number:<4} ", Style(color=palette.hex(HASH))),  # type: ignore[union-attr]
                            (it.title, Style(color=palette.hex(PATH))))  # type: ignore[union-attr]
        if isinstance(it, forge.PullRequest) and it.draft:
            out.append(_(" (draft)"), Style(color=palette.hex(WHEN)))
        out.append(f"  {it.author}", Style(color=palette.hex(WHO)))  # type: ignore[union-attr]
        return out

    def filter_text_of(self, node) -> str:
        row: Row | None = node.data
        if row is not None and row.kind in ("pr", "issue"):
            it = row.item
            return f"#{it.number} {it.title} {it.author}"  # type: ignore[union-attr]
        return str(node.label)

    @work(group="forge", exclusive=True)
    async def reload(self) -> None:
        tree = self.git_tree
        try:
            self.status = await git.status(self.repo)
            found, why = await forge.detect(self.repo)
            if found is None:
                self.forge = None
                tree.clear()
                tree.root.add_leaf(_('No forge'), Row("none", "none"))
                self.info.update(why)
                self.show_state()
                return
            self.forge = found
            self.title = f"{found.name}: {found.remote.slug}"
            self.state.update(_('Asking {program}...').format(program=found.program))
            self.pulls = await forge.pull_requests(found, self.repo)
            self.issues = await forge.issues(found, self.repo)
        except (git.GitError, forge.ForgeError, ValueError) as exc:
            self.info.update(f"[!] {exc}")
            self.show_state(_('{program} could not answer').format(program=self.forge.program if self.forge else "git"))
            return
        keep = self.row.key if self.row is not None else None
        self.remember_folds()
        tree.clear()
        group = tree.root.add(_("Pull requests  {n}").format(n=len(self.pulls)), Row("group", "pulls"),
                              expand="pulls" not in self._folded)
        for pr in self.pulls:
            group.add_leaf(pr.title, Row("pr", f"pr:{pr.number}", pr))
        group = tree.root.add(_("Issues  {n}").format(n=len(self.issues)), Row("group", "issues"),
                              expand="issues" not in self._folded)
        for issue in self.issues:
            group.add_leaf(issue.title, Row("issue", f"issue:{issue.number}", issue))
        if not tree.put_bar(keep):
            first = tree.first_item()
            tree.put_bar(first.data.key if first is not None else "pulls")
        self.show_state(ngettext("{n} open pull request", "{n} open pull requests", len(self.pulls)).format(n=len(self.pulls))
                        + " · " + ngettext("{n} open issue", "{n} open issues", len(self.issues)).format(n=len(self.issues)))

    def focused_row(self, row: Row | None) -> None:
        if self.forge is None:
            return
        it = row.item if row is not None and row.kind in ("pr", "issue") else None
        if it is None:
            what = row.key if row is not None else "pulls"
            self.info.update({
                "pulls": _("The open pull requests of {repo}. Ins proposes the current branch as a new one."),
                "issues": _("The open issues of {repo}. Ins writes a new one."),
            }.get(what, "").format(repo=self.forge.remote.slug))
            return
        lines = [f"#{it.number}  {it.title}", "─" * min(60, len(it.title) + 6)]
        rows = [(_("Author"), it.author)]
        if isinstance(it, forge.PullRequest):
            rows += [(_("Branch"), f"{it.head} -> {it.base}"), (_("Draft"), _("yes") if it.draft else "")]
        else:
            rows += [(_("Labels"), ", ".join(it.labels))]
        rows += [(_("Updated"), it.updated.replace("T", " ").rstrip("Z")), (_("Address"), it.url)]
        width = max(len(label) for label, _value in rows)
        lines += [f"{label:<{width}}  {value}" for label, value in rows if value]
        self.info.update("\n".join(lines))

    def chosen(self, row: Row) -> None:
        self.app.forge_action(self, "open")  # type: ignore[attr-defined]

    def action_new(self) -> None:
        row = self.row
        on_issues = row is not None and (row.kind == "issue" or row.key == "issues")
        self.app.forge_action(self, "new_issue" if on_issues else "new_pr")  # type: ignore[attr-defined]

    def action_local_menu(self) -> None:
        self.app.forge_action(self, "menu")  # type: ignore[attr-defined]


class NewItemDialog(_Dialog):
    """A new pull request (title, description, into which branch, draft) or a new issue (title, description)."""

    DEFAULT_CSS = """
    NewItemDialog { width: 80; height: 22; }
    NewItemDialog InputLine { width: 1fr; }
    NewItemDialog .ni-row { height: 1; }
    NewItemDialog .ni-row Label { width: 14; }
    NewItemDialog MessageView { height: 1fr; }
    NewItemDialog CheckBoxes { width: 1fr; }
    NewItemDialog .ni-what { height: 2; color: $text-muted; background: $surface; }
    NewItemDialog .ni-what.-bad { color: $error; }
    """

    def __init__(self, title: str, what: str, *, summary: str = "", base: str | None = None) -> None:
        super().__init__(title=title)
        self.title_input = InputLine(max_len=200)
        self.title_input.data = summary
        self.body = MessageView()
        self.base_input = InputLine(max_len=200) if base is not None else None
        if self.base_input is not None:
            self.base_input.data = base or ""
        self.flags = CheckBoxes([_('~D~raft (not ready for review yet)')]) if base is not None else None
        self.what = Static(what, classes="ni-what", markup=False)
        self.title_text = self.body_text = self.base = ""
        self.draft = False

    def compose_content(self) -> ComposeResult:
        with Horizontal(classes="ni-row"):
            yield Label(_('~T~itle'), link=self.title_input)
            yield self.title_input
        if self.base_input is not None:
            with Horizontal(classes="ni-row"):
                yield Label(_('~I~nto branch'), link=self.base_input)
                yield self.base_input
        yield Label(_('D~e~scription'), link=self.body)
        yield self.body
        if self.flags is not None:
            yield self.flags
        yield self.what
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('C~r~eate'), Command.OK, is_default=True, id="ok")
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def action_commit(self) -> None:  # Ctrl+Enter in the description (MessageView)
        self.end_modal(Command.OK)

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        self.title_text = self.title_input.data.strip()
        self.body_text = self.body.text.strip()
        self.base = self.base_input.data.strip() if self.base_input is not None else ""
        self.draft = bool(self.flags.value & 1) if self.flags is not None else False
        problem = ""
        if not self.title_text:
            problem = _("Write a title.")
        elif self.base_input is not None and not self.base:
            problem = _("Say into which branch it goes (main, for example).")
        if problem:
            self.what.set_class(True, "-bad")
            self.what.update(f"[!] {problem}")
            return False
        return True


class ForgeMixin:
    """Git > Pull requests and issues."""

    async def open_forge(self) -> None:
        await self.open_git(ForgeWindow)  # type: ignore[attr-defined]

    def forge_action(self, win: ForgeWindow, action: str) -> None:
        self._forge_action(win, action)

    @work(group="forge-action", exclusive=True)
    async def _forge_action(self, win: ForgeWindow, action: str) -> None:
        if action == "menu":
            action = await self._forge_menu(win)
        if not action:
            return
        hub = win.forge
        if hub is None:
            await self.run_dialog(information(_('Pull requests and issues'), str(win.info.render())))  # type: ignore[attr-defined]
            return
        try:
            changed = await self._forge_do(win, hub, action)
        except (forge.ForgeError, git.GitError) as exc:
            await self.run_dialog(information(hub.name, str(exc)))  # type: ignore[attr-defined]
            changed = False
        if changed:
            win.reload()
            for w in self.git_windows():  # type: ignore[attr-defined]
                if w is not win:
                    w.reload()
            self.refresh_git_state()  # type: ignore[attr-defined]
        if win.is_attached:
            win.git_tree.focus()

    async def _forge_do(self, win: ForgeWindow, hub: forge.Forge, action: str) -> bool:
        root = win.repo
        it = win.item
        match action:
            case "open" | "copy":
                if it is None or not it.url:
                    return False
                if action == "copy":
                    self.copy_to_clipboard(it.url)  # type: ignore[attr-defined]
                    self.notify(_('Copied: {url}').format(url=it.url), timeout=3)  # type: ignore[attr-defined]
                else:
                    self.open_url(it.url)  # type: ignore[attr-defined]
                    self.notify(_('Opening {url}').format(url=it.url), timeout=3)  # type: ignore[attr-defined]
                return False
            case "checkout" if isinstance(it, forge.PullRequest):
                await forge.checkout(hub, root, it.number)
                self._git_files_changed(None)  # type: ignore[attr-defined]
                self.notify(_('On the branch of #{n} now').format(n=it.number), timeout=3)  # type: ignore[attr-defined]
                return True
            case "merge" | "squash" | "rebase" if isinstance(it, forge.PullRequest):
                how = {"merge": _("merge commit"), "squash": _("squashed into one commit"), "rebase": _("rebased")}[action]
                text = _('Merge #{n} ({title}) into {base} on {forge}, {how}?').format(
                    n=it.number, title=it.title, base=it.base, forge=hub.name, how=how)
                if await self.run_dialog(confirm(_('Merge the pull request'), text)) != Command.YES:  # type: ignore[attr-defined]
                    return False
                await forge.merge(hub, root, it.number, action)
                self.notify(_('#{n} merged: Git > Pull brings it here').format(n=it.number), timeout=4)  # type: ignore[attr-defined]
                return True
            case "new_pr":
                return await self._forge_new_pr(win, hub)
            case "new_issue":
                dialog = NewItemDialog(_('New issue on {repo}').format(repo=hub.remote.slug),
                                       _('{forge} gets it as you write it here (Markdown).').format(forge=hub.name))
                if await self.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
                    return False
                out = await forge.create_issue(hub, root, dialog.title_text, dialog.body_text)
                self.notify(_('Issue created: {url}').format(url=forge.url_of(out) or out), timeout=5)  # type: ignore[attr-defined]
                return True
        return False

    async def _forge_new_pr(self, win: ForgeWindow, hub: forge.Forge) -> bool:
        root = win.repo
        state = await git.status(root)
        if state.detached:
            raise git.GitError(_('No branch is checked out (detached HEAD): switch to a branch first.'))
        base = await self._forge_default_branch(root)
        if state.branch == base:
            raise forge.ForgeError(_('{branch} is the branch pull requests go into: make a branch for the change '
                                     '(Git > Branches, Ins) and propose that one.').format(branch=state.branch))
        summary = (await git.capture(["log", "-1", "--format=%s"], root)).strip() if state.oid else ""
        others = len(state.changes)
        what = _('{branch} goes to {forge} as it is in its last commit').format(branch=state.branch, forge=hub.name)
        if others:
            what += " " + ngettext("({n} file changed and not committed stays here).",
                                   "({n} files changed and not committed stay here).", others).format(n=others)
        dialog = NewItemDialog(_('New pull request: {branch}').format(branch=state.branch), what,
                               summary=summary, base=base)
        if await self.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return False
        if not state.upstream or state.ahead:  # the forge needs the branch: push it first
            await self._git_remote(root, "push")  # type: ignore[attr-defined]
            state = await git.status(root)
            if not state.upstream or state.ahead:
                return True  # the push failed: the Git window says why
        out = await forge.create_pull_request(hub, root, dialog.title_text, dialog.body_text, state.branch,
                                              dialog.base, dialog.draft)
        url = forge.url_of(out)
        self.notify(_('Pull request created: {url}').format(url=url or out), timeout=6)  # type: ignore[attr-defined]
        return True

    async def _forge_default_branch(self, root: Path) -> str:
        """The branch the remote's HEAD points at (main, master...), else main."""
        result = await git.run(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], root)
        name = result.output.strip() if result.ok else ""
        if name.startswith("origin/"):
            return name.split("/", 1)[1]
        names = {b.name for b in await git.branches(root) if not b.remote}
        return next((n for n in ("main", "master", "trunk", "develop") if n in names), "main")

    async def _forge_menu(self, win: ForgeWindow) -> str:
        from textual_vision.menus import Menu, MenuItem as Item, Separator as Sep
        from divide.ui.explorer import LocalMenu

        it = win.item
        items = [Item(_('~O~pen in the browser'), CM_FG_OPEN, _('Enter')), Item(_('~C~opy the address'), CM_FG_COPY)]
        if isinstance(it, forge.PullRequest):
            items += [
                Sep(),
                Item(_('C~h~eck out its branch'), CM_FG_CHECKOUT),
                Item(_('~M~erge it'), CM_FG_MERGE),
                Item(_('~S~quash and merge it'), CM_FG_SQUASH),
                Item(_('~R~ebase and merge it'), CM_FG_REBASE),
            ]
        items += [Sep(), Item(_('~N~ew pull request...'), CM_FG_NEW_PR, _('Ins')), Item(_('New ~i~ssue...'), CM_FG_NEW_ISSUE)]
        tree = win.git_tree
        region = tree.content_region
        at = (region.x + 2, region.y + max(0, tree.cursor_line - tree.scroll_offset.y))
        chosen = await self.push_screen_wait(LocalMenu(Menu(items=items), at))  # type: ignore[attr-defined]
        return {
            CM_FG_OPEN: "open", CM_FG_COPY: "copy", CM_FG_CHECKOUT: "checkout", CM_FG_MERGE: "merge",
            CM_FG_SQUASH: "squash", CM_FG_REBASE: "rebase", CM_FG_NEW_PR: "new_pr", CM_FG_NEW_ISSUE: "new_issue",
        }.get(chosen, "")


__all__ = ["ForgeMixin", "ForgeWindow", "NewItemDialog", "CM_FORGE"]
