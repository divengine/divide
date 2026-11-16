"""The outline of a PHP file: its declarations, from tree-sitter's PHP grammar.

Namespaces, classes, interfaces, traits and enums, with their constants,
cases, properties and methods below them (UML's marks for visibility), and
the functions and constants of the file, also inside ``if
(!function_exists(...)) { }``. Functions show their parameters and return
type as written; closures and anonymous classes are left out. The grammar
colours the editor too: no language server needed, and errors don't stop it.
"""

from __future__ import annotations

from divide.lang import php as php_lang
from divide.lang import treesitter
from divide.outline import VISIBILITY, Node, Offsets, TreePainter, default_kind

_CLASSES = {"class_declaration": "class", "interface_declaration": "interface",
            "trait_declaration": "trait", "enum_declaration": "enum"}


def outline(text: str, **_context) -> list[Node] | None:
    found = php_lang.grammar()
    if found is None:
        return None
    from tree_sitter import Parser

    language, query_source = found
    source = text.encode("utf-8")
    tree = Parser(language).parse(source)  # type: ignore[arg-type]
    paint = TreePainter(source, tree, treesitter.query(language, query_source))
    offset = Offsets(source)

    def node(kind: str, name, *rest, mark: str = "") -> Node:
        spans = paint.node_spans(name, *rest)
        if kind in _CLASSES.values():
            spans = default_kind(spans, "php.type")  # Cart extends Base implements Priced
        elif kind in ("case", "const"):
            spans = default_kind(spans, "php.constant")
        return Node(kind, spans, offset(name.start_byte), offset(name.end_byte), mark)

    def mark_of(declaration) -> str:
        for child in declaration.named_children:
            if child.type == "visibility_modifier":
                return VISIBILITY.get(source[child.start_byte:child.end_byte].decode().lower(), "+")
        return "+"

    def typed(declaration, name):
        """``$items`` with its type after it, as UML writes it: ``$items: array``."""
        kind = declaration.child_by_field_name("type")
        if kind is None:
            return node("property", name, mark=mark_of(declaration))
        n = node("property", name, mark=mark_of(declaration))
        n.label = n.label + [(": ", None)] + paint.node_spans(kind)
        return n

    def function(kind: str, declaration, mark: str = "") -> Node:
        n = node(kind, declaration.child_by_field_name("name"), mark=mark)
        params = declaration.child_by_field_name("parameters")
        returns = declaration.child_by_field_name("return_type")
        n.label = n.label + (paint.node_spans(params) if params is not None else [("()", None)])
        if returns is not None:
            n.label = n.label + [(": ", None)] + paint.node_spans(returns)
        return n

    def consts(declaration, mark: str = "") -> list[Node]:
        return [node("const", element.named_children[0], mark=mark)
                for element in declaration.named_children
                if element.type == "const_element" and element.named_children]

    def members(body) -> list[Node]:
        out: list[Node] = []
        for member in body.named_children:
            if member.type == "method_declaration" and member.child_by_field_name("name") is not None:
                out.append(function("method", member, mark_of(member)))
            elif member.type == "property_declaration":
                for element in member.named_children:
                    if element.type == "property_element" and element.named_children:
                        out.append(typed(member, element.named_children[0]))
            elif member.type == "const_declaration":
                out += consts(member, mark_of(member))
            elif member.type == "enum_case" and member.child_by_field_name("name") is not None:
                out.append(node("case", member.child_by_field_name("name")))
        return out

    def top(container) -> list[Node]:
        found: list[Node] = []
        out = found  # after ``namespace X;``, what follows is the namespace's
        for child in container.named_children:
            name = child.child_by_field_name("name")
            if child.type == "namespace_definition":
                body = child.child_by_field_name("body")
                if name is not None:
                    space = node("namespace", name)
                    found.append(space)
                    if body is not None:  # namespace X { ... }
                        space.children = top(body)
                        out = found
                    else:
                        out = space.children
                elif body is not None:
                    found.extend(top(body))
                    out = found
            elif child.type in _CLASSES and name is not None:
                heads = [c for c in child.named_children if c.type in ("base_clause", "class_interface_clause")]
                kind = _CLASSES[child.type]
                declared = node(kind, name, *heads)
                body = child.child_by_field_name("body")
                if body is not None:
                    declared.children = members(body)
                out.append(declared)
            elif child.type == "function_definition" and name is not None:
                out.append(function("function", child))
            elif child.type == "const_declaration":
                out += consts(child)
            elif child.type in ("compound_statement", "declare_statement", "if_statement"):
                out += top(child)  # function_exists() guards, declare(...) { }
        return found

    return top(tree.root_node)
