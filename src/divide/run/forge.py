"""The repository's forge (UI-independent): GitHub through ``gh``, Gitea through ``tea``.

divide does not talk to the forges itself: their own command line programs do
it, signed in as you are (``gh auth login``, ``tea login add``). The forge is
the one of the ``origin`` remote (else the first one): github.com is GitHub;
any other host is Gitea when ``tea`` is installed (Forgejo and Codeberg speak
Gitea's language too). Pull requests and issues are read as JSON and changed
by the programs (``gh pr create``, ``tea pulls merge``...), which never ask:
there is no terminal to answer them.
"""

from __future__ import annotations

from divide.i18n import _

import asyncio
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from divide.run import children, git

# The programs, by forge (tests put fakes here).
COMMANDS: dict[str, list[str] | None] = {}


def command(kind: str) -> list[str] | None:
    if kind in COMMANDS:
        return COMMANDS[kind]
    found = shutil.which({"github": "gh", "gitea": "tea"}[kind])
    return [found] if found else None


class ForgeError(RuntimeError):
    """The forge's program could not do it (its own words)."""


@dataclass(frozen=True)
class Remote:
    host: str
    owner: str
    repo: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_remote(url: str) -> Remote | None:
    """``git@github.com:owner/repo.git``, ``https://host/owner/repo``, ``ssh://git@host:2222/owner/repo.git``."""
    url = url.strip()
    match = (re.match(r"^[a-z+]+://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+?)/([^/]+?)(?:\.git)?/?$", url)
             or re.match(r"^(?:[^@/]+@)?([^/:]+):(?!/)(.+?)/([^/]+?)(?:\.git)?/?$", url))
    if match is None:
        return None
    host, owner, repo = match.groups()
    return Remote(host.lower(), owner, repo)


@dataclass(frozen=True)
class Forge:
    kind: str  # "github" | "gitea"
    remote: Remote

    @property
    def name(self) -> str:
        return "GitHub" if self.kind == "github" else "Gitea"

    @property
    def program(self) -> str:
        return "gh" if self.kind == "github" else "tea"


async def detect(root: Path) -> tuple[Forge | None, str]:
    """The forge of the repository's remote, or None and why (for the user)."""
    names = await git.remotes(root)
    if not names:
        return None, _('The repository has no remote: add one in a terminal (git remote add origin <url>).')
    name = "origin" if "origin" in names else names[0]
    url = (await git.capture(["remote", "get-url", name], root)).strip()
    remote = parse_remote(url)
    if remote is None:
        return None, _('The remote {name} ({url}) is not on a forge divide knows.').format(name=name, url=url)
    if remote.host == "github.com":
        if command("github") is None:
            return None, _('The repository is on GitHub: install gh (https://cli.github.com) and sign in with gh auth login.')
        return Forge("github", remote), ""
    if command("gitea") is None:
        return None, _('{host} is not GitHub: for Gitea, Forgejo or Codeberg install tea (https://gitea.com/gitea/tea) '
                       'and sign in with tea login add.').format(host=remote.host)
    return Forge("gitea", remote), ""


async def _run(forge: Forge, args: list[str], root: Path, stdin: str | None = None, timeout: float = 120.0) -> str:
    program = command(forge.kind)
    if program is None:
        raise ForgeError(_('{program} was not found').format(program=forge.program))
    env = {**os.environ, "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "NO_COLOR": "1",
           "GH_PAGER": "cat", "PAGER": "cat", "GIT_TERMINAL_PROMPT": "0"}
    options = children.options()
    if os.name != "nt":
        options["start_new_session"] = True  # nothing of divide's screen to ask on
    try:
        proc = children.track(await asyncio.create_subprocess_exec(
            *program, *args, cwd=str(root), env=env,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **options,
        ))
    except OSError as exc:
        raise ForgeError(_('{program} could not start: {exc}').format(program=forge.program, exc=exc)) from None
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin.encode("utf-8") if stdin is not None else None), timeout)
    except (asyncio.CancelledError, TimeoutError):
        children.kill(proc)
        await asyncio.shield(proc.wait())
        raise
    if proc.returncode:
        message = (err or out).decode("utf-8", "replace").strip()
        raise ForgeError(message or _('{program} failed').format(program=forge.program))
    return out.decode("utf-8", "replace")


def _json(text: str) -> list[dict]:
    start = min((i for i in (text.find("["), text.find("{")) if i >= 0), default=-1)
    if start < 0:
        return []
    data = json.loads(text[start:])
    return data if isinstance(data, list) else [data]


def _login(value) -> str:
    if isinstance(value, dict):
        return str(value.get("login") or value.get("username") or value.get("name") or "")
    return str(value or "")


def _labels(value) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(v.get("name", "")) if isinstance(v, dict) else str(v) for v in value)
    if isinstance(value, str):
        return tuple(x.strip() for x in value.split(",") if x.strip())
    return ()


# ------------------------------------------------------------------ pull requests
@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    author: str
    head: str  # the branch it brings
    base: str  # the branch it goes into
    state: str
    url: str
    draft: bool = False
    updated: str = ""


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    author: str
    state: str
    url: str
    labels: tuple[str, ...] = ()
    updated: str = ""


def _number(value) -> int:
    try:
        return int(str(value).lstrip("#"))
    except ValueError:
        return 0


def pull_requests_of(kind: str, text: str) -> list[PullRequest]:
    out = []
    for d in _json(text):
        if kind == "github":
            out.append(PullRequest(_number(d.get("number")), d.get("title", ""), _login(d.get("author")),
                                   d.get("headRefName", ""), d.get("baseRefName", ""), str(d.get("state", "")).lower(),
                                   d.get("url", ""), bool(d.get("isDraft")), d.get("updatedAt", "")))
        else:
            title = d.get("title", "")
            out.append(PullRequest(_number(d.get("index")), title, _login(d.get("author")), d.get("head", ""),
                                   d.get("base", ""), str(d.get("state", "")).lower(), d.get("url", ""),
                                   title.upper().startswith(("WIP:", "[WIP]")), str(d.get("updated", ""))))
    return out


def issues_of(kind: str, text: str) -> list[Issue]:
    out = []
    for d in _json(text):
        if kind == "github":
            out.append(Issue(_number(d.get("number")), d.get("title", ""), _login(d.get("author")),
                             str(d.get("state", "")).lower(), d.get("url", ""), _labels(d.get("labels")),
                             d.get("updatedAt", "")))
        else:
            out.append(Issue(_number(d.get("index")), d.get("title", ""), _login(d.get("author")),
                             str(d.get("state", "")).lower(), d.get("url", ""), _labels(d.get("labels")),
                             str(d.get("updated", ""))))
    return out


async def pull_requests(forge: Forge, root: Path) -> list[PullRequest]:
    """The open pull requests."""
    if forge.kind == "github":
        args = ["pr", "list", "--state", "open", "--limit", "100", "--json",
                "number,title,author,headRefName,baseRefName,state,url,isDraft,updatedAt"]
    else:
        args = ["pulls", "list", "--state", "open", "--limit", "100", "--output", "json",
                "--fields", "index,title,state,author,head,base,url,updated"]
    return pull_requests_of(forge.kind, await _run(forge, args, root))


async def issues(forge: Forge, root: Path) -> list[Issue]:
    """The open issues."""
    if forge.kind == "github":
        args = ["issue", "list", "--state", "open", "--limit", "100", "--json",
                "number,title,author,state,url,labels,updatedAt"]
    else:
        args = ["issues", "list", "--state", "open", "--limit", "100", "--kind", "issues", "--output", "json",
                "--fields", "index,title,state,author,url,labels,updated"]
    return issues_of(forge.kind, await _run(forge, args, root))


async def create_pull_request(forge: Forge, root: Path, title: str, body: str, head: str, base: str,
                              draft: bool = False) -> str:
    """A pull request of ``head`` (already pushed) into ``base``; what the program printed (its URL)."""
    if forge.kind == "github":
        args = ["pr", "create", "--title", title, "--body-file", "-", "--head", head, "--base", base,
                *(["--draft"] if draft else [])]
    else:
        args = ["pulls", "create", "--title", title, "--description-file", "-", "--head", head, "--base", base,
                *(["--draft"] if draft else [])]
    return (await _run(forge, args, root, stdin=body)).strip()


async def create_issue(forge: Forge, root: Path, title: str, body: str) -> str:
    if forge.kind == "github":
        args = ["issue", "create", "--title", title, "--body-file", "-"]
    else:
        args = ["issues", "create", "--title", title, "--description-file", "-"]
    return (await _run(forge, args, root, stdin=body)).strip()


async def checkout(forge: Forge, root: Path, number: int) -> None:
    """The pull request's branch, checked out here."""
    if forge.kind == "github":
        await _run(forge, ["pr", "checkout", str(number)], root)
    else:
        await _run(forge, ["pulls", "checkout", "--branch", str(number)], root)


async def merge(forge: Forge, root: Path, number: int, style: str = "merge") -> None:
    """Merge the pull request on the forge (``merge``, ``squash`` or ``rebase``)."""
    if forge.kind == "github":
        await _run(forge, ["pr", "merge", str(number), f"--{style}"], root)
    else:
        await _run(forge, ["pulls", "merge", "--style", style, str(number)], root)


def url_of(text: str) -> str:
    """The first web address in what a program printed (the new pull request's, the issue's)."""
    match = re.search(r"https?://\S+", text)
    return match.group(0) if match else ""
