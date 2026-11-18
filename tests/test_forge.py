"""divide.run.forge: GitHub (gh) and Gitea (tea), with fake programs that say what they were asked."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from divide.run import forge, git

pytestmark = pytest.mark.skipif(git.program() is None, reason="git is not installed")

FAKE = r'''
import json, sys, os
log = os.environ["FAKE_FORGE_LOG"]
args = sys.argv[1:]
body = sys.stdin.read() if "-" in args else ""
with open(log, "a", encoding="utf-8") as f:
    f.write(json.dumps({"args": args, "stdin": body}) + "\n")
answers = json.loads(os.environ.get("FAKE_FORGE_ANSWERS", "{}"))
key = " ".join(args[:2])
if key in answers:
    print(answers[key])
elif os.environ.get("FAKE_FORGE_FAIL"):
    sys.stderr.write(os.environ["FAKE_FORGE_FAIL"])
    sys.exit(1)
'''


@pytest.fixture
def fake(tmp_path, monkeypatch):
    script = tmp_path / "fake_forge.py"
    script.write_text(FAKE, encoding="utf-8")
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("FAKE_FORGE_LOG", str(log))
    monkeypatch.setattr(forge, "COMMANDS", {"github": [sys.executable, str(script)], "gitea": [sys.executable, str(script)]})

    def calls():
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []

    def answer(answers: dict[str, object]):
        monkeypatch.setenv("FAKE_FORGE_ANSWERS", json.dumps({k: v if isinstance(v, str) else json.dumps(v)
                                                              for k, v in answers.items()}))

    return calls, answer


def repo_with_remote(root: Path, url: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "remote", "add", "origin", url], cwd=root, check=True)
    return root


@pytest.mark.parametrize("url, expected", [
    ("git@github.com:divengine/divide.git", ("github.com", "divengine", "divide")),
    ("https://github.com/divengine/divide", ("github.com", "divengine", "divide")),
    ("https://github.com/divengine/divide.git/", ("github.com", "divengine", "divide")),
    ("ssh://git@gitea.example.com:2222/team/site.git", ("gitea.example.com", "team", "site")),
    ("https://user:token@codeberg.org/me/notes.git", ("codeberg.org", "me", "notes")),
    ("git@git.example.com:group/sub/project.git", ("git.example.com", "group/sub", "project")),
    ("/srv/git/site.git", None),
])
def test_remote_urls(url, expected):
    remote = forge.parse_remote(url)
    assert (None if remote is None else (remote.host, remote.owner, remote.repo)) == expected


async def test_the_forge_of_the_remote(tmp_path, fake, monkeypatch):
    found, why = await forge.detect(repo_with_remote(tmp_path / "a", "git@github.com:me/site.git"))
    assert found == forge.Forge("github", forge.Remote("github.com", "me", "site")) and why == ""
    found, _why = await forge.detect(repo_with_remote(tmp_path / "b", "https://codeberg.org/me/site.git"))
    assert found is not None and found.kind == "gitea" and found.name == "Gitea"
    monkeypatch.setattr(forge, "COMMANDS", {"github": None, "gitea": None})
    found, why = await forge.detect(tmp_path / "a")
    assert found is None and "install gh" in why
    found, why = await forge.detect(tmp_path / "b")
    assert found is None and "install tea" in why
    plain = tmp_path / "c"
    plain.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=plain, check=True)
    found, why = await forge.detect(plain)
    assert found is None and "no remote" in why


async def test_github_lists_and_creates(tmp_path, fake):
    calls, answer = fake
    root = repo_with_remote(tmp_path / "site", "git@github.com:me/site.git")
    hub = forge.Forge("github", forge.Remote("github.com", "me", "site"))
    answer({
        "pr list": [{"number": 7, "title": "Cards", "author": {"login": "ana"}, "headRefName": "cards",
                     "baseRefName": "main", "state": "OPEN", "url": "https://github.com/me/site/pull/7",
                     "isDraft": True, "updatedAt": "2026-11-18T10:00:00Z"}],
        "issue list": [{"number": 3, "title": "Broken footer", "author": {"login": "bo"}, "state": "OPEN",
                        "url": "https://github.com/me/site/issues/3", "labels": [{"name": "bug"}], "updatedAt": "x"}],
        "pr create": "https://github.com/me/site/pull/8",
    })
    assert await forge.pull_requests(hub, root) == [forge.PullRequest(
        7, "Cards", "ana", "cards", "main", "open", "https://github.com/me/site/pull/7", True, "2026-11-18T10:00:00Z")]
    assert (await forge.issues(hub, root))[0] == forge.Issue(3, "Broken footer", "bo", "open",
                                                            "https://github.com/me/site/issues/3", ("bug",), "x")
    out = await forge.create_pull_request(hub, root, "Footer", "Fixes #3\n", "footer", "main", draft=True)
    assert forge.url_of(out) == "https://github.com/me/site/pull/8"
    created = calls()[-1]
    assert created["args"][:2] == ["pr", "create"] and created["stdin"] == "Fixes #3\n"
    assert created["args"][created["args"].index("--head") + 1] == "footer" and "--draft" in created["args"]
    await forge.checkout(hub, root, 7)
    await forge.merge(hub, root, 7, "squash")
    assert [c["args"] for c in calls()[-2:]] == [["pr", "checkout", "7"], ["pr", "merge", "7", "--squash"]]


async def test_gitea_lists_and_creates(tmp_path, fake):
    calls, answer = fake
    root = repo_with_remote(tmp_path / "site", "https://codeberg.org/me/site.git")
    tea = forge.Forge("gitea", forge.Remote("codeberg.org", "me", "site"))
    answer({
        "pulls list": [{"index": "5", "title": "WIP: cards", "state": "open", "author": "ana", "head": "cards",
                        "base": "main", "url": "https://codeberg.org/me/site/pulls/5", "updated": "2026-11-18"}],
        "issues list": [{"index": "2", "title": "Footer", "state": "open", "author": "bo",
                         "url": "https://codeberg.org/me/site/issues/2", "labels": "bug, ui", "updated": "y"}],
    })
    prs = await forge.pull_requests(tea, root)
    assert prs == [forge.PullRequest(5, "WIP: cards", "ana", "cards", "main", "open",
                                     "https://codeberg.org/me/site/pulls/5", True, "2026-11-18")]
    assert (await forge.issues(tea, root))[0].labels == ("bug", "ui")
    listed = calls()[0]["args"]
    assert listed[:2] == ["pulls", "list"] and listed[listed.index("--output") + 1] == "json"
    await forge.create_issue(tea, root, "New", "Body")
    assert calls()[-1] == {"args": ["issues", "create", "--title", "New", "--description-file", "-"], "stdin": "Body"}
    await forge.merge(tea, root, 5)
    assert calls()[-1]["args"] == ["pulls", "merge", "--style", "merge", "5"]


async def test_the_program_s_own_words_when_it_fails(tmp_path, fake, monkeypatch):
    root = repo_with_remote(tmp_path / "site", "git@github.com:me/site.git")
    monkeypatch.setenv("FAKE_FORGE_FAIL", "To get started with GitHub CLI, please run:  gh auth login")
    with pytest.raises(forge.ForgeError, match="gh auth login"):
        await forge.pull_requests(forge.Forge("github", forge.Remote("github.com", "me", "site")), root)
