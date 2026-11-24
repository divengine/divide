"""What a Function asks its context for, read from its file (never run): the doubles a Mock Simulation
needs (UI-independent).

The Mock Simulation dialog pre-fills its doubles from this scan; every one it writes is a placeholder
the user fills in, and the scenario keeps ``unknown: fail`` (a call nobody doubled throws). The scan
reads the PHP with tree-sitter, as the Functions window reads a Function's imports
(:func:`divide.run.flowfunctions.inspect_source`):

- **imports**: ``$context['_importer']('name', 'module')``, also through a variable it was assigned
  to; a name computed at run time cannot be known and is reported as ``dynamic``;
- **services**: ``$context['key']->method(`` (and ``?->``), also through a variable assigned from
  ``$context['key']``; keys starting with ``_`` belong to Runner and are left out.

A scan is a help, not a proof: a call it cannot see (a method name in a variable, a service passed
to another function) is not found, and the simulation then fails loudly on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from divide.run import flowfunctions as ff

CALLS = ("member_call_expression", "nullsafe_member_call_expression")
PLACEHOLDER = {"returns": None}  # what a scanned double answers until the user says otherwise


@dataclass
class Scan:
    imports: list[str] = field(default_factory=list)  # importer keys: "module:name" or "name", in order
    dynamic: list[int] = field(default_factory=list)  # lines of imports whose name is computed
    services: dict[str, list[str]] = field(default_factory=dict)  # context key -> methods called, in order
    readable: bool = True  # False: the file could not be read or parsed

    def doubles(self) -> dict:
        """A ``doubles`` object with a placeholder outcome for each name found."""
        return {"importer": {key: dict(PLACEHOLDER) for key in self.imports},
                "services": {key: {m: dict(PLACEHOLDER) for m in methods} for key, methods in self.services.items()}}

    def missing(self, doubles: dict) -> list[str]:
        """What the scan found that ``doubles`` does not double, as ``name`` and ``service->method``."""
        importer = doubles.get("importer") if isinstance(doubles, dict) and isinstance(doubles.get("importer"), dict) else {}
        services = doubles.get("services") if isinstance(doubles, dict) and isinstance(doubles.get("services"), dict) else {}
        out = [key for key in self.imports if key not in importer]
        for key, methods in self.services.items():
            have = services.get(key) if isinstance(services.get(key), dict) else {}
            out += [f"{key}->{m}" for m in methods if m not in have]
        return out


def merge(doubles: dict, scan: Scan) -> dict:
    """``doubles`` with a placeholder for what the scan found and it lacks; what it had, kept as it was."""
    out = {"importer": dict(doubles.get("importer") or {}), "services": {k: dict(v) for k, v in (doubles.get("services") or {}).items()
                                                                          if isinstance(v, dict)}}
    for key in scan.imports:
        out["importer"].setdefault(key, dict(PLACEHOLDER))
    for key, methods in scan.services.items():
        have = out["services"].setdefault(key, {})
        for method in methods:
            have.setdefault(method, dict(PLACEHOLDER))
    return out


def scan_file(path: Path) -> Scan:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return Scan(readable=False)
    return scan_text(data)


def scan_text(data: bytes | str) -> Scan:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    parser = ff._parser()
    if parser is None:
        return Scan(readable=False)
    root = parser.parse(raw).root_node

    def text(node) -> str:
        return raw[node.start_byte:node.end_byte].decode("utf-8", "replace")

    out = Scan()
    for imp in ff._imports(root, text):
        if imp.dynamic or imp.name is None:
            out.dynamic.append(imp.line)
        elif imp.qualified not in out.imports:
            out.imports.append(imp.qualified)
    context = _context_name(root, text)
    if context is None:
        return out

    def service(node) -> str | None:
        """``$context['key']``'s key, when it is a service a double can stand for."""
        if node.type != "subscript_expression":
            return None
        named = [c for c in node.children if c.is_named]
        if len(named) < 2 or named[0].type != "variable_name" or text(named[0]) != context:
            return None
        ok, key = ff._literal(named[1], text)
        return key if ok and key and not key.startswith("_") else None

    aliases: dict[str, str] = {}  # $mailer = $context['mailer'];
    calls = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "assignment_expression":
            left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
            if left is not None and right is not None and left.type == "variable_name" and (key := service(right)):
                aliases[text(left)] = key
        if node.type in CALLS:
            calls.append(node)
        stack.extend(reversed(node.children))
    for call in sorted(calls, key=lambda n: n.start_byte):
        target, name = call.child_by_field_name("object"), call.child_by_field_name("name")
        if target is None or name is None or name.type != "name":
            continue  # $x->$method(): not knowable
        key = service(target) or (aliases.get(text(target)) if target.type == "variable_name" else None)
        if key is None:
            continue
        methods = out.services.setdefault(key, [])
        if text(name) not in methods:
            methods.append(text(name))
    return out


def _context_name(root, text) -> str | None:
    """The variable the Function's callable takes the context in (``$context`` when unsure)."""
    for child in root.children:
        if child.type != "return_statement":
            continue
        value = next((c for c in child.children if c.is_named), None)
        if value is None or value.type not in ("anonymous_function", "arrow_function"):
            return "$context"
        params = value.child_by_field_name("parameters")
        for param in params.children if params is not None else []:
            if param.type in ("simple_parameter", "variadic_parameter"):
                name = param.child_by_field_name("name")
                return text(name) if name is not None else "$context"
        return None  # a callable with no parameter takes no context
    return "$context"
