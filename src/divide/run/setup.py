"""How divide sets up the Div engine for a project, at design time.

The PHP application configures Div in its own code at runtime; divide cannot
read that, so a project tells divide in ``.div/setup.json``, and the user can
set what applies to all their projects in ``~/.div/setup.json`` (``$DIV_HOME``
moves it). Both are Div JSON (comments allowed)::

    {
      "engine": "vendor/autoload.php",
      "paths": {"packages": "templates", "repository": "templates", "include": ["shared"]},
      "files": {"template_ext": "tpl", "data_ext": "json"},
      "parser": {"max_cycles": 100, "max_filename": 250, "error_reporting": "E_ALL & ~E_NOTICE"},
      "dialect": "erb.dialect",
      "data": {"globals": {"site": "Shop"}, "defaults": [{"search": null, "replace": "-"}],
               "defaults_by_var": [{"var": "price", "search": 0, "replace": "free"}],
               "system_vars": ["server", "session"]},
      "php": {"allowed_functions": ["array_sum"], "modifiers": {"rev:": "strrev"}},
      "request": {"get": {"page": 1}, "post": {}, "server": {"HTTP_HOST": "shop.test"},
                  "session": {"user": "rafa"}, "cookie": {}}
    }

- Everything is optional: what is missing is Div's own default.
- The project's file is found walking up from the folder divide opened (the
  user's ``~/.div`` never counts as a project's). Relative paths are relative
  to the folder that holds that ``.div``: the project's root, or the home folder.
- The project wins over the user; ``null`` drops the user's value (Div's default
  again). Lists are joined (the project's first); objects are merged by key.
- An invalid entry is left out and reported with its place in the file.
- ``php`` lets templates call PHP functions: a project's ``php`` is applied only
  once the user trusts it (``~/.div/trust.json`` keeps a hash of it, so a change
  asks again); the user's own is always applied.

What it becomes for Div (``bridge.php`` applies it to every request, see
:meth:`DivSetup.bridge`): the request's superglobals and the constants, before
Div loads (``PACKAGES``, ``DIV_REPO``, ``DIV_DEFAULT_TPL_FILE_EXT``,
``DIV_DEFAULT_DATA_FILE_EXT``, ``DIV_MAX_PARSE_CYCLES``, ``DIV_MAX_FILENAME_SIZE``,
the dialect's ``DIV_TAG_*``), then Div's static API before any engine is built:
``setErrorReporting()``, ``addIncludePath()``, ``enableSystemVar()``,
``setAllowedFunction()``, ``addCustomModifier()``, ``setGlobal()``,
``setDefault()``, ``setDefaultByVar()``.
"""

from __future__ import annotations

from divide.i18n import _

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from divide.lang import divjson
from divide.lang.div.dialect import DEFAULT_TAGS, Dialect, lenient_json

DIR = ".div"
FILE = "setup.json"
TRUST = "trust.json"
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

# Div's system variables (div::getSystemData()); Div turns the first five on
# itself in every engine, so only the others are worth enabling
SYSTEM_VARS = ("ascii", "server", "session", "script_name", "now", "post", "get", "version", "level")
ALWAYS_ON = frozenset({"now", "post", "get", "version", "level"})

SUPERGLOBALS = ("get", "post", "server", "session", "cookie")

# every setting: section -> names (None: the section is a value itself)
SECTIONS: dict[str, tuple[str, ...] | None] = {
    "engine": None,
    "paths": ("packages", "repository", "include"),
    "files": ("template_ext", "data_ext"),
    "parser": ("max_cycles", "max_filename", "error_reporting"),
    "dialect": None,
    "data": ("globals", "defaults", "defaults_by_var", "system_vars"),
    "php": ("allowed_functions", "modifiers"),
    "request": SUPERGLOBALS,
}

# how a setting merges with a weaker file's: the stronger one's value (scalar),
# both lists (list), both objects by key (object), both lists of defaults by
# what they search (defaults)
_KIND = {
    "paths.include": "list", "data.system_vars": "list", "php.allowed_functions": "list",
    "data.globals": "object", "php.modifiers": "object",
    "data.defaults": "defaults", "data.defaults_by_var": "defaults",
    **{f"request.{name}": "object" for name in SUPERGLOBALS},
}

_CONSTANTS = {
    "paths.packages": "PACKAGES", "paths.repository": "DIV_REPO",
    "files.template_ext": "DIV_DEFAULT_TPL_FILE_EXT", "files.data_ext": "DIV_DEFAULT_DATA_FILE_EXT",
    "parser.max_cycles": "DIV_MAX_PARSE_CYCLES", "parser.max_filename": "DIV_MAX_FILENAME_SIZE",
}


@dataclass(frozen=True)
class Problem:
    """Something in a setup file divide left out."""

    file: Path
    offset: int  # in the file's text
    text: str


@dataclass(frozen=True)
class Untrusted:
    """A project's ``php`` settings waiting for the user's trust."""

    file: Path
    digest: str
    functions: tuple[str, ...]
    modifiers: dict[str, str]


@dataclass(frozen=True)
class DivSetup:
    """The setup in effect for a project: the user's and the project's files merged."""

    files: tuple[Path, ...] = ()  # the setup files read, the project's first
    engine: Path | None = None
    constants: dict[str, str | int] = field(default_factory=dict)  # defined before Div loads (not the dialect)
    include_paths: tuple[str, ...] = ()  # div::addIncludePath(), in this order
    error_reporting: int | None = None  # div::setErrorReporting()
    dialect_tags: dict[str, str] = field(default_factory=dict)  # DIV_TAG_* overrides of Div's defaults
    dialect_source: Path | None = None  # the .dialect file they come from (None: written in the setup)
    globals: dict[str, Any] = field(default_factory=dict)
    defaults: tuple[tuple[Any, Any], ...] = ()  # (search, replace)
    defaults_by_var: tuple[tuple[str, Any, Any], ...] = ()  # (var, search, replace)
    system_vars: tuple[str, ...] = ()
    allowed_functions: tuple[str, ...] = ()
    modifiers: dict[str, str] = field(default_factory=dict)  # prefix -> PHP function
    request: dict[str, dict[str, Any]] = field(default_factory=dict)  # superglobal -> values
    problems: tuple[Problem, ...] = ()
    untrusted: Untrusted | None = None

    @property
    def template_ext(self) -> str:
        """With its dot: ``.tpl``."""
        return "." + str(self.constants.get("DIV_DEFAULT_TPL_FILE_EXT", DEFAULT_TEMPLATE_EXT))

    @property
    def data_ext(self) -> str:
        return "." + str(self.constants.get("DIV_DEFAULT_DATA_FILE_EXT", DEFAULT_DATA_EXT))

    @property
    def dialect(self) -> Dialect | None:
        """The project's dialect (Div's defaults with its tags), None when it has none."""
        if not self.dialect_tags:
            return None
        name = self.dialect_source.stem if self.dialect_source else _('project')
        return Dialect.from_overrides(self.dialect_tags, name=name, source=self.dialect_source)

    @property
    def empty(self) -> bool:
        return not self.bridge() and self.engine is None

    def bridge(self, *, dialect: bool = True) -> dict[str, Any]:
        """The ``setup`` of a bridge request; empty when nothing is set (Div as it comes).
        ``dialect=False``: without the project's dialect (Div's default one)."""
        out: dict[str, Any] = {}
        constants = dict(self.constants)
        if dialect:
            constants.update(self.dialect_tags)
        if constants:
            out["constants"] = constants
        if self.include_paths:
            out["include_paths"] = list(self.include_paths)
        if self.error_reporting is not None:
            out["error_reporting"] = self.error_reporting
        if self.system_vars:
            out["system_vars"] = list(self.system_vars)
        if self.allowed_functions:
            out["allowed_functions"] = list(self.allowed_functions)
        if self.modifiers:
            out["modifiers"] = dict(self.modifiers)
        if self.globals:
            out["globals"] = dict(self.globals)
        if self.defaults:
            out["defaults"] = [[s, r] for s, r in self.defaults]
        if self.defaults_by_var:
            out["defaults_by_var"] = [[v, s, r] for v, s, r in self.defaults_by_var]
        if self.request:
            out["request"] = {k: dict(v) for k, v in self.request.items()}
        return out

    def variables(self) -> dict[str, Any]:
        """What templates get besides their data: the globals and the system variables
        Div adds (a template's own data wins over a global, as in Div)."""
        out: dict[str, Any] = dict(self.globals)
        for name in self.system_vars:
            out[f"div.{name}"] = self.request.get(name, {}) if name in ("server", "session") else ""
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


def project_file(root: Path) -> Path:
    """Where the project's setup is (or would be: ``<root>/.div/setup.json``)."""
    found = project_dir(root)
    return (found or root.resolve() / DIR) / FILE


def user_file() -> Path:
    return user_dir() / FILE


def is_setup_file(path: Path | None) -> bool:
    return path is not None and path.name == FILE and path.parent.name in (DIR, user_dir().name)


def _real(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


# ------------------------------------------------------------------ reading
class Layer:
    """One setup file, checked: its values (paths made absolute) and its problems."""

    def __init__(self, file: Path, text: str | None = None) -> None:
        self.file = file
        self.base = file.parent.parent  # the folder holding .div
        self.values: dict[str, Any] = {}  # flat: "paths.packages" -> value (None: Div's default)
        self.problems: list[Problem] = []
        self.data: dict = {}
        if text is None:
            try:
                text = file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                self.text = ""
                self.problem(0, _('cannot read it: {exc}').format(exc=exc))
                return
        self.text = text
        if not text.strip():
            return
        try:
            data = divjson.loads(text)
        except divjson.DivJsonError as exc:
            self.problem(exc.offset, str(exc))
            return
        if not isinstance(data, dict):
            self.problem(0, _('the setup must be a JSON object'))
            return
        self.data = data
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
        for key, value in data.items():
            if key not in SECTIONS:
                self.problem(self.where(key), _('unknown setting "{key}"').format(key=key))
                continue
            names = SECTIONS[key]
            if names is None:
                self.set(key, value, getattr(self, key))
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
                self.set(f"{key}.{name}", item, getattr(self, f"{key}_{name}"))

    def set(self, key: str, value: Any, check) -> None:
        if value is None:
            self.values[key] = None
            return
        try:
            self.values[key] = check(value)
        except ValueError as exc:
            self.problem(self.where(*key.split(".")), f"{key}: {exc}")

    def note(self, key: str, text: str) -> None:
        """A part of a setting left out while the rest of it counts."""
        self.problem(self.where(*key.split(".")), f"{key}: {text}")

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
        out = []
        for item in self.strings(value, _('a list of folders is expected')):
            try:
                out.append(self.path(item))
            except ValueError as exc:  # the others still count
                self.note("paths.include", str(exc))
        return out

    def strings(self, value: Any, expected: str) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            raise ValueError(expected)
        return [v.strip() for v in value]

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

    def dialect(self, value: Any) -> dict:
        """A .dialect file (decoded as Div's jsonDecode() does) or the tags themselves."""
        source = None
        if isinstance(value, str):
            source = Path(self.path(value, folder=False))
            try:
                value = lenient_json(source.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                raise ValueError(_('Div cannot decode {path}: {exc}').format(path=source, exc=exc)) from None
        if not isinstance(value, dict):
            raise ValueError(_('a .dialect file or an object of DIV_TAG_ tags is expected'))
        tags: dict[str, str] = {}
        for name, tag in value.items():
            if name not in DEFAULT_TAGS:
                if str(name).startswith("DIV_TAG_"):
                    self.note("dialect", _('Div has no tag {name}').format(name=name))
                continue  # a dialect file may say more (a name, comments)
            if not isinstance(tag, (str, int, float)) or isinstance(tag, bool):
                self.note("dialect", _('{name} must be text').format(name=name))
                continue
            tags[name] = str(tag)
        return {"tags": tags, "source": source}

    def data_globals(self, value: Any) -> dict:
        if not isinstance(value, dict):
            raise ValueError(_('an object of variables is expected'))
        self.plain(value, "data.globals")
        return value

    def plain(self, value: Any, key: str) -> None:
        """Values Div can take: no $references (they would be decoded before any variable exists)."""
        if isinstance(value, divjson.Ref):
            raise ValueError(_('{key}: a $reference is not a value here').format(key=key))
        if isinstance(value, dict):
            for item in value.values():
                self.plain(item, key)
        elif isinstance(value, list):
            for item in value:
                self.plain(item, key)

    def data_defaults(self, value: Any) -> list[tuple]:
        if not isinstance(value, list):
            raise ValueError(_('a list of {{"search": ..., "replace": ...}} is expected'))
        out = []
        for item in value:
            if not isinstance(item, dict) or set(item) != {"search", "replace"}:
                self.note("data.defaults", _('each default is {{"search": ..., "replace": ...}}'))
                continue
            self.plain(item, "data.defaults")
            out.append((item["search"], item["replace"]))
        return out

    def data_defaults_by_var(self, value: Any) -> list[tuple]:
        if not isinstance(value, list):
            raise ValueError(_('a list of {{"var": ..., "search": ..., "replace": ...}} is expected'))
        out = []
        for item in value:
            if (not isinstance(item, dict) or set(item) != {"var", "search", "replace"}
                    or not isinstance(item["var"], str) or not item["var"].strip()):
                self.note("data.defaults_by_var", _('each default is {{"var": "name", "search": ..., "replace": ...}}'))
                continue
            self.plain(item, "data.defaults_by_var")
            out.append((item["var"].strip(), item["search"], item["replace"]))
        return out

    def data_system_vars(self, value: Any) -> list[str]:
        out = []
        for name in self.strings(value, _('a list of names is expected')):
            name = name.removeprefix("div.")
            if name not in SYSTEM_VARS:
                self.note("data.system_vars", _('Div has no system variable div.{name}').format(name=name))
            elif name not in out:
                out.append(name)
        return out

    def php_allowed_functions(self, value: Any) -> list[str]:
        out = []
        for name in self.strings(value, _('a list of PHP function names is expected')):
            if not re.fullmatch(r"[A-Za-z_\\][\w\\]*", name):
                self.note("php.allowed_functions", _('"{name}" is not a PHP function name').format(name=name))
            elif name not in out:
                out.append(name)
        return out

    def php_modifiers(self, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ValueError(_('an object of prefix: PHP function is expected'))
        out = {}
        for prefix, function in value.items():
            if not prefix.strip():
                self.note("php.modifiers", _('a modifier needs a prefix'))
            elif not isinstance(function, str) or not re.fullmatch(r"[A-Za-z_\\][\w\\]*(::\w+)?", function):
                self.note("php.modifiers", _('"{prefix}" needs the name of a PHP function').format(prefix=prefix))
            else:
                out[prefix] = function
        return out

    def superglobal(self, value: Any) -> dict:
        if not isinstance(value, dict):
            raise ValueError(_('an object of names and values is expected'))
        self.plain(value, "request")
        return value

    request_get = request_post = request_server = request_session = request_cookie = superglobal


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


# ------------------------------------------------------------------ trust
def php_digest(layer: Layer) -> str | None:
    """A hash of a file's ``php`` settings as written (None: it has none)."""
    php = layer.data.get("php")
    if not php:
        return None
    return hashlib.sha256(json.dumps(php, sort_keys=True, default=str).encode()).hexdigest()


def trust_file() -> Path:
    return user_dir() / TRUST


def _trusted() -> dict[str, str]:
    try:
        data = json.loads(trust_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def trust(untrusted: Untrusted) -> None:
    """The user trusts these ``php`` settings of that project (until they change)."""
    data = _trusted()
    data[str(_real(untrusted.file))] = untrusted.digest
    trust_file().parent.mkdir(parents=True, exist_ok=True)
    trust_file().write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ merging
_cache: dict[tuple, DivSetup] = {}


def _stamp(file: Path | None) -> tuple:
    if file is None:
        return (None,)
    try:
        st = file.stat()
    except OSError:
        return (str(file), None)
    return (str(file), st.st_mtime_ns, st.st_size)


def _dialect_stamp(layer_files: list[Path]) -> tuple:
    """The dialect files the setups name change the setup too."""
    out = []
    for file in layer_files:
        try:
            data = divjson.loads(file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, divjson.DivJsonError):
            continue
        ref = data.get("dialect") if isinstance(data, dict) else None
        if isinstance(ref, str):
            out.append(_stamp((file.parent.parent / Path(ref).expanduser()).resolve()))
    return tuple(out)


def setup_files(root: Path) -> list[Path]:
    """The setup files for the project at ``root``: the project's, then the user's."""
    project = project_dir(root)
    files = [d / FILE for d in (project, user_dir()) if d is not None and (d / FILE).is_file()]
    if len(files) == 2 and _real(files[0]) == _real(files[1]):
        files = files[:1]
    return files


def load(root: Path) -> DivSetup:
    """The setup for the project at ``root``: read again only when a file changed."""
    files = setup_files(root)
    if not files:
        return NONE
    key = (*(_stamp(f) for f in files), _stamp(trust_file()), _dialect_stamp(files))
    cached = _cache.get(key)
    if cached is None:
        user = _real(user_dir())
        layers = [Layer(f) for f in files]
        projects = [layer for layer in layers if _real(layer.file.parent) != user]
        cached = _cache[key] = merge(layers, untrusted=_untrusted(projects[0]) if projects else None)
    return cached


def _untrusted(layer: Layer) -> Untrusted | None:
    digest = php_digest(layer)
    if digest is None or _trusted().get(str(_real(layer.file))) == digest:
        return None
    return Untrusted(layer.file, digest, tuple(layer.values.get("php.allowed_functions") or ()),
                     dict(layer.values.get("php.modifiers") or {}))


def merge(layers: list[Layer], untrusted: Untrusted | None = None) -> DivSetup:
    """``layers`` from the strongest (the project's) to the weakest (the user's);
    ``untrusted``: the project's ``php`` is left out."""
    if not layers:
        return NONE
    problems = [p for layer in layers for p in layer.problems]
    if untrusted is not None:
        for layer in layers:
            if layer.file == untrusted.file:
                for name in ("php.allowed_functions", "php.modifiers"):
                    layer.values.pop(name, None)
                problems.append(Problem(layer.file, layer.where("php"), _(
                    'the project\'s "php" settings are not applied until you trust them (Options > Div setup)')))
    values: dict[str, Any] = {}
    for layer in layers:
        for key, value in layer.values.items():
            kind = _KIND.get(key, "scalar")
            if kind == "scalar":
                values.setdefault(key, value)
    lists: dict[str, Any] = {}
    for key, kind in _KIND.items():
        if kind == "list":
            joined: list = []
            for layer in layers:
                if key in layer.values:
                    if layer.values[key] is None:
                        break  # Div's default: none of the weaker files' either
                    joined += [v for v in layer.values[key] if v not in joined]
            lists[key] = joined
        elif kind == "object":
            obj: dict = {}
            for layer in layers:
                if key in layer.values:
                    if layer.values[key] is None:
                        break
                    for name, value in layer.values[key].items():
                        obj.setdefault(name, value)
            lists[key] = obj
        else:  # defaults: one per variable and value searched, the stronger one
            seen: dict = {}
            for layer in layers:
                if key in layer.values:
                    if layer.values[key] is None:
                        break
                    for item in layer.values[key]:
                        seen.setdefault(json.dumps(item[:-1], sort_keys=True, default=str), item)
            lists[key] = list(seen.values())
    constants = {const: values[key] for key, const in _CONSTANTS.items() if values.get(key) is not None}
    engine = values.get("engine")
    dialect = values.get("dialect") or {}
    request = {name: lists[f"request.{name}"] for name in SUPERGLOBALS if lists[f"request.{name}"]}
    return DivSetup(
        files=tuple(layer.file for layer in layers),
        engine=Path(engine) if engine else None,
        constants=constants,
        include_paths=tuple(lists["paths.include"]),
        error_reporting=values.get("parser.error_reporting"),
        dialect_tags=dict(dialect.get("tags") or {}),
        dialect_source=dialect.get("source"),
        globals=lists["data.globals"],
        defaults=tuple(lists["data.defaults"]),
        defaults_by_var=tuple(lists["data.defaults_by_var"]),
        system_vars=tuple(n for n in lists["data.system_vars"] if n not in ALWAYS_ON),
        allowed_functions=tuple(lists["php.allowed_functions"]),
        modifiers=lists["php.modifiers"],
        request=request,
        problems=tuple(problems),
        untrusted=untrusted,
    )


def check_text(file: Path, text: str) -> list[Problem]:
    """The problems of a setup file as it is being edited (for the editor)."""
    return Layer(file, text).problems
