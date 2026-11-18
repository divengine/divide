"""Git > Pull requests and issues, with a fake gh that says what it was asked."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from divide.app import Divide
from divide.run import forge, git
from divide.ui import forge as forgeui
from test_forge import FAKE
from test_git_ui import bar_on, repo, rows, sh, until, window

pytestmark = pytest.mark.skipif(git.program() is None, reason="git is not installed")

PULLS = [{"number": 7, "title": "Cards", "author": {"login": "ana"}, "headRefName": "cards", "baseRefName": "main",
          "state": "OPEN", "url": "https://github.com/me/site/pull/7", "isDraft": True, "updatedAt": "2026-11-18T10:00:00Z"}]
ISSUES = [{"number": 3, "title": "Broken footer", "author": {"login": "bo"}, "state": "OPEN",
           "url": "https://github.com/me/site/issues/3", "labels": [{"name": "bug"}], "updatedAt": "2026-11-17T09:00:00Z"}]


@pytest.fixture
def gh(tmp_path, monkeypatch):
    script = tmp_path / "fake_gh.py"
    script.write_text(FAKE, encoding="utf-8")
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("FAKE_FORGE_LOG", str(log))
    monkeypatch.setenv("FAKE_FORGE_ANSWERS", json.dumps({
        "pr list": json.dumps(PULLS), "issue list": json.dumps(ISSUES),
        "pr create": "https://github.com/me/site/pull/8", "issue create": "https://github.com/me/site/issues/4"}))
    monkeypatch.setattr(forge, "COMMANDS", {"github": [sys.executable, str(script)], "gitea": None})
    return lambda: [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


def on_github(tmp_path: Path) -> Path:
    """A repository whose origin reads as GitHub's and pushes to a folder."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    root = repo(tmp_path / "site")
    sh(root, "remote", "add", "origin", "git@github.com:me/site.git")
    sh(root, "remote", "set-url", "--push", "origin", str(bare))
    return root


async def test_the_open_pull_requests_and_issues(tmp_path, gh):
    root = on_github(tmp_path)
    app = Divide(root, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await app.open_forge()
        win = window(app, forgeui.ForgeWindow)
        await until(pilot, lambda: "#7    Cards (draft)  ana" in rows(win), message=lambda: rows(win))
        assert rows(win) == ["Pull requests  1", "#7    Cards (draft)  ana", "Issues  1", "#3    Broken footer  bo"]
        assert win.title == "GitHub: me/site"
        await bar_on(pilot, win, "#3    Broken footer  bo")
        await until(pilot, lambda: "bug" in str(win.info.render()), message=lambda: str(win.info.render()))
        assert "https://github.com/me/site/issues/3" in str(win.info.render())


async def test_a_new_pull_request_pushes_the_branch_first(tmp_path, gh):
    root = on_github(tmp_path)
    sh(root, "switch", "-q", "-c", "footer")
    (root / "footer.tpl").write_text("footer\n", encoding="utf-8")
    sh(root, "add", ".")
    sh(root, "commit", "-qm", "A footer")
    app = Divide(root, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await app.open_forge()
        win = window(app, forgeui.ForgeWindow)
        await bar_on(pilot, win, "#7    Cards (draft)  ana")
        await pilot.press("insert")
        await until(pilot, lambda: isinstance(getattr(app.screen, "dialog", None), forgeui.NewItemDialog))
        dialog = app.screen.dialog
        assert dialog.title_input.data == "A footer" and dialog.base_input.data == "main"
        await until(pilot, lambda: app.focused is dialog.title_input)  # the dialog has put its focus first
        dialog.body.focus()
        await until(pilot, lambda: app.focused is dialog.body)
        await pilot.press(*"Fixes #3")
        await pilot.press("ctrl+j")
        await until(pilot, lambda: any(c["args"][:2] == ["pr", "create"] for c in gh()), tries=300)
        created = next(c for c in gh() if c["args"][:2] == ["pr", "create"])
        args = created["args"]
        assert args[args.index("--head") + 1] == "footer" and args[args.index("--base") + 1] == "main"
        assert args[args.index("--title") + 1] == "A footer" and created["stdin"] == "Fixes #3"
        assert sh(tmp_path / "origin.git", "branch", "--list", "footer").strip() == "footer"  # pushed first


async def test_a_new_issue_and_a_merge(tmp_path, gh):
    root = on_github(tmp_path)
    app = Divide(root, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await app.open_forge()
        win = window(app, forgeui.ForgeWindow)
        await bar_on(pilot, win, "#3    Broken footer  bo")
        await pilot.press("insert")  # on the issues: a new issue
        await until(pilot, lambda: isinstance(getattr(app.screen, "dialog", None), forgeui.NewItemDialog))
        assert app.screen.dialog.base_input is None
        await until(pilot, lambda: app.focused is app.screen.dialog.title_input)
        await pilot.press(*"Header too", "enter")  # Enter in the title: the default button
        await until(pilot, lambda: any(c["args"][:2] == ["issue", "create"] for c in gh()))

        await bar_on(pilot, win, "#7    Cards (draft)  ana")
        app.forge_action(win, "squash")
        await until(pilot, lambda: getattr(app.screen, "dialog", None) is not None
                    and "squashed" in getattr(app.screen.dialog, "_text", ""))
        await pilot.press("y")
        await until(pilot, lambda: any(c["args"] == ["pr", "merge", "7", "--squash"] for c in gh()))


async def test_without_a_forge_it_says_why(tmp_path, gh):
    root = repo(tmp_path / "site")  # no remote
    app = Divide(root, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await app.open_forge()
        win = window(app, forgeui.ForgeWindow)
        await until(pilot, lambda: rows(win) == ["No forge"], message=lambda: rows(win))
        assert "no remote" in str(win.info.render())
