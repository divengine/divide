"""How divide sets up the Div engine for a project, at design time.

The PHP application configures Div in its own code at runtime; divide cannot
read that, so a project tells divide in ``.div/setup.json``, and the user can
set what applies to all their projects in ``~/.div/setup.json`` (``$DIV_HOME``
moves it). Both are Div JSON (comments allowed)::

    {
      "engine": "vendor/autoload.php",
      "paths": {"packages": "templates", "repository": "templates", "include": ["shared"]},
      "files": {"template_ext": "tpl", "data_ext": "json"},
      "parser": {"max_cycles": 100, "max_filename": 250, "error_reporting": "E_ALL & ~E_NOTICE"}
    }

- Everything is optional: what is missing is Div's own default.
- The project's file is found walking up from the folder divide opened (the
  user's ``~/.div`` never counts as a project's). Relative paths are relative
  to the folder that holds that ``.div``: the project's root, or the home folder.
- The project wins over the user; ``null`` in the project drops the user's
  value (Div's default again). Lists are joined, the project's first.
- An invalid entry is left out and reported with its place in the file.

What it becomes for Div (applied by ``bridge.php`` to every request, see
:func:`DivSetup.bridge`): constants defined before Div loads (``PACKAGES``,
``DIV_REPO``, ``DIV_DEFAULT_TPL_FILE_EXT``, ``DIV_DEFAULT_DATA_FILE_EXT``,
``DIV_MAX_PARSE_CYCLES``, ``DIV_MAX_FILENAME_SIZE``), then Div's static API
(``addIncludePath()``, ``setErrorReporting()``) before any engine is built.
"""

from __future__ import annotations

from divide.i18n import _

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from divide.lang import divjson

DIR = ".div"
FILE = "setup.json"
ENV_HOME = "DIV_HOME"

# what Div defines when nothing is set (div.php, "defined(...) or define(...)")
DEFAULT_TEMPLATE_EXT = "tpl"
DEFAULT_DATA_EXT = "json"

# PHP's error levels, for "error_reporting": "E_ALL & ~E_NOTICE"
E_LEVELS = {
    "E_ERROR": 1, "E_WARNING": 2, "E_PARSE": 4, "E_NOTICE": 8, "E_CORE_ERROR": 16,
    "E_CORE_WARNING": 32, "E_COMPILE_ERROR": 64, "E_COMPILE_WARNING": 128, "E_USER_ERROR": 256,
    "E_USER_WARNING": 512, "E_USER_NOTICE": 1024, "E_STRICT": 2048, "E_RECOVERABLE_ERROR": 4096,
    "E_DEPRECATED": 8192, "E_USER_DEPRECATED": 16384, "E_ALL": 32767,
}

# sections planned but not applied yet: reported once, never an error
LATER = {"dialect", "data", "php", "request"}


@dataclass(frozen=True)
class Problem:
    """Something in a setup file divide left out."""

    file: Path
    offset: int  # in the file's text
    text: str


@dataclass(frozen=True)
class DivSetup:
    """The setup in effect for a project: the user's and the project's files merged."""

    files: tuple[Path, ...] = ()  # the setup files read, the project's first
    engine: Path | None = None
    constants: dict[str, str | int] = field(default_factory=dict)  # defined before Div loads
    include_paths: tuple[str, ...] = ()  # div::addIncludePath(), in this order
    error_reporting: int | None = None  # div::setErrorReporting()
    problems: tuple[Problem, ...] = ()

    @property
    def template_ext(self) -> str:
        """With its dot: ``.tpl``."""
        return "." + str(self.constants.get("DIV_DEFAULT_TPL_FILE_EXT", DEFAULT_TEMPLATE_EXT))

    @property
    def data_ext(self) -> str:
        return "." + str(self.constants.get("DIV_DEFAULT_DATA_FILE_EXT", DEFAULT_DATA_EXT))

    def bridge(self) -> dict[str, Any]:
        """The ``setup`` of a bridge request; empty when nothing is set (Div as it comes)."""
        out: dict[str, Any] = {}
        if self.constants:
            out["constants"] = dict(self.constants)
        if self.include_paths:
            out["include_paths"] = list(self.include_paths)
        if self.error_reporting is not None:
            out["error_reporting"] = self.error_reporting
        return out


NONE = DivSetup()


def user_dir() -> Path:
    home = os.environ.get(ENV_HOME)
    return Path(home).expanduser() if home else Path.home() / DIR


def project_dir(start: Path) -> Path | None:
    """The project's ``.div`` folder, walking up from ``start`` (never the user's)."""
    user = _real(user_dir())
    start = start.resolve()
    for folder in [start, *start.parents]:
        candidate = folder / DIR
        if (candidate / FILE).is_file() and _real(candidate) != user:
            return candidate
    return None


def _real(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


# ------------------------------------------------------------------ reading
class _Layer:
    """One setup file, checked: its values (paths made absolute) and its problems."""

    def __init__(self, file: Path) -> None:
        self.file = file
        self.base = file.parent.parent  # the folder holding .div
        self.values: dict[str, Any] = {}  # flat: "paths.packages" -> value (None: Div's default)
        self.problems: list[Problem] = []
        try:
            self.text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            self.text = ""
            self.problem(0, _('cannot read it: {exc}').format(exc=exc))
            return
        if not self.text.strip():
            return
        try:
            data = divjson.loads(self.text)
        except divjson.DivJsonError as exc:
            self.problem(exc.offset, str(exc))
            return
        if not isinstance(data, dict):
            self.problem(0, _('the setup must be a JSON object'))
            return
        self.read(data)

    def problem(self, offset: int, text: str) -> None:
        self.problems.append(Problem(self.file, offset, text))

    def where(self, *names: str) -> int:
        """Where a key is written (its last name, after the ones before it): for messages."""
        offset = 0
        for name in names:
            found = re.search(r"""(["']?)%s\1\s*:""" % re.escape(name), self.text[offset:])
            if found is None:
                break
            offset += found.start()
        return offset

    def read(self, data: dict) -> None:
        sections = {"engine": None, "paths": ("packages", "repository", "include"),
                    "files": ("template_ext", "data_ext"),
                    "parser": ("max_cycles", "max_filename", "error_reporting")}
        for key, value in data.items():
            if key in LATER:
                self.problem(self.where(key), _('"{key}" is not applied yet: this divide leaves it out').format(key=key))
                continue
            if key not in sections:
                self.problem(self.where(key), _('unknown setting "{key}"').format(key=key))
                continue
            names = sections[key]
            if names is None:
                self.set(key, value, self.engine)
                continue
            if value is None:  # the whole section back to Div's defaults
                for name in names:
                    self.values[f"{key}.{name}"] = None
                continue
            if not isinstance(value, dict):
                self.problem(self.where(key), _('"{key}" must be an object').format(key=key))
                continue
            for name, item in value.items():
                if name not in names:
                    self.problem(self.where(key, name), _('unknown setting "{key}.{name}"').format(key=key, name=name))
                    continue
                check = getattr(self, f"{key}_{name}")
                self.set(f"{key}.{name}", item, check)

    def set(self, key: str, value: Any, check) -> None:
        if value is None:
            self.values[key] = None
            return
        try:
            self.values[key] = check(value)
        except ValueError as exc:
            self.problem(self.where(*key.split(".")), f"{key}: {exc}")

    # one check per setting: the value as Div gets it, or ValueError
    def path(self, value: Any, *, folder: bool = True) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(_('a path is expected'))
        path = (self.base / Path(value).expanduser()).resolve()
        if folder and not path.is_dir():
            raise ValueError(_('{path} is not a folder').format(path=path))
        if not folder and not path.is_file():
            raise ValueError(_('{path} is not a file').format(path=path))
        return str(path) + ("/" if folder else "")

    def engine(self, value: Any) -> str:
        path = self.path(value, folder=False)
        if not path.endswith(".php"):
            raise ValueError(_('the engine is a .php file (autoload.php or div.php)'))
        return path

    def paths_packages(self, value: Any) -> str:
        return self.path(value)

    paths_repository = paths_packages

    def paths_include(self, value: Any) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError(_('a list of folders is expected'))
        out = []
        for item in value:
            try:
                out.append(self.path(item))
            except ValueError as exc:  # the others still count
                self.problem(self.where("paths", "include"), f"paths.include: {exc}")
        return out

    def extension(self, value: Any) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"\.?[A-Za-z0-9_-]+", value.strip()):
            raise ValueError(_('an extension is expected, like "tpl"'))
        return value.strip().lstrip(".")

    files_template_ext = files_data_ext = extension

    def count(self, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(_('a whole number of at least 1 is expected'))
        return value

    parser_max_cycles = parser_max_filename = count

    def parser_error_reporting(self, value: Any) -> int:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        if isinstance(value, str):
            return error_level(value)
        raise ValueError(_('a number or PHP error levels are expected (E_ALL, E_NOTICE...)'))


def error_level(text: str) -> int:
    """``E_ALL & ~E_NOTICE | E_STRICT`` as PHP reads it (``&`` before ``|``)."""
    total = 0
    for term in text.split("|"):
        value = -1
        for factor in term.split("&"):
            name = factor.strip()
            negate = name.startswith("~")
            name = name.lstrip("~").strip()
            if name.isdigit():
                level = int(name)
            elif name in E_LEVELS:
                level = E_LEVELS[name]
            else:
                raise ValueError(_('unknown PHP error level "{name}"').format(name=name or factor))
            value &= ~level if negate else level
        total |= value
    return total & E_LEVELS["E_ALL"]


# ------------------------------------------------------------------ merging
_CONSTANTS = {
    "paths.packages": "PACKAGES", "paths.repository": "DIV_REPO",
    "files.template_ext": "DIV_DEFAULT_TPL_FILE_EXT", "files.data_ext": "DIV_DEFAULT_DATA_FILE_EXT",
    "parser.max_cycles": "DIV_MAX_PARSE_CYCLES", "parser.max_filename": "DIV_MAX_FILENAME_SIZE",
}

_cache: dict[tuple, DivSetup] = {}


def _stamp(file: Path | None) -> tuple:
    if file is None:
        return (None,)
    try:
        st = file.stat()
    except OSError:
        return (str(file), None)
    return (str(file), st.st_mtime_ns, st.st_size)


def load(root: Path) -> DivSetup:
    """The setup for the project at ``root``: read again only when a file changed."""
    project = project_dir(root)
    files = [d / FILE for d in (project, user_dir()) if d is not None and (d / FILE).is_file()]
    if project is not None and len(files) == 2 and _real(files[0]) == _real(files[1]):
        files = files[:1]
    key = tuple(_stamp(f) for f in files)
    cached = _cache.get(key)
    if cached is None:
        cached = _cache[key] = merge([_Layer(f) for f in files])
    return cached


def merge(layers: list[_Layer]) -> DivSetup:
    """``layers`` from the strongest (the project's) to the weakest (the user's)."""
    if not layers:
        return NONE
    values: dict[str, Any] = {}
    for layer in layers:
        for key, value in layer.values.items():
            values.setdefault(key, value)  # a stronger null stays: Div's default
    includes: list[str] = []
    for layer in layers:
        if "paths.include" in layer.values:
            value = layer.values["paths.include"]
            if value is None:
                break  # Div's default: none of the weaker files' either
            includes += [p for p in value if p not in includes]
    constants = {const: values[key] for key, const in _CONSTANTS.items() if values.get(key) is not None}
    engine = values.get("engine")
    return DivSetup(
        files=tuple(layer.file for layer in layers),
        engine=Path(engine) if engine else None,
        constants=constants,
        include_paths=tuple(includes),
        error_reporting=values.get("parser.error_reporting"),
        problems=tuple(p for layer in layers for p in layer.problems),
    )
