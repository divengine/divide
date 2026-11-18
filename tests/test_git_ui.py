"""The Git menu's windows on real repositories: stage, commit, branches, discard, history, push and pull."""

import subprocess
from pathlib import Path

import pytest
from textual_vision.constants import Command

from divide.app import Divide
from divide.run import git
from divide.ui import git as gitui

pytestmark = pytest.mark.skipif(git.program() is None, reason="git is not installed")


def sh(root: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=root, check=check, capture_output=True, text=True).stdout


def repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    sh(root, "init", "-q", "-b", "main")
    sh(root, "config", "user.name", "Test")
    sh(root, "config", "user.email", "test@example.com")
    sh(root, "config", "commit.gpgsign", "false")
    (root / "index.tpl").write_text("<h1>{$title}</h1>\n", encoding="utf-8")
    sh(root, "add", ".")
    sh(root, "commit", "-q", "-m", "The home page")
    return root.resolve()


async def until(pilot, check, tries=200, message=None):
    for _ in range(tries):
        if check():
            return
        await pilot.pause(0.05)
    raise AssertionError(f"timed out: {message()}" if message else "timed out")


def window(app, kind):
    return next((w for w in app.windows() if isinstance(w, kind)), None)


def rows(win) -> list[str]:
    tree = win.git_tree
    out = []
    for line in range(tree.last_line + 1):
        node = tree.get_node_at_line(line)
        if node is not None:
            out.append(tree.render_label(node, tree.rich_style, tree.rich_style).plain.lstrip("►▼ ").strip())
    return out


async def bar_on(pilot, win, text: str) -> None:
    """Put the bar on the row that reads ``text``."""
    tree = win.git_tree
    await until(pilot, lambda: text in rows(win), message=lambda: rows(win))
    for line in range(tree.last_line + 1):
        node = tree.get_node_at_line(line)
        if node is not None and tree.render_label(node, tree.rich_style, tree.rich_style).plain.lstrip("►▼ ").strip() == text:
            tree.move_cursor(node)
            break
    tree.focus()
    await until(pilot, lambda: win.row is not None and tree.cursor_node is not None
                and tree.render_label(tree.cursor_node, tree.rich_style, tree.rich_style).plain.lstrip("►▼ ").strip() == text)


async def test_the_project_window_says_the_branch_and_what_changed(tmp_path):
    root = repo(tmp_path / "site")
    (root / "new.tpl").write_text("x", encoding="utf-8")
    app = Divide(root, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await until(pilot, lambda: app.project_window() is not None)
        frame = app.project_window().query_one(gitui.IndicatorFrame)
        await until(pilot, lambda: frame.indicator == "main · 1 changed", message=lambda: frame.indicator)


async def test_stage_unstage_and_commit(tmp_path):
    root = repo(tmp_path / "site")
    (root / "index.tpl").write_text("<h1 class=\"t\">{$title}</h1>\n", encoding="utf-8")
    (root / "card.tpl").write_text("card\n", encoding="utf-8")
    app = Divide(root, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await app.git_command(gitui.CM_GIT_CHANGES)
        win = window(app, gitui.GitChangesWindow)
        await until(pilot, lambda: win is not None and "? card.tpl" in rows(win), message=lambda: rows(win))
        assert rows(win) == ["Changes  1", "M index.tpl", "Untracked  1", "? card.tpl"]

        await bar_on(pilot, win, "M index.tpl")
        await until(pilot, lambda: "+<h1 class=\"t\">{$title}</h1>" in win.diff.text, message=lambda: win.diff.text)
        assert ("diff.add" in {kind for _s, _e, kind in win.diff.marks}
                and "diff.del" in {kind for _s, _e, kind in win.diff.marks})
        await pilot.press("space")
        await until(pilot, lambda: rows(win)[:2] == ["Staged (the next commit)  1", "M index.tpl"], message=lambda: rows(win))
        await bar_on(pilot, win, "M index.tpl")
        await pilot.press("space")  # back out
        await until(pilot, lambda: rows(win)[0] == "Changes  1", message=lambda: rows(win))
        await bar_on(pilot, win, "Untracked  1")
        await pilot.press("space")  # an area: all of it
        await until(pilot, lambda: rows(win)[:2] == ["Staged (the next commit)  1", "A card.tpl"], message=lambda: rows(win))

        await pilot.press("ctrl+k")
        await until(pilot, lambda: isinstance(getattr(app.screen, "dialog", None), gitui.CommitDialog))
        dialog = app.screen.dialog
        await pilot.press("ctrl+j")  # an empty message is refused
        await until(pilot, lambda: "Write a message" in str(dialog.what.render()))
        await pilot.press(*"A card")
        await pilot.press("ctrl+j")
        await until(pilot, lambda: rows(win)[:2] == ["Changes  1", "M index.tpl"], message=lambda: rows(win))
        assert sh(root, "log", "-1", "--format=%s").strip() == "A card"
        assert sh(root, "show", "--name-only", "--format=").split() == ["card.tpl"]


async def test_commit_can_stage_everything_first(tmp_path):
    root = repo(tmp_path / "site")
    (root / "index.tpl").write_text("changed\n", encoding="utf-8")
    app = Divide(root, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await app.git_command(gitui.CM_GIT_COMMIT)
        await until(pilot, lambda: isinstance(getattr(app.screen, "dialog", None), gitui.CommitDialog))
        dialog = app.screen.dialog
        assert dialog.flags.value == 2  # nothing staged: stage every change, ticked
        await pilot.press(*"Everything")
        await pilot.press("ctrl+j")
        await until(pilot, lambda: sh(root, "log", "-1", "--format=%s").strip() == "Everything")
        assert sh(root, "status", "--porcelain") == ""


async def test_discard_reads_the_open_file_again(tmp_path):
    root = repo(tmp_path / "site")
    (root / "index.tpl").write_text("oops\n", encoding="utf-8")
    app = Divide(root, [root / "index.tpl"])
    async with app.run_test(size=(120, 40)) as pilot:
        editor = app.editor_windows()[0]
        assert editor.editor.text == "oops\n"
        await app.git_command(gitui.CM_GIT_CHANGES)
        win = window(app, gitui.GitChangesWindow)
        await bar_on(pilot, win, "M index.tpl")
        await pilot.press("delete")
        await until(pilot, lambda: getattr(app.screen, "dialog", None) is not None)
        await pilot.press("y")
        await until(pilot, lambda: (root / "index.tpl").read_text(encoding="utf-8") == "<h1>{$title}</h1>\n")
        await until(pilot, lambda: editor.editor.text == "<h1>{$title}</h1>\n" and not editor.dirty)


async def test_branches_new_switch_and_delete(tmp_path):
    root = repo(tmp_path / "site")
    app = Divide(root, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await app.git_command(gitui.CM_GIT_BRANCHES)
        win = window(app, gitui.GitBranchesWindow)
        await until(pilot, lambda: win is not None and "* main" in rows(win), message=lambda: rows(win))
        win.git_tree.focus()
        await pilot.press("insert")
        await until(pilot, lambda: getattr(app.screen, "dialog", None) is not None)
        await pilot.press(*"bad name")
        await pilot.press("enter")
        await until(pilot, lambda: "cannot be a branch name" in getattr(getattr(app.screen, "dialog", None), "_text", ""))
        await pilot.press("enter")  # the message; the name again, to correct
        await until(pilot, lambda: hasattr(getattr(app.screen, "dialog", None), "input"))
        app.screen.dialog.input.data = "feature/cards"
        await pilot.press("enter")
        await until(pilot, lambda: "* feature/cards" in rows(win), message=lambda: rows(win))
        assert sh(root, "branch", "--show-current").strip() == "feature/cards"

        await bar_on(pilot, win, "main")
        await pilot.press("enter")
        await until(pilot, lambda: "* main" in rows(win), message=lambda: rows(win))
        await bar_on(pilot, win, "feature/cards")
        await pilot.press("delete")
        await until(pilot, lambda: getattr(app.screen, "dialog", None) is not None)
        await pilot.press("y")
        await until(pilot, lambda: "feature/cards" not in rows(win), message=lambda: rows(win))


async def test_history_and_a_commit_s_diff(tmp_path):
    root = repo(tmp_path / "site")
    (root / "index.tpl").write_text("<h1>{$title}</h1>\n<p>more</p>\n", encoding="utf-8")
    sh(root, "commit", "-qam", "More on the page")
    app = Divide(root, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await app.git_command(gitui.CM_GIT_HISTORY)
        win = window(app, gitui.GitHistoryWindow)
        await until(pilot, lambda: win is not None and len(rows(win)) == 2, message=lambda: rows(win))
        assert "[main]" in rows(win)[0] and rows(win)[0].endswith("More on the page")
        win.git_tree.focus()
        await until(pilot, lambda: "More on the page" in str(win.info.render()), message=lambda: str(win.info.render()))
        await pilot.press("enter")
        await until(pilot, lambda: window(app, gitui.DiffWindow) is not None)
        diff = window(app, gitui.DiffWindow)
        await until(pilot, lambda: "+<p>more</p>" in diff.view.text, message=lambda: diff.view.text)


async def test_push_and_pull_with_a_remote(tmp_path):
    origin = tmp_path / "origin.git"
    sh(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    root = repo(tmp_path / "site")
    sh(root, "remote", "add", "origin", str(origin))
    app = Divide(root, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await app.git_command(gitui.CM_GIT_PUSH)  # no upstream yet: it is set
        await until(pilot, lambda: sh(root, "rev-parse", "--abbrev-ref", "main@{upstream}", check=False).strip() == "origin/main")
        log = window(app, gitui.GitLogWindow)
        assert log is not None and log.lines[0] == "$ git push"

        other = tmp_path / "other"
        sh(tmp_path, "clone", "-q", str(origin), str(other))
        sh(other, "config", "user.name", "Other")
        sh(other, "config", "user.email", "other@example.com")
        (other / "card.tpl").write_text("card\n", encoding="utf-8")
        sh(other, "add", ".")
        sh(other, "commit", "-qm", "A card")
        sh(other, "push", "-q")

        await until(pilot, lambda: not app.screen.is_modal, tries=100)
        await app.git_command(gitui.CM_GIT_PULL)
        await until(pilot, lambda: (root / "card.tpl").exists(), tries=300)


async def test_outside_a_repository_it_says_so(tmp_path):
    (tmp_path / "plain").mkdir()
    app = Divide(tmp_path / "plain", [])
    async with app.run_test(size=(120, 40)) as pilot:
        if git.find_root(tmp_path / "plain") is not None:
            pytest.skip("the temporary folder is inside a repository")
        app.run_worker(app.git_command(gitui.CM_GIT_CHANGES))
        await until(pilot, lambda: getattr(app.screen, "dialog", None) is not None)
        assert "not in a git repository" in app.screen.dialog._text
        await pilot.press("enter")
        assert window(app, gitui.GitChangesWindow) is None
