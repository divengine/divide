"""Git for a project (UI-independent): what changed, the history, the branches, and git's own commands.

divide runs the ``git`` of the system for everything, as a person would in a
terminal: it reads what git prints in its machine formats (``status
--porcelain=v2``, ``for-each-ref``, ``log`` with separators) and lets git do
every change (``add``, ``commit``, ``switch``, ``pull``, ``push``...), with its
output line by line.

git never asks anything here: there is no terminal to answer it. Its own
prompts are off (``GIT_TERMINAL_PROMPT=0``) and, on Linux and macOS, it runs in
a session of its own, so ssh cannot ask for a passphrase on divide's screen:
a remote that needs one fails and says so (an ssh agent or a credential
helper answers for you).
"""

from __future__ import annotations

from divide.i18n import _

import asyncio
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from divide.run import children

MAX_DIFF_LINES = 20000  # a longer diff is cut there (the rest is not shown)
SEP = "\x1f"  # between the fields git prints for us (str.splitlines() would cut at \x1e: see lines())
REC = "\x1e"  # before each commit of the log (the graph is before it)


def lines(text: str) -> list[str]:
    """The lines of git's output: only \n ends one (str.splitlines() also cuts at the separators)."""
    out = text.split("\n")
    if out and out[-1] == "":
        out.pop()
    return [line.removesuffix("\r") for line in out]


class GitError(RuntimeError):
    """git could not do it (not found, or it failed: the message is git's)."""


def program() -> str | None:
    """The git command, or None when it is not installed."""
    return shutil.which("git")


def find_root(path: Path) -> Path | None:
    """The repository holding ``path`` (the folder with ``.git``), or None. Without running git."""
    try:
        here = path.resolve()
    except OSError:
        return None
    for folder in (here, *here.parents):
        if (folder / ".git").exists():
            return folder
    return None


@dataclass(frozen=True)
class Result:
    code: int
    output: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def _env() -> dict[str, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "PAGER": "cat", "GCM_INTERACTIVE": "never"}
    env.pop("GIT_DIR", None)  # the repository is the one of cwd
    env.pop("GIT_WORK_TREE", None)
    return env


def _options() -> dict:
    options = children.options()
    if sys.platform != "win32":
        options["start_new_session"] = True  # no terminal of divide's for ssh to ask on
    return options


BASE = ["-c", "core.quotepath=false", "-c", "color.ui=false", "--no-pager"]


async def run(args: list[str], cwd: Path, on_line: Callable[[str], None] | None = None,
              on_progress: Callable[[str], None] | None = None, stdin: str | None = None,
              timeout: float | None = None) -> Result:
    """``git args`` in ``cwd``. Its output (both streams) goes line by line to ``on_line``;
    the lines git rewrites in place (``Receiving objects: 45%``) go to ``on_progress``.
    Cancelling the task stops git."""
    git = program()
    if git is None:
        raise GitError(_('git was not found: install it (https://git-scm.com) and start divide again'))
    try:
        proc = children.track(await asyncio.create_subprocess_exec(
            git, *BASE, *args, cwd=str(cwd), env=_env(),
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, **_options(),
        ))
    except OSError as exc:
        raise GitError(_('git could not start: {exc}').format(exc=exc)) from None
    output: list[str] = []

    async def feed() -> None:
        if stdin is not None and proc.stdin is not None:
            proc.stdin.write(stdin.encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()

    async def pump() -> None:
        assert proc.stdout is not None
        pending = b""
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            pending += chunk
            while True:
                match = re.search(rb"[\r\n]", pending)
                if match is None:
                    break
                end = match.start()
                text = pending[:end].decode("utf-8", "replace")
                ending = pending[end:end + 1]
                pending = pending[end + 1:]
                if ending == b"\r":
                    if pending.startswith(b"\n"):  # \r\n: a whole line
                        pending = pending[1:]
                    else:
                        if text and on_progress is not None:
                            on_progress(text)
                        continue
                output.append(text)
                if on_line is not None:
                    on_line(text)
        if pending:
            text = pending.decode("utf-8", "replace")
            output.append(text)
            if on_line is not None:
                on_line(text)

    try:
        await asyncio.wait_for(asyncio.gather(feed(), pump(), proc.wait()), timeout)
    except (asyncio.CancelledError, TimeoutError):
        children.kill(proc)
        await asyncio.shield(proc.wait())
        raise
    return Result(proc.returncode or 0, "\n".join(output))


async def capture(args: list[str], cwd: Path, timeout: float = 60.0) -> str:
    """What ``git args`` prints; GitError (with git's message) when it fails."""
    result = await run(args, cwd, timeout=timeout)
    if not result.ok:
        raise GitError(result.output.strip() or _('git {command} failed').format(command=args[0]))
    return result.output


async def must(args: list[str], cwd: Path, stdin: str | None = None) -> str:
    """Run a change (``add``, ``switch``...): GitError with git's message when it fails."""
    result = await run(args, cwd, stdin=stdin, timeout=120.0)
    if not result.ok:
        raise GitError(result.output.strip() or _('git {command} failed').format(command=args[0]))
    return result.output


# ------------------------------------------------------------------ status
@dataclass(frozen=True)
class Change:
    """A file in one of the areas: ``staged`` (in the index), ``changes`` (the working
    tree), ``untracked`` or ``conflicts``. ``code``: git's letter (M, A, D, R, C, T, U, ?)."""

    area: str
    path: str  # relative to the repository, with /
    code: str
    orig: str = ""  # a rename's or a copy's old path


@dataclass
class Status:
    branch: str = ""  # "" when detached
    oid: str = ""  # "" before the first commit
    upstream: str = ""
    ahead: int = 0
    behind: int = 0
    changes: list[Change] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)  # what .gitignore leaves out (a folder ends in /)

    @property
    def detached(self) -> bool:
        return not self.branch

    def area(self, name: str) -> list[Change]:
        return [c for c in self.changes if c.area == name]

    @property
    def clean(self) -> bool:
        return not self.changes


def parse_status(text: str) -> Status:
    """``git status --porcelain=v2 --branch -z``."""
    status = Status()
    fields = text.split("\0")
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if not entry:
            continue
        if entry.startswith("# "):
            key, _sep, value = entry[2:].partition(" ")
            if key == "branch.oid":
                status.oid = "" if value == "(initial)" else value
            elif key == "branch.head":
                status.branch = "" if value == "(detached)" else value
            elif key == "branch.upstream":
                status.upstream = value
            elif key == "branch.ab":
                ahead, _sep, behind = value.partition(" ")
                status.ahead, status.behind = int(ahead.lstrip("+") or 0), int(behind.lstrip("-") or 0)
            continue
        kind = entry[0]
        if kind == "?":
            status.changes.append(Change("untracked", entry[2:], "?"))
        elif kind == "!":
            status.ignored.append(entry[2:])
        elif kind == "1":
            parts = entry.split(" ", 8)
            _add(status, parts[1], parts[8])
        elif kind == "2":
            parts = entry.split(" ", 9)
            orig = fields[i] if i < len(fields) else ""
            i += 1
            _add(status, parts[1], parts[9], orig)
        elif kind == "u":
            parts = entry.split(" ", 10)
            status.changes.append(Change("conflicts", parts[10], "U"))
    return status


def _add(status: Status, xy: str, path: str, orig: str = "") -> None:
    x, y = xy[0], xy[1]
    if x != ".":
        status.changes.append(Change("staged", path, x, orig))
    if y != ".":
        status.changes.append(Change("changes", path, y, orig if x == "." else ""))


async def status(root: Path, ignored: bool = False) -> Status:
    """What changed; with ``ignored``, also what .gitignore leaves out (a whole ignored folder
    is one entry, ``vendor/``)."""
    args = ["--no-optional-locks", "status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all"]
    out = await capture([*args, *(["--ignored=matching"] if ignored else [])], root)
    return parse_status(out)


def marks(status: Status, root: Path) -> tuple[dict[Path, str], set[Path], set[Path]]:
    """For the project window: each changed file's letter (a conflict first, then the
    working tree's, then the index's), the folders that hold changes, the ignored paths."""
    files: dict[Path, str] = {}
    rank = {"conflicts": 0, "untracked": 1, "changes": 2, "staged": 3}
    best: dict[Path, int] = {}
    for change in status.changes:
        path = root / change.path
        if rank[change.area] < best.get(path, 9):
            best[path] = rank[change.area]
            files[path] = change.code
    folders: set[Path] = set()
    for path in files:
        for parent in path.parents:
            if parent == root or root not in parent.parents:
                break
            folders.add(parent)
    ignored = {root / entry.rstrip("/") for entry in status.ignored}
    return files, folders, ignored


# ------------------------------------------------------------------ history
@dataclass(frozen=True)
class Commit:
    """A row of the log: the graph's drawing at its left, then the commit (none on a
    row that only carries the graph's lines on)."""

    graph: str
    oid: str = ""
    short: str = ""
    parents: tuple[str, ...] = ()
    author: str = ""
    email: str = ""
    time: int = 0
    refs: tuple[str, ...] = ()
    subject: str = ""


LOG_FORMAT = REC + SEP.join(["%H", "%h", "%P", "%an", "%ae", "%at", "%D", "%s"])


def parse_log(text: str) -> list[Commit]:
    """``git log --graph --format=LOG_FORMAT``."""
    rows = []
    for line in lines(text):
        graph, sep, rest = line.partition(REC)
        if not sep:
            if line.strip():
                rows.append(Commit(graph=line.rstrip()))
            continue
        parts = rest.split(SEP)
        if len(parts) < 8:
            continue
        oid, short, parents, author, email, at, refs, subject = parts[:8]
        rows.append(Commit(
            graph=graph.rstrip(), oid=oid, short=short, parents=tuple(parents.split()), author=author, email=email,
            time=int(at or 0), refs=tuple(r.strip() for r in refs.split(",") if r.strip()), subject=subject,
        ))
    return rows


async def log(root: Path, limit: int = 400, path: str | None = None, everything: bool = True) -> list[Commit]:
    """The history, newest first, with its graph: every branch (``everything``) or the current one;
    only the commits that touched ``path`` when it is given (following its renames)."""
    args = ["log", "--graph", f"--format={LOG_FORMAT}", f"--max-count={limit}"]
    if path:
        args = ["log", f"--format={LOG_FORMAT}", f"--max-count={limit}", "--follow", "--", path]
    elif everything:
        args.append("--all")
    try:
        return parse_log(await capture(args, root))
    except GitError as exc:
        if "does not have any commits" in str(exc) or "bad default revision" in str(exc):
            return []
        raise


@dataclass(frozen=True)
class Details:
    message: str
    committer: str
    committed: int
    files: list[tuple[str, str]]  # (code, path): what the commit changed (a merge: against its first parent)


async def details(root: Path, oid: str) -> Details:
    head = await capture(["show", "-s", f"--format=%cn <%ce>{SEP}%ct{SEP}%B", oid], root)
    committer, _sep, rest = head.partition(SEP)
    when, _sep, message = rest.partition(SEP)
    names = await capture(["show", "--format=", "--name-status", "-z", "--diff-merges=first-parent", oid], root)
    files: list[tuple[str, str]] = []
    parts = names.strip("\0\n").split("\0")
    i = 0
    while i < len(parts):
        code = parts[i].strip()
        i += 1
        if not code:
            continue
        if code[0] in "RC" and i + 1 < len(parts):
            files.append((code[0], f"{parts[i]} -> {parts[i + 1]}"))
            i += 2
        elif i < len(parts):
            files.append((code[0], parts[i]))
            i += 1
    return Details(message.strip(), committer, int(when or 0), files)


# ------------------------------------------------------------------ blame
@dataclass(frozen=True)
class BlameLine:
    """A line of a file and the commit that last changed it (``oid`` all zeros: not committed yet)."""

    oid: str
    author: str
    time: int
    summary: str
    text: str

    @property
    def committed(self) -> bool:
        return self.oid.strip("0") != ""


def parse_blame(text: str) -> list[BlameLine]:
    """``git blame --porcelain``: a header per line, the commit's details the first time it comes."""
    out: list[BlameLine] = []
    info: dict[str, dict[str, str]] = {}
    oid = ""
    for line in lines(text):
        if line.startswith("\t"):
            d = info.get(oid, {})
            out.append(BlameLine(oid, d.get("author", ""), int(d.get("author-time", "0") or 0), d.get("summary", ""), line[1:]))
            continue
        head, _sep, rest = line.partition(" ")
        if len(head) == 40 and all(c in "0123456789abcdef" for c in head):
            oid = head
            info.setdefault(oid, {})
        elif oid:
            info[oid][head] = rest
    return out


async def blame(root: Path, path: str, contents: str | None = None) -> list[BlameLine]:
    """Who changed each line last; with ``contents`` (an editor's unsaved text), of that text."""
    args = ["blame", "--porcelain", *(["--contents", "-"] if contents is not None else []), "--", path]
    result = await run(args, root, stdin=contents, timeout=120.0)
    if not result.ok:
        raise GitError(result.output.strip() or _('git blame failed'))
    return parse_blame(result.output)


# ------------------------------------------------------------------ diffs
async def diff_of(root: Path, change: Change) -> str:
    """What changed in a file: the index against HEAD (staged), the working tree
    against the index (changes, conflicts), or the whole new file (untracked)."""
    if change.area == "untracked":
        return new_file_diff(root, change.path)
    args = ["diff", "--no-ext-diff", "--find-renames"]
    if change.area == "staged":
        args.append("--cached")
    return _cut(await capture([*args, "--", change.path, *([change.orig] if change.orig else [])], root))


async def diff_of_commit(root: Path, oid: str, path: str | None = None) -> str:
    """A commit: its header, the files it changed and their diff (a merge: against its first parent)."""
    args = ["show", "--no-ext-diff", "--format=fuller", "--stat", "--patch", "--diff-merges=first-parent", oid]
    return _cut(await capture([*args, *(["--", path] if path else [])], root))


async def head_text(root: Path, path: str) -> str | None:
    """The file as the last commit has it (None: not in it, or no commit yet)."""
    result = await run(["show", f"HEAD:{path}"], root, timeout=30.0)
    return result.output + "\n" if result.ok else None


def line_changes(old: str, new: str) -> dict[int, str]:
    """The rows of ``new`` (0-based) that differ from ``old``: ``add`` (new lines), ``mod``
    (changed ones) and ``del`` (lines were removed just before this row; after the last
    row, on the last one)."""
    import difflib

    a, b = old.splitlines(), new.splitlines()
    rows: dict[int, str] = {}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "insert":
            rows.update({j: "add" for j in range(j1, j2)})
        elif tag == "replace":  # as many changed as there were, the rest new
            rows.update({j: "mod" if j - j1 < i2 - i1 else "add" for j in range(j1, j2)})
        elif tag == "delete" and b:
            rows.setdefault(min(j1, len(b) - 1), "del")
    return rows


def new_file_diff(root: Path, path: str) -> str:
    """The diff git would show for a new file (``git diff`` does not show untracked ones)."""
    file = root / path
    header = f"diff --git a/{path} b/{path}\nnew file\n--- /dev/null\n+++ b/{path}\n"
    try:
        data = file.read_bytes() if file.is_file() else b""
    except OSError as exc:
        return header + f"({exc})\n"
    if b"\0" in data[:8000]:
        return f"diff --git a/{path} b/{path}\nnew file\nBinary files /dev/null and b/{path} differ\n"
    rows = data.decode("utf-8", "replace").splitlines()
    if not rows:
        return header
    return _cut(header + f"@@ -0,0 +1,{len(rows)} @@\n" + "".join(f"+{line}\n" for line in rows))


def _cut(text: str) -> str:
    rows = lines(text)
    if len(rows) <= MAX_DIFF_LINES:
        return text
    rest = len(rows) - MAX_DIFF_LINES
    return "\n".join(rows[:MAX_DIFF_LINES]) + "\n" + _('... {count} more lines not shown').format(count=rest) + "\n"


HUNK = re.compile(r"^@@+ -(\d+)(?:,(\d+))? .*?\+(\d+)(?:,(\d+))? @@")
META = ("diff ", "index ", "--- ", "+++ ", "new file", "deleted file", "old mode", "new mode", "similarity ",
        "dissimilarity ", "rename ", "copy ", "Binary files", "commit ", "Author:", "AuthorDate:", "Commit:",
        "CommitDate:", "Date:", "Merge:", "\\ ")


def diff_kinds(text: str) -> list[str]:
    """What each line of a diff is: ``add``, ``del``, ``hunk``, ``meta`` (headers) or ``""``
    (context, a commit's message, the stat). Inside a hunk the counts in its ``@@`` say where
    it ends, so a removed line that reads ``-- x`` is not taken for a header."""
    kinds = []
    old = new = 0
    for line in lines(text):
        if old > 0 or new > 0:
            first = line[:1]
            if first == "+":
                new -= 1
                kinds.append("add")
            elif first == "-":
                old -= 1
                kinds.append("del")
            elif first == "\\":
                kinds.append("meta")
            else:
                old -= 1
                new -= 1
                kinds.append("")
            continue
        match = HUNK.match(line)
        if match:
            old = int(match.group(2)) if match.group(2) is not None else 1
            new = int(match.group(4)) if match.group(4) is not None else 1
            kinds.append("hunk")
        elif line.startswith(META):
            kinds.append("meta")
        else:
            kinds.append("")
    return kinds


# ------------------------------------------------------------------ branches
@dataclass(frozen=True)
class Branch:
    name: str  # main, origin/main
    remote: bool
    current: bool = False
    upstream: str = ""
    track: str = ""  # "ahead 1, behind 2", "gone"
    short: str = ""
    time: int = 0
    subject: str = ""


BRANCH_FORMAT = "%1f".join(["%(HEAD)", "%(refname)", "%(refname:short)", "%(upstream:short)",
                            "%(upstream:track,nobracket)", "%(objectname:short)", "%(committerdate:unix)",
                            "%(contents:subject)", "%(symref)"])


def parse_branches(text: str) -> list[Branch]:
    out = []
    for line in lines(text):
        parts = line.split(SEP)
        if len(parts) < 9:
            continue
        head, ref, short_name, upstream, track, oid, when, subject, symref = parts[:9]
        if symref:  # origin/HEAD -> origin/main
            continue
        out.append(Branch(short_name, ref.startswith("refs/remotes/"), head.strip() == "*", upstream, track, oid,
                          int(when or 0), subject))
    return out


async def branches(root: Path) -> list[Branch]:
    out = await capture(["for-each-ref", f"--format={BRANCH_FORMAT}", "--sort=-committerdate", "refs/heads", "refs/remotes"], root)
    return parse_branches(out)


async def remotes(root: Path) -> list[str]:
    return (await capture(["remote"], root)).split()


# ------------------------------------------------------------------ changes
async def has_commits(root: Path) -> bool:
    return (await run(["rev-parse", "--verify", "-q", "HEAD"], root)).ok


async def stage(root: Path, paths: list[str]) -> None:
    await must(["add", "--all", "--", *paths], root)


async def unstage(root: Path, paths: list[str]) -> None:
    if await has_commits(root):
        await must(["restore", "--staged", "--", *paths], root)
    else:  # nothing to restore from yet
        await must(["rm", "--cached", "-r", "-q", "--", *paths], root)


async def discard(root: Path, change: Change) -> None:
    """Throw away a file's changes in the working tree; an untracked file is deleted."""
    if change.area == "untracked":
        target = root / change.path
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
        return
    await must(["restore", "--worktree", "--", change.path], root)


async def commit(root: Path, message: str, amend: bool = False, on_line: Callable[[str], None] | None = None) -> Result:
    """``git commit`` with ``message`` (its hooks run: their output goes to ``on_line``)."""
    return await run(["commit", "--file=-", *(["--amend"] if amend else [])], root, on_line=on_line, stdin=message,
                     timeout=600.0)


async def last_message(root: Path) -> str:
    return (await capture(["log", "-1", "--format=%B"], root)).strip()


async def switch(root: Path, branch: Branch) -> None:
    """Make ``branch`` the current one; a remote one gets its local branch, tracking it."""
    if branch.remote:
        local = branch.name.split("/", 1)[1]
        mine = {b.name for b in await branches(root) if not b.remote}
        if local in mine:
            await must(["switch", local], root)
        else:
            await must(["switch", "--track", branch.name], root)
    else:
        await must(["switch", branch.name], root)


async def create_branch(root: Path, name: str, start: str = "", switch_to: bool = True) -> None:
    if switch_to:
        await must(["switch", "--create", name, *([start] if start else [])], root)
    else:
        await must(["branch", name, *([start] if start else [])], root)


async def delete_branch(root: Path, name: str, force: bool = False) -> None:
    await must(["branch", "--delete", *(["--force"] if force else []), name], root)


def valid_branch_name(name: str) -> bool:
    """git's rules for a branch name (``git check-ref-format --branch``), without running git."""
    if not name or name.startswith(("-", "/")) or name.endswith(("/", ".", ".lock")) or name == "@":
        return False
    if any(part.startswith(".") for part in name.split("/")):
        return False
    return not re.search(r"\.\.|//|@\{|[\x00-\x20\x7f~^:?*\[\\]", name)


# ------------------------------------------------------------------ remotes
async def fetch(root: Path, on_line=None, on_progress=None) -> Result:
    return await run(["fetch", "--all", "--prune", "--progress"], root, on_line, on_progress)


async def pull(root: Path, on_line=None, on_progress=None) -> Result:
    return await run(["pull", "--progress"], root, on_line, on_progress)


async def push(root: Path, status: Status, on_line=None, on_progress=None) -> Result:
    """``git push``; a branch with no upstream yet goes to the first remote and tracks it."""
    if status.branch and not status.upstream:
        names = await remotes(root)
        if names:
            remote = "origin" if "origin" in names else names[0]
            return await run(["push", "--progress", "--set-upstream", remote, status.branch], root, on_line, on_progress)
    return await run(["push", "--progress"], root, on_line, on_progress)


# ------------------------------------------------------------------ merging
async def merging(root: Path) -> bool:
    """A merge stopped halfway (its conflicts to solve, then a commit)."""
    return (await run(["rev-parse", "-q", "--verify", "MERGE_HEAD"], root)).ok


async def merge_message(root: Path) -> str:
    """The message git prepared for the merge's commit (its comment lines left out)."""
    path = (await capture(["rev-parse", "--git-path", "MERGE_MSG"], root)).strip()
    file = Path(path) if Path(path).is_absolute() else root / path
    try:
        text = file.read_text(encoding="utf-8")
    except OSError:
        return ""
    return "\n".join(line for line in text.splitlines() if not line.startswith("#")).strip()


async def merge(root: Path, branch: str, on_line=None) -> Result:
    """``git merge`` of ``branch`` into the current one: a conflict leaves it halfway (exit 1)."""
    return await run(["merge", "--no-edit", branch], root, on_line=on_line, timeout=600.0)


async def abort_merge(root: Path) -> None:
    await must(["merge", "--abort"], root)


def conflict_kinds(text: str) -> list[str]:
    """A file in conflict: git's markers (``meta``), our side (``mod``), theirs (``add``)."""
    kinds, side = [], ""
    for line in lines(text):
        if line.startswith("<<<<<<<"):
            kinds.append("meta")
            side = "mod"
        elif line.startswith("|||||||") and side:
            kinds.append("meta")
            side = "base"
        elif line.startswith("=======") and side:
            kinds.append("meta")
            side = "add"
        elif line.startswith(">>>>>>>") and side:
            kinds.append("meta")
            side = ""
        else:
            kinds.append("" if side == "base" else side)
    return kinds


# ------------------------------------------------------------------ stashes
@dataclass(frozen=True)
class Stash:
    ref: str  # stash@{0}
    time: int
    message: str  # "On main: work in progress"


def parse_stashes(text: str) -> list[Stash]:
    out = []
    for line in lines(text):
        parts = line.split(SEP)
        if len(parts) >= 3:
            out.append(Stash(parts[0], int(parts[1] or 0), parts[2]))
    return out


async def stashes(root: Path) -> list[Stash]:
    return parse_stashes(await capture(["stash", "list", f"--format=%gd{SEP}%ct{SEP}%gs"], root))


async def stash(root: Path, message: str = "") -> None:
    """Put the changes aside (the untracked files too) and leave the last commit's files."""
    await must(["stash", "push", "--include-untracked", *(["--message", message] if message else [])], root)


async def unstash(root: Path, ref: str, keep: bool = False) -> None:
    """Bring a stash's changes back; without ``keep`` the stash goes (``pop``)."""
    await must(["stash", "apply" if keep else "pop", ref], root)


async def drop_stash(root: Path, ref: str) -> None:
    await must(["stash", "drop", ref], root)
