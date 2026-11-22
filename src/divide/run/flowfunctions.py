"""Runner's Modules and Functions as divide develops them (UI-independent).

Runner calls a Step's ``condition`` and ``activity`` *Functions*: PHP files
that return a callable, which Runner calls with the Flow's shared context
(``function (array &$context)``). A *Module* is a folder of them, named by a
Step's ``module``; it is not a Block, and a Function is not a Step. Where Runner
looks is :class:`divide.run.flowmodel.Functions` (``--root``, ``_root_folder``,
``_modules``); this module adds nothing to that resolution, it uses it:

- :func:`load_settings`: the project's optional ``.div/runner.json``, a default
  function root and Module folders shared by the team (no file: Runner's own
  defaults). Precedence, the same as a run's: the Flow's ``--root`` (the Run
  Flow dialog), else the context's ``_root_folder``, else the file's ``root``,
  else the project; a Module's folder from the context's ``_modules``, else the
  file's ``modules``, else ``<root>/<module>``. :func:`run_options` gives Runner
  what the file adds, so a run finds what the Designer shows.
- :func:`catalog`: the Modules and Functions on disk, the Steps of the project's
  Flows that reference each one (open buffers included, unsaved edits too), the
  references that resolve to nothing, and the Functions each Function imports
  through ``$context['_importer']`` where that is written literally (dynamic
  imports are unknown, never errors).
- :func:`inspect_source`: what can be said of a Function's file without running
  it, from tree-sitter's PHP grammar: a top-level ``return`` of a closure that
  takes more arguments than the context, takes it by value, or types it as
  something else than an array. Any other callable (``return 'strlen';``, an
  invokable object...) is left alone: no anatomy is enforced.
- :func:`create_module`, :func:`create_function`: a folder, or a file from a
  minimal template (:func:`function_source`), only inside the project, never in
  its Composer vendor folder, never over an existing file; :meth:`Created.undo`
  takes back exactly what was made while it is unchanged.

No PHP is run to build the catalog.
"""

from __future__ import annotations

from divide.i18n import _

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from divide.run import flowmodel as fm
from divide.run.flow import is_flow, vendor_dir

SETTINGS = Path(".div") / "runner.json"
ROLES = ("activity", "condition")
_NEW_SEGMENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*$")  # a new Function's name (Runner's segment, without dots)
_MAX_FLOWS = 200
_MAX_FLOW_BYTES = 512 * 1024
_SKIP_DIRS = {"vendor", "node_modules", ".git", ".div", ".hg", ".svn"}


class CreateError(Exception):
    """Why a Module or a Function cannot be made there (nothing was written)."""


# ---------------------------------------------------------------- the project's settings
@dataclass(frozen=True)
class ProjectSettings:
    """``.div/runner.json``: ``{"root": "functions", "modules": {"shared": "../lib/shared"}}``, both optional,
    paths relative to the project."""

    path: Path
    exists: bool = False
    root: str = ""
    modules: dict[str, str] = field(default_factory=dict)
    problems: tuple[str, ...] = ()


def load_settings(project: Path) -> ProjectSettings:
    path = project / SETTINGS
    if not path.is_file():
        return ProjectSettings(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return ProjectSettings(path, True, problems=(_('{file} is not JSON: {why}').format(file=SETTINGS.as_posix(), why=exc),))
    if not isinstance(data, dict):
        return ProjectSettings(path, True, problems=(_('{file} must be a JSON object').format(file=SETTINGS.as_posix()),))
    problems = []
    root = data.get("root", "")
    if not isinstance(root, str):
        problems.append(_('"root" must be a path (a string)'))
        root = ""
    modules: dict[str, str] = {}
    given = data.get("modules", {})
    if not isinstance(given, dict):
        problems.append(_('"modules" must be an object: {"module": "folder"}'))
        given = {}
    for name, folder in given.items():
        if fm.module_problem(str(name), "x") is not None:
            problems.append(_('"modules": {name} is not a Module name (letters, digits, _ and -)').format(name=name))
        elif not isinstance(folder, str) or not folder.strip():
            problems.append(_('"modules": {name} needs a folder (a string)').format(name=name))
        else:
            modules[str(name)] = folder.strip()
    for key in data:
        if key not in ("root", "modules"):
            problems.append(_('{key}: not a setting of {file} (root, modules)').format(key=key, file=SETTINGS.as_posix()))
    return ProjectSettings(path, True, root.strip(), modules, tuple(problems))


def settings_text(root: str, modules: dict[str, str] | None = None) -> str:
    return json.dumps({"root": root, "modules": modules or {}}, indent=4) + "\n"


def run_options(settings: ProjectSettings, flow_root: str, context: dict) -> tuple[str, dict[str, str]]:
    """What a run must give Runner for it to see the project's settings: the ``--root`` (the Flow's own,
    else the file's when the context has no ``_root_folder``; empty: none) and the Modules to add to the
    context's ``_modules`` (the file's, where the context does not map them)."""
    root = flow_root.strip()
    given = context.get("_root_folder")
    if not root and not (isinstance(given, str) and given.strip()):
        root = settings.root
    mapped = context.get("_modules") if isinstance(context.get("_modules"), dict) else {}
    extra = {name: folder for name, folder in settings.modules.items() if name not in mapped}
    return root, extra


# ---------------------------------------------------------------- reading a Function's source
@dataclass(frozen=True)
class Import:
    """``$context['_importer']('name', 'module')`` in a Function: what it names, if written literally."""

    line: int
    name: str | None  # None: computed at run time (unknown)
    module: str | None = None
    dynamic: bool = False

    @property
    def qualified(self) -> str:
        if self.dynamic or self.name is None:
            return "?"
        return f"{self.module}:{self.name}" if self.module else self.name


@dataclass(frozen=True)
class SourceInfo:
    form: str  # "closure", "arrow", "other" (another callable expression), "none" (no top-level return), "unknown"
    signature: str = ""  # the closure's parameters and return type, as written
    line: int = 0  # the top-level return's line (1-based; 0: none)
    problems: tuple[tuple[str, str, int], ...] = ()  # (severity: error, warning, note; message, line)
    imports: tuple[Import, ...] = ()


_SOURCES: dict[Path, tuple[tuple[int, int], SourceInfo]] = {}
_ACCEPTED_TYPES = {"array", "mixed", "iterable", "?array", "?iterable"}


def _parser():
    from divide.lang.php import grammar
    found = grammar()
    if found is None:
        return None
    from tree_sitter import Parser
    return Parser(found[0])


def inspect_source(path: Path) -> SourceInfo:
    """The file's callable and imports, read (never run); cached while the file is unchanged."""
    try:
        stat = path.stat()
        key = (stat.st_mtime_ns, stat.st_size)
        cached = _SOURCES.get(path)
        if cached is not None and cached[0] == key:
            return cached[1]
        data = path.read_bytes()
    except OSError:
        return SourceInfo("unknown")
    info = inspect_text(data)
    _SOURCES[path] = (key, info)
    return info


def inspect_text(data: bytes | str) -> SourceInfo:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    parser = _parser()
    if parser is None:
        return SourceInfo("unknown")
    tree = parser.parse(raw)
    root = tree.root_node

    def text(node) -> str:
        return raw[node.start_byte:node.end_byte].decode("utf-8", "replace")

    imports = tuple(_imports(root, text))
    if root.has_error:
        return SourceInfo("unknown", imports=imports)  # PHP's lint says what is wrong
    returns = [c for c in root.children if c.type == "return_statement"]
    if not returns:
        return SourceInfo("none", problems=(("error", _('the file returns nothing: Runner needs it to return a callable'), 1),),
                          imports=imports)
    value = next((c for c in returns[0].children if c.is_named), None)
    if value is None:
        return SourceInfo("none", problems=(("error", _('the file returns nothing: Runner needs it to return a callable'),
                                             returns[0].start_point[0] + 1),), imports=imports)
    if value.type not in ("anonymous_function", "arrow_function"):
        return SourceInfo("other", line=returns[0].start_point[0] + 1, imports=imports)
    form = "closure" if value.type == "anonymous_function" else "arrow"
    params = value.child_by_field_name("parameters")
    line = value.start_point[0] + 1
    problems: list[tuple[str, str, int]] = []
    plist = [p for p in (params.children if params is not None else []) if p.type in
             ("simple_parameter", "variadic_parameter", "property_promotion_parameter")]
    required = [p for p in plist if p.type == "simple_parameter" and p.child_by_field_name("default_value") is None]
    if len(required) > 1:
        problems.append(("error", _('the callable needs {n} arguments: Runner passes only the context').format(n=len(required)), line))
    if plist:
        first = plist[0]
        kind = first.child_by_field_name("type")
        written = text(kind).replace(" ", "").lower() if kind is not None else ""
        if written and written not in _ACCEPTED_TYPES and not written.startswith("array|") and "|array" not in written:
            problems.append(("error", _('its first parameter is {type}: Runner passes the context, an array').format(type=text(kind)), line))
        if first.type == "simple_parameter" and not any(c.type == "reference_modifier" for c in first.children):
            # fine for one that only reads it: said where the Function is shown, not as a Flow's problem
            problems.append(("note", _('it takes the context by value: what it changes there is lost (&$context keeps it)'), line))
    ret = value.child_by_field_name("return_type")
    signature = (text(params) if params is not None else "()") + (": " + text(ret) if ret is not None else "")
    return SourceInfo(form, signature, returns[0].start_point[0] + 1, tuple(problems), imports)


def _literal(node, text) -> tuple[bool, str | None]:
    """(is a literal, its value) of a PHP string or null."""
    if node.type == "null":
        return True, None
    if node.type == "string":  # single-quoted: no interpolation
        inner = text(node)[1:-1]
        return True, inner.replace("\\'", "'").replace("\\\\", "\\")
    if node.type == "encapsed_string" and all(c.type in ('"', "string_content", "string_value") for c in node.children):
        return True, text(node)[1:-1]
    return False, None


def _is_importer(node, text) -> bool:
    """``$x['_importer']`` (any variable: the context's name is the callable's own)."""
    if node.type != "subscript_expression":
        return False
    index = [c for c in node.children if c.is_named][1:]
    if not index:
        return False
    ok, value = _literal(index[0], text)
    return ok and value == "_importer"


def _imports(root, text):
    aliases: set[str] = set()  # $importer = $context['_importer'];
    stack = [root]
    calls = []
    while stack:
        node = stack.pop()
        if node.type == "assignment_expression":
            left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
            if left is not None and right is not None and left.type == "variable_name" and _is_importer(right, text):
                aliases.add(text(left))
        if node.type == "function_call_expression":
            calls.append(node)
        stack.extend(reversed(node.children))
    for call in calls:
        callee = call.child_by_field_name("function")
        if callee is None or not (_is_importer(callee, text) or (callee.type == "variable_name" and text(callee) in aliases)):
            continue
        line = call.start_point[0] + 1
        args = call.child_by_field_name("arguments")
        values = [next((c for c in a.children if c.is_named), a) for a in (args.children if args is not None else [])
                  if a.type == "argument"]
        if not values:
            continue
        ok, name = _literal(values[0], text)
        module = None
        if ok and len(values) > 1:
            ok, module = _literal(values[1], text)
        if not ok or name is None:
            yield Import(line, None, dynamic=True)
        else:
            yield Import(line, name, module or None)


# ---------------------------------------------------------------- the catalog
@dataclass(frozen=True)
class Reference:
    """A Step's ``condition`` or ``activity``, and the file it resolves to (None: nothing)."""

    flow: Path
    block: str
    step: str
    key: str  # condition | activity
    module: str | None
    name: str
    path: Path | None
    start: int = 0
    end: int = 0

    @property
    def qualified(self) -> str:
        return f"{self.module}:{self.name}" if self.module else self.name

    @property
    def step_name(self) -> str:
        return f"{self.block}.{self.step}"

    @property
    def may_be_callable(self) -> bool:
        """Unqualified and not found: Runner tries a PHP callable of that name (strlen, ns\\fn, Cls::m)."""
        return self.module is None and self.path is None


@dataclass
class FunctionEntry:
    module: str | None
    name: str
    path: Path
    references: list[Reference] = field(default_factory=list)
    imported_by: list[tuple["FunctionEntry", Import]] = field(default_factory=list)
    source: SourceInfo | None = None

    @property
    def qualified(self) -> str:
        return f"{self.module}:{self.name}" if self.module else self.name

    @property
    def roles(self) -> list[str]:
        return sorted({r.key for r in self.references})


@dataclass
class ModuleEntry:
    name: str
    folder: Path
    origin: str  # fm.MODULE_*
    exists: bool
    inside: bool  # in the project (else read-only here)
    functions: list[FunctionEntry] = field(default_factory=list)


@dataclass
class Catalog:
    project: Path
    functions: fm.Functions
    settings: ProjectSettings
    root_functions: list[FunctionEntry]
    modules: list[ModuleEntry]
    references: list[Reference]
    flows: list[Path]

    @property
    def missing(self) -> list[Reference]:
        return [r for r in self.references if r.path is None]

    def entries(self) -> list[FunctionEntry]:
        return self.root_functions + [f for m in self.modules for f in m.functions]

    def entry(self, module: str | None, name: str) -> FunctionEntry | None:
        return next((e for e in self.entries() if e.module == (module or None) and e.name == name), None)

    def entry_at(self, path: Path) -> FunctionEntry | None:
        key = _key(path)
        return next((e for e in self.entries() if _key(e.path) == key), None)

    def module(self, name: str) -> ModuleEntry | None:
        return next((m for m in self.modules if m.name == name), None)

    def root_inside(self) -> bool:
        return inside(self.functions.root, self.project)


def _key(path: Path) -> str:
    try:
        return os.path.normcase(str(path.resolve()))
    except OSError:
        return os.path.normcase(str(path))


def inside(path: Path, project: Path) -> bool:
    try:
        path.resolve().relative_to(project.resolve())
    except (ValueError, OSError):
        return False
    return True


def shown(path: Path, project: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix() or "."
    except (ValueError, OSError):
        return str(path)


def scan_flows(project: Path) -> list[Path]:
    """The project's Runner Flows (YAML files whose root has ``blocks``), outside vendor and hidden folders."""
    out: list[Path] = []
    vendor = _key(vendor_dir(project))
    for folder, dirs, files in os.walk(project):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")
                         and _key(Path(folder) / d) != vendor)
        for name in sorted(files):
            if not name.lower().endswith((".yml", ".yaml")):
                continue
            path = Path(folder) / name
            try:
                if path.stat().st_size > _MAX_FLOW_BYTES:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if is_flow(path, text):
                out.append(path)
                if len(out) >= _MAX_FLOWS:
                    return out
    return out


def references(doc: fm.FlowDoc, flow: Path, functions: fm.Functions, cwd: Path) -> list[Reference]:
    """The Flow's activity and condition references, each with the file Runner's importer would load."""
    out = []
    for step in doc.steps():
        module = step.get("module") or None
        for key in fm.FUNCTION_ATTRS:
            attr = step.attrs.get(key)
            if attr is None or attr.kind != "scalar" or not str(attr.value).strip():
                continue
            name = str(attr.value).strip()
            path = None if module and fm.module_problem(module, name) else functions.find(name, module, cwd)
            out.append(Reference(flow, step.block, step.id, key, module, name, path, attr.value_start, attr.value_end))
    return out


def catalog(project: Path, functions: fm.Functions, *, settings: ProjectSettings | None = None,
            flows: list[Path] | None = None, texts: dict[Path, str] | None = None) -> Catalog:
    """Every Module and Function under ``functions``, with the Steps of ``flows`` (default: the project's)
    that reference them; ``texts`` are open buffers, read instead of their files."""
    settings = settings if settings is not None else load_settings(project)
    flows = list(flows) if flows is not None else scan_flows(project)
    texts = {_key(p): t for p, t in (texts or {}).items()}
    root_entries = [FunctionEntry(None, name, functions.root / (name + ".php")) for name in functions.names(None)]
    modules = []
    for name in functions.module_names():
        folder = functions.folder(name)
        modules.append(ModuleEntry(name, folder, functions.module_origin(name), folder.is_dir(), inside(folder, project),
                                   [FunctionEntry(name, f, folder / (f + ".php")) for f in functions.names(name)]))
    result = Catalog(project, functions, settings, root_entries, modules, [], flows)
    for flow in flows:
        text = texts.get(_key(flow))
        if text is None:
            try:
                text = flow.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
        for ref in references(fm.parse(text), flow, functions, project):
            result.references.append(ref)
            entry = result.entry_at(ref.path) if ref.path is not None else None
            if entry is not None:
                entry.references.append(ref)
    for entry in result.entries():
        entry.source = inspect_source(entry.path)
    for entry in result.entries():
        for imp in entry.source.imports if entry.source else ():
            if imp.dynamic or imp.name is None:
                continue
            if imp.module and fm.module_problem(imp.module, imp.name):
                continue
            target = functions.find(imp.name, imp.module, project)
            found = result.entry_at(target) if target is not None else None
            if found is not None:
                found.imported_by.append((entry, imp))
    return result


# ---------------------------------------------------------------- making Modules and Functions
def module_name_problem(name: str) -> str | None:
    name = name.strip()
    if not name:
        return _('A Module needs a name')
    if fm.module_problem(name, "x") is not None:
        return _('A Module name is letters, digits, _ and -, not starting with -')
    if name.lower() == "vendor":
        return _('vendor is Composer\'s folder, not a Module')
    return None


def function_name_problem(name: str, module: str | None) -> str | None:
    """A new Function's name: Runner's (``compute``, in a Module also ``tax/compute``), without ``.php`` or dots."""
    name = name.strip()
    if not name:
        return _('A Function needs a name')
    if name.lower().endswith(".php"):
        return _('Write the name without .php: Runner adds it')
    segments = name.split("/")
    if not module and len(segments) > 1:
        return _('Outside a Module a Function is one name: a folder of the root is a Module')
    if len(name) > 120 or not all(_NEW_SEGMENT.match(s) for s in segments):
        return _('A Function name is letters, digits, _ and - (and / between folders inside a Module)')
    return None


def target(functions: fm.Functions, module: str | None, name: str, project: Path) -> Path:
    """The file Runner would load for ``module:name`` (the first place it looks)."""
    return functions.candidates(name.strip(), module or None, project)[0]


def where_problem(path: Path, project: Path) -> str | None:
    """Why divide does not write at ``path``: outside the project, or in Composer's vendor folder."""
    if not inside(path, project):
        return _('{path} is outside the project: divide only reads it').format(path=path)
    if inside(path, vendor_dir(project)):
        return _('{path} is in Composer\'s vendor folder: divide only reads it').format(path=shown(path, project))
    rel = Path(shown(path, project)).parts
    if any(part.startswith(".") and part not in (".", "..") for part in rel):
        return _('{path} is in a hidden folder').format(path=shown(path, project))
    return None


@dataclass
class Created:
    """What :func:`create_module` or :func:`create_function` made: a folder or a file, and the folders made for it."""

    path: Path
    folders: list[Path] = field(default_factory=list)  # made, outermost first
    text: str | None = None  # the file's, None for a Module

    def undo(self) -> bool:
        """Remove what was made, while it is as it was made (an edited file stays). True: all of it gone."""
        try:
            if self.text is not None:
                if not self.path.is_file() or self.path.read_text(encoding="utf-8") != self.text:
                    return False
                self.path.unlink()
            for folder in reversed(self.folders):
                if folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()
        except OSError:
            return False
        return True


def _make_folders(folder: Path) -> list[Path]:
    missing = []
    probe = folder
    while not probe.exists():
        missing.append(probe)
        if probe.parent == probe:
            break
        probe = probe.parent
    missing.reverse()
    for path in missing:
        path.mkdir()
    return missing


def module_target(functions: fm.Functions, name: str) -> Path:
    return functions.folder(name.strip())


def create_module(functions: fm.Functions, project: Path, name: str) -> Created:
    """The Module's folder: ``<root>/<name>`` (or its ``_modules`` folder), made if it is not there."""
    name = name.strip()
    if problem := module_name_problem(name):
        raise CreateError(problem)
    folder = module_target(functions, name)
    if folder.exists():
        raise CreateError(_('Module {name} is already there: {path}').format(name=name, path=shown(folder, project)))
    if problem := where_problem(folder, project):
        raise CreateError(problem)
    try:
        return Created(folder, _make_folders(folder))
    except OSError as exc:
        raise CreateError(str(exc)) from exc


def function_source(role: str, module: str | None, name: str) -> str:
    """A minimal Runner Function: a callable of the shared context (PHP 8.1+)."""
    qualified = f"{module}:{name}" if module else name
    if role == "condition":
        return ("<?php\n\ndeclare(strict_types=1);\n\n"
                f"// {qualified}, a condition: the Step runs its activity, call or jump only when this returns true.\n"
                "// $context is the Flow's shared context (by reference: what you set stays).\n\n"
                "return function (array &$context): bool {\n"
                "    return true;\n"
                "};\n")
    return ("<?php\n\ndeclare(strict_types=1);\n\n"
            f"// {qualified}, an activity: Runner keeps what it returns in $context[<the Step's id>].\n"
            "// $context is the Flow's shared context (by reference: what you set stays).\n"
            "// Another Function: $context['_importer']('name', 'module') returns its callable.\n\n"
            "return function (array &$context): mixed {\n"
            "    return null;\n"
            "};\n")


def create_function(functions: fm.Functions, project: Path, module: str | None, name: str, role: str) -> Created:
    """``<module folder>/<name>.php`` (or ``<root>/<name>.php``) from :func:`function_source`; never over a file."""
    module = (module or "").strip() or None
    name = name.strip()
    if role not in ROLES:
        raise CreateError(_('A Function is an activity or a condition'))
    if module and (problem := module_name_problem(module)):
        raise CreateError(problem)
    if problem := function_name_problem(name, module):
        raise CreateError(problem)
    path = target(functions, module, name, project)
    if path.exists():
        raise CreateError(_('{path} is already there: open it instead').format(path=shown(path, project)))
    if problem := where_problem(path, project):
        raise CreateError(problem)
    text = function_source(role, module, name)
    folders: list[Path] = []
    try:
        folders = _make_folders(path.parent)
        with open(path, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError as exc:
        Created(path, folders).undo()
        raise CreateError(_('{path} is already there: open it instead').format(path=shown(path, project))) from exc
    except OSError as exc:
        Created(path, folders).undo()
        raise CreateError(str(exc)) from exc
    return Created(path, folders, text)
