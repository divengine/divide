"""Composer for a project (UI-independent): its packages, and composer's own commands.

divide never edits ``composer.json`` behind composer's back: adding, removing
and updating packages run composer itself (``require``, ``remove``,
``update``, ``install``...), with its output line by line. Only a new
``composer.json`` (the wizard) is written by divide, as ``composer init``
would write it.

Composer is found (first hit wins): ``$DIVIDE_COMPOSER``, the path chosen in
the settings, a ``composer.phar`` in the project (run with ``php``), then
``composer`` in the PATH.
"""

from __future__ import annotations

from divide.i18n import _

import asyncio
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from divide.run import children

ENV = "DIVIDE_COMPOSER"
NAME = re.compile(r"^[a-z0-9]([_.-]?[a-z0-9]+)*/[a-z0-9](([_.]|-{1,2})?[a-z0-9]+)*$")  # composer's own rule
LICENSES = ("MIT", "GPL-3.0-or-later", "LGPL-3.0-or-later", "Apache-2.0", "BSD-3-Clause", "proprietary")


class ComposerError(RuntimeError):
    """Composer could not run (not found, or it failed before saying anything useful)."""


def find(root: Path, configured: str | None = None) -> list[str] | None:
    """The command that runs composer, or None."""
    for candidate in (os.environ.get(ENV), configured):
        if candidate:
            path = Path(candidate).expanduser()
            if path.is_file():
                return _command(path)
    phar = root / "composer.phar"
    if phar.is_file():
        return _command(phar)
    found = shutil.which("composer")
    return [found] if found else None


def _command(path: Path) -> list[str]:
    if path.suffix == ".phar":
        php = shutil.which("php")
        return [php, str(path)] if php else [str(path)]
    return [str(path)]


# ------------------------------------------------------------------ the project's packages
@dataclass
class Package:
    name: str
    constraint: str | None = None  # as composer.json requires it (None: only a dependency)
    dev: bool = False  # require-dev
    version: str | None = None  # installed (composer.lock)
    description: str = ""
    type: str = ""
    license: list[str] = field(default_factory=list)
    homepage: str = ""
    source: str = ""
    requires: dict[str, str] = field(default_factory=dict)
    platform: bool = False  # php, ext-mbstring...: not a package composer installs
    latest: str | None = None  # from "outdated", when asked

    @property
    def direct(self) -> bool:
        return self.constraint is not None

    @property
    def kind(self) -> str:
        if self.platform:
            return _("platform")
        if not self.direct:
            return _("dependency")
        return _("dev") if self.dev else _("require")


@dataclass
class Project:
    root: Path
    json: dict | None  # composer.json (None: there is none)
    lock: dict | None
    problem: str | None = None  # composer.json cannot be read
    packages: list[Package] = field(default_factory=list)

    @property
    def name(self) -> str:
        return str((self.json or {}).get("name") or self.root.name)

    @property
    def installed(self) -> bool:
        return (self.root / "vendor" / "autoload.php").is_file()


def is_platform(name: str) -> bool:
    return name == "php" or name.startswith(("ext-", "lib-")) or name in ("composer", "composer-plugin-api", "composer-runtime-api")


def read(root: Path) -> Project:
    """composer.json and composer.lock: the packages it requires, and what is installed."""
    file = root / "composer.json"
    if not file.is_file():
        return Project(root, None, None)
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return Project(root, None, None, problem=_('composer.json cannot be read: {exc}').format(exc=exc))
    if not isinstance(data, dict):
        return Project(root, None, None, problem=_('composer.json is not a JSON object'))
    lock = None
    try:
        lock = json.loads((root / "composer.lock").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        pass
    locked: dict[str, dict] = {}
    for section in ("packages", "packages-dev"):
        for item in (lock or {}).get(section) or []:
            if isinstance(item, dict) and item.get("name"):
                locked[item["name"]] = item
    packages: dict[str, Package] = {}
    for section, dev in (("require", False), ("require-dev", True)):
        for name, constraint in (data.get(section) or {}).items():
            packages[name] = Package(name, str(constraint), dev, platform=is_platform(name))
    for name, item in locked.items():
        package = packages.setdefault(name, Package(name))
        package.version = str(item.get("version") or "") or None
        package.description = str(item.get("description") or "")
        package.type = str(item.get("type") or "")
        package.license = [str(x) for x in item.get("license") or []]
        package.homepage = str(item.get("homepage") or "")
        package.source = str((item.get("source") or {}).get("url") or "")
        package.requires = {str(k): str(v) for k, v in (item.get("require") or {}).items()}
    project = Project(root, data, lock)
    project.packages = sorted(packages.values(), key=lambda p: (
        3 if p.platform else 2 if not p.direct else 1 if p.dev else 0, p.name))
    return project


# ------------------------------------------------------------------ running composer
@dataclass
class Result:
    code: int
    output: str

    @property
    def ok(self) -> bool:
        return self.code == 0


async def run(command: list[str], args: list[str], cwd: Path, on_line: Callable[[str], None] | None = None,
              timeout: float | None = None) -> Result:
    """``composer args`` in ``cwd``, its output (both streams) line by line to ``on_line``.
    Cancelling the task stops composer."""
    env = {**os.environ, "COMPOSER_NO_INTERACTION": "1"}
    try:
        proc = children.track(await asyncio.create_subprocess_exec(
            *command, *args, "--no-ansi", "--no-interaction", cwd=str(cwd), env=env,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            **children.options(),
        ))
    except OSError as exc:
        raise ComposerError(_('composer could not start: {exc}').format(exc=exc)) from None
    lines: list[str] = []

    async def pump() -> None:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            lines.append(line)
            if on_line is not None:
                on_line(line)

    try:
        await asyncio.wait_for(asyncio.gather(pump(), proc.wait()), timeout)
    except (asyncio.CancelledError, TimeoutError):
        children.kill(proc)
        await asyncio.shield(proc.wait())
        raise
    return Result(proc.returncode or 0, "\n".join(lines))


async def json_of(command: list[str], args: list[str], cwd: Path, timeout: float = 60.0) -> object:
    """A composer command with ``--format=json``, decoded (None when it failed)."""
    result = await run(command, [*args, "--format=json"], cwd, timeout=timeout)
    text = result.output
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if not result.ok or start < 0:
        return None
    try:
        return json.loads(text[start:])
    except ValueError:
        return None


@dataclass(frozen=True)
class Found:
    name: str
    description: str = ""
    url: str = ""


async def search(command: list[str], query: str, cwd: Path) -> list[Found]:
    """Packagist's packages for ``query`` (``composer search``)."""
    value = await json_of(command, ["search", query], cwd, timeout=30.0)
    out: dict[str, Found] = {}  # composer may list a package twice (one per repository)
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict) and item.get("name") and str(item["name"]) not in out:
            out[str(item["name"])] = Found(str(item["name"]), str(item.get("description") or ""), str(item.get("url") or ""))
    return list(out.values())


async def versions(command: list[str], name: str, cwd: Path) -> list[str]:
    """The versions a package has (``composer show --all``), the newest first."""
    value = await json_of(command, ["show", "--all", name], cwd, timeout=30.0)
    if isinstance(value, dict):
        found = value.get("versions")
        if isinstance(found, list):
            return [str(v) for v in found]
    return []


def suggest_constraint(available: list[str]) -> str | None:
    """``^1.4`` for the newest stable ``1.4.2`` (or None when there is no stable one)."""
    for version in available:
        m = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.\d+)*", version)
        if m:
            major, minor = int(m.group(1)), int(m.group(2))
            return f"^{major}.{minor}" if major or minor else f"^0.{minor}"
    return None


async def outdated(command: list[str], cwd: Path) -> dict[str, str]:
    """name -> latest version, for the direct packages with a newer one."""
    value = await json_of(command, ["outdated", "--direct"], cwd)
    out: dict[str, str] = {}
    for item in (value or {}).get("installed", []) if isinstance(value, dict) else []:
        if isinstance(item, dict) and item.get("name") and item.get("latest"):
            out[str(item["name"])] = str(item["latest"])
    return out


# ------------------------------------------------------------------ a new composer.json
@dataclass
class NewProject:
    name: str
    description: str = ""
    type: str = "project"
    license: str = "MIT"
    php: str = ">=8.0"
    require_div: bool = True
    div_constraint: str = "^6.1"
    namespace: str = ""  # PSR-4, "App\\"
    source: str = "src/"
    minimum_stability: str = ""

    def problems(self) -> list[str]:
        out = []
        if not NAME.match(self.name):
            out.append(_('the name is vendor/project, in lowercase: divengine/shop'))
        parts = self.namespace.strip("\\").split("\\")
        if self.namespace and not all(re.fullmatch(r"[A-Za-z_]\w*", part) for part in parts):
            out.append(_('the namespace is like App\\ or Acme\\Shop\\'))
        return out

    def json(self) -> dict:
        data: dict = {"name": self.name}
        if self.description:
            data["description"] = self.description
        data["type"] = self.type
        if self.license:
            data["license"] = self.license
        require: dict[str, str] = {}
        if self.php:
            require["php"] = self.php
        if self.require_div:
            require["divengine/div"] = self.div_constraint or "*"
        data["require"] = require
        if self.namespace:
            namespace = self.namespace.rstrip("\\") + "\\"
            data["autoload"] = {"psr-4": {namespace: self.source.rstrip("/") + "/"}}
        if self.minimum_stability:
            data["minimum-stability"] = self.minimum_stability
        return data

    def text(self) -> str:
        return json.dumps(self.json(), indent=4, ensure_ascii=False) + "\n"


def suggest_name(root: Path) -> str:
    """vendor/project from the folder (and its parent as the vendor)."""
    def slug(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "project"
    return f"{slug(root.parent.name)}/{slug(root.name)}"
