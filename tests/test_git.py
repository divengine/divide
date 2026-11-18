"""divide.run.git: what git prints, read; and git's commands on real repositories."""

import subprocess
from pathlib import Path

import pytest

from divide.run import git

pytestmark = pytest.mark.skipif(git.program() is None, reason="git is not installed")


def sh(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


def repo(root: Path) -> Path:
    sh(root, "init", "-q", "-b", "main")
    sh(root, "config", "user.name", "Test")
    sh(root, "config", "user.email", "test@example.com")
    sh(root, "config", "commit.gpgsign", "false")
    return root


def commit_file(root: Path, name: str, text: str, message: str) -> None:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(text, encoding="utf-8")
    sh(root, "add", name)
    sh(root, "commit", "-q", "-m", message)


# ------------------------------------------------------------------ reading
def test_status_lines_become_changes_in_their_areas():
    text = "\0".join([
        "# branch.oid 1234567890abcdef", "# branch.head main", "# branch.upstream origin/main", "# branch.ab +2 -1",
        "1 M. N... 100644 100644 100644 aaa bbb staged.tpl",
        "1 .M N... 100644 100644 100644 aaa bbb changed.tpl",
        "1 MM N... 100644 100644 100644 aaa bbb both.tpl",
        "2 R. N... 100644 100644 100644 aaa bbb R100 new name.tpl", "old name.tpl",
        "u UU N... 100644 100644 100644 100644 aaa bbb ccc fight.tpl",
        "? fresh/file.tpl", "",
    ])
    status = git.parse_status(text)
    assert (status.branch, status.oid, status.upstream, status.ahead, status.behind) == (
        "main", "1234567890abcdef", "origin/main", 2, 1)
    assert status.area("staged") == [git.Change("staged", "staged.tpl", "M"), git.Change("staged", "both.tpl", "M"),
                                     git.Change("staged", "new name.tpl", "R", "old name.tpl")]
    assert status.area("changes") == [git.Change("changes", "changed.tpl", "M"), git.Change("changes", "both.tpl", "M")]
    assert status.area("conflicts") == [git.Change("conflicts", "fight.tpl", "U")]
    assert status.area("untracked") == [git.Change("untracked", "fresh/file.tpl", "?")]


def test_a_new_repository_and_a_detached_head():
    assert git.parse_status("# branch.oid (initial)\0# branch.head main\0").oid == ""
    detached = git.parse_status("# branch.oid abc\0# branch.head (detached)\0")
    assert detached.detached and detached.clean


def test_the_log_keeps_the_graph_and_its_connecting_rows():
    text = "\n".join([
        f"*   {git.REC}" + git.SEP.join(["a" * 40, "aaaaaaa", "b" * 40 + " " + "c" * 40, "Ana", "ana@x", "100",
                                         "HEAD -> main, origin/main, tag: v1", "Merge branch 'x'"]),
        "|\\  ",
        f"| * {git.REC}" + git.SEP.join(["c" * 40, "ccccccc", "b" * 40, "Bo", "bo@x", "90", "", "On x"]),
        "|/  ",
    ])
    rows = git.parse_log(text)
    assert [r.graph for r in rows] == ["*", "|\\", "| *", "|/"]
    merge, link, side, _end = rows
    assert merge.short == "aaaaaaa" and len(merge.parents) == 2 and merge.time == 100
    assert merge.refs == ("HEAD -> main", "origin/main", "tag: v1")
    assert merge.subject == "Merge branch 'x'"
    assert link.oid == "" and side.author == "Bo" and side.refs == ()


def test_diff_lines_are_told_apart_by_the_hunk_counts():
    text = "\n".join([
        "diff --git a/a.tpl b/a.tpl", "index 1..2 100644", "--- a/a.tpl", "+++ b/a.tpl",
        "@@ -1,3 +1,3 @@ title", " same", "--- a line that was '-- x'", "+new", " same", "\\ No newline at end of file",
        "diff --git a/b.tpl b/b.tpl", "@@ -5 +5 @@", "-old", "+new",
    ])
    assert git.diff_kinds(text) == ["meta", "meta", "meta", "meta", "hunk", "", "del", "add", "", "meta",
                                    "meta", "hunk", "del", "add"]


def test_branch_rows():
    line = git.SEP.join(["*", "refs/heads/main", "main", "origin/main", "ahead 1", "abc1234", "100", "Hi", ""])
    remote = git.SEP.join([" ", "refs/remotes/origin/main", "origin/main", "", "", "abc1234", "100", "Hi", ""])
    head = git.SEP.join([" ", "refs/remotes/origin/HEAD", "origin", "", "", "abc1234", "100", "Hi", "refs/remotes/origin/main"])
    rows = git.parse_branches("\n".join([line, remote, head]))
    assert rows == [git.Branch("main", False, True, "origin/main", "ahead 1", "abc1234", 100, "Hi"),
                    git.Branch("origin/main", True, False, "", "", "abc1234", 100, "Hi")]


@pytest.mark.parametrize("name, ok", [
    ("feature/login", True), ("fix-12", True), ("", False), ("-x", False), ("a..b", False), ("a b", False),
    ("a.lock", False), ("a/", False), (".hidden", False), ("a/.b", False), ("a~1", False), ("a:b", False), ("@", False),
])
def test_branch_names(name, ok):
    assert git.valid_branch_name(name) is ok


def test_the_repository_is_found_from_inside_it(tmp_path):
    root = repo(tmp_path)
    (root / "a" / "b").mkdir(parents=True)
    assert git.find_root(root / "a" / "b") == root.resolve()
    assert git.find_root(tmp_path.parent) is None or git.find_root(tmp_path.parent) != root


# ------------------------------------------------------------------ git's commands
async def test_stage_commit_and_history(tmp_path):
    root = repo(tmp_path)
    assert await git.log(root) == []
    (root / "index.tpl").write_text("Hello\n", encoding="utf-8")
    status = await git.status(root)
    assert status.oid == "" and status.area("untracked") == [git.Change("untracked", "index.tpl", "?")]
    diff = await git.diff_of(root, status.changes[0])
    assert "+Hello" in diff and "@@ -0,0 +1,1 @@" in diff

    await git.stage(root, ["index.tpl"])
    assert (await git.status(root)).area("staged") == [git.Change("staged", "index.tpl", "A")]
    await git.unstage(root, ["index.tpl"])  # before the first commit: there is no HEAD to restore from
    assert (await git.status(root)).area("untracked")
    await git.stage(root, ["index.tpl"])

    result = await git.commit(root, "First page\n\nWith a body.")
    assert result.ok, result.output
    status = await git.status(root)
    assert status.clean and status.branch == "main" and status.oid
    rows = await git.log(root)
    assert [r.subject for r in rows] == ["First page"]
    assert "HEAD -> main" in rows[0].refs
    info = await git.details(root, rows[0].oid)
    assert info.message == "First page\n\nWith a body."
    assert info.files == [("A", "index.tpl")]
    assert "+Hello" in await git.diff_of_commit(root, rows[0].oid)


async def test_changes_diff_and_discard(tmp_path):
    root = repo(tmp_path)
    commit_file(root, "a.tpl", "one\ntwo\n", "a")
    (root / "a.tpl").write_text("one\nTWO\n", encoding="utf-8")
    (root / "junk.txt").write_text("x", encoding="utf-8")
    status = await git.status(root)
    change = status.area("changes")[0]
    diff = await git.diff_of(root, change)
    assert git.diff_kinds(diff).count("add") == 1 and "-two" in diff and "+TWO" in diff
    await git.discard(root, change)
    await git.discard(root, status.area("untracked")[0])
    assert (await git.status(root)).clean
    assert (root / "a.tpl").read_text(encoding="utf-8") == "one\ntwo\n"


async def test_amend_keeps_one_commit(tmp_path):
    root = repo(tmp_path)
    commit_file(root, "a.tpl", "1", "first")
    (root / "b.tpl").write_text("2", encoding="utf-8")
    await git.stage(root, ["b.tpl"])
    assert await git.last_message(root) == "first"
    assert (await git.commit(root, "first, with b", amend=True)).ok
    rows = await git.log(root)
    assert [r.subject for r in rows] == ["first, with b"]
    assert sorted(p for _c, p in (await git.details(root, rows[0].oid)).files) == ["a.tpl", "b.tpl"]


async def test_branches_switch_create_delete(tmp_path):
    root = repo(tmp_path)
    commit_file(root, "a.tpl", "1", "first")
    await git.create_branch(root, "feature/x")
    assert (await git.status(root)).branch == "feature/x"
    commit_file(root, "b.tpl", "2", "on x")
    names = {b.name: b for b in await git.branches(root)}
    assert set(names) == {"main", "feature/x"} and names["feature/x"].current
    await git.switch(root, names["main"])
    assert (await git.status(root)).branch == "main"
    with pytest.raises(git.GitError, match="not fully merged"):
        await git.delete_branch(root, "feature/x")
    await git.delete_branch(root, "feature/x", force=True)
    assert [b.name for b in await git.branches(root)] == ["main"]
    graph = await git.log(root)
    assert graph[0].graph.startswith("*")


async def test_push_pull_and_a_remote_branch(tmp_path):
    origin = tmp_path / "origin.git"
    sh(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    (tmp_path / "one").mkdir()
    one = repo(tmp_path / "one")
    commit_file(one, "a.tpl", "1", "first")
    sh(one, "remote", "add", "origin", str(origin))
    lines: list[str] = []
    result = await git.push(one, await git.status(one), on_line=lines.append)
    assert result.ok, result.output
    status = await git.status(one)
    assert status.upstream == "origin/main" and status.ahead == 0  # the first push set it up

    (tmp_path / "two").mkdir()
    sh(tmp_path, "clone", "-q", str(origin), "two")
    two = tmp_path / "two"
    sh(two, "config", "user.name", "Two")
    sh(two, "config", "user.email", "two@example.com")
    sh(two, "switch", "-q", "-c", "topic")
    commit_file(two, "t.tpl", "t", "topic work")
    sh(two, "push", "-q", "-u", "origin", "topic")
    commit_file(one, "b.tpl", "2", "second")
    assert (await git.push(one, await git.status(one))).ok

    assert (await git.fetch(two)).ok
    remote = next(b for b in await git.branches(two) if b.name == "origin/main")
    await git.switch(two, remote)  # main exists: switch to it
    assert (await git.status(two)).behind == 1
    assert (await git.pull(two)).ok
    assert (two / "b.tpl").exists()

    assert (await git.fetch(one)).ok
    topic = next(b for b in await git.branches(one) if b.name == "origin/topic")
    await git.switch(one, topic)  # no local topic yet: one that tracks it
    status = await git.status(one)
    assert status.branch == "topic" and status.upstream == "origin/topic"


def test_marks_for_the_project_window(tmp_path):
    root = tmp_path
    status = git.parse_status("\0".join([
        "1 M. N... 100644 100644 100644 a b parts/nav.tpl",
        "1 .M N... 100644 100644 100644 a b parts/nav.tpl",  # staged and changed again: the working tree's
        "u UU N... 100644 100644 100644 100644 a b c fight.tpl",
        "? parts/deep/new.tpl", "! vendor/", "",
    ]))
    files, folders, ignored = git.marks(status, root)
    assert files == {root / "parts/nav.tpl": "M", root / "fight.tpl": "U", root / "parts/deep/new.tpl": "?"}
    assert folders == {root / "parts", root / "parts/deep"}
    assert ignored == {root / "vendor"}


async def test_status_with_the_ignored(tmp_path):
    root = repo(tmp_path)
    (root / ".gitignore").write_text("vendor/\n*.log\n", encoding="utf-8")
    (root / "vendor" / "x").mkdir(parents=True)
    (root / "vendor" / "x" / "a.php").write_text("a", encoding="utf-8")
    (root / "debug.log").write_text("a", encoding="utf-8")
    assert (await git.status(root)).ignored == []
    assert sorted((await git.status(root, ignored=True)).ignored) == ["debug.log", "vendor/"]
