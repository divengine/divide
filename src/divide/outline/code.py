"""Outlines of code: JavaScript, CSS, SQL and shell scripts (``.env`` too)."""

from __future__ import annotations

from divide.outline import Node, Span, default_kind, first, named, parse

_FUNCTIONS = ("arrow_function", "function_expression", "function", "generator_function")


def _no_semicolon(label: list[Span]) -> list[Span]:
    if label and label[-1][0].endswith(";"):
        label = label[:-1] + [(label[-1][0].rstrip(";").rstrip(), label[-1][1])]
    return [(t, k) for t, k in label if t]


def javascript(text: str, **_context) -> list[Node] | None:
    """Imports, classes with their methods and fields (``#private`` ones marked
    -), functions, and the file's own constants and variables (a constant
    holding a function or a class counts as one)."""
    parsed = parse("javascript", text)
    if parsed is None:
        return None

    def signature(name, params) -> list[Span]:
        label = parsed.paint.spans(name.start_byte, name.end_byte)
        return label + (parsed.paint.node_spans(params) if params is not None else [("()", None)])

    def members(body) -> list[Node]:
        out = []
        for member in body.named_children:
            name = member.child_by_field_name("name") if member.type == "method_definition" else (
                member.child_by_field_name("property") if member.type == "field_definition" else None)
            if name is None:
                continue
            mark = "-" if name.type == "private_property_identifier" else "+"
            if member.type == "method_definition":
                out.append(parsed.node("method", name, signature(name, member.child_by_field_name("parameters")), mark=mark))
            else:
                out.append(parsed.node("property", name, default_kind(parsed.paint.spans(name.start_byte, name.end_byte), "ts.property"), mark=mark))
        return out

    def klass(node, name) -> Node:
        heritage = first(node, "class_heritage")
        label = default_kind(parsed.paint.node_spans(name, heritage), "ts.type")
        body = node.child_by_field_name("body")
        return parsed.node("class", name, label, members(body) if body is not None else [])

    def declaration(node) -> list[Node]:
        name = node.child_by_field_name("name")
        if node.type in ("function_declaration", "generator_function_declaration") and name is not None:
            return [parsed.node("function", name, signature(name, node.child_by_field_name("parameters")))]
        if node.type == "class_declaration" and name is not None:
            return [klass(node, name)]
        if node.type in ("lexical_declaration", "variable_declaration"):
            constant = parsed.text(node).startswith("const")
            out = []
            for declarator in named(node, "variable_declarator"):
                name = declarator.child_by_field_name("name")
                value = declarator.child_by_field_name("value")
                if name is None:
                    continue
                if value is not None and value.type in _FUNCTIONS:
                    out.append(parsed.node("function", name, signature(name, value.child_by_field_name("parameters"))))
                elif value is not None and value.type == "class":
                    out.append(klass(value, name))
                else:
                    out.append(parsed.node("const" if constant else "variable", name,
                                           parsed.paint.spans(name.start_byte, name.end_byte)))
            return out
        if node.type == "import_statement":
            return [parsed.node("import", node, _no_semicolon(parsed.line(node)))]
        if node.type == "export_statement":
            inner = node.child_by_field_name("declaration") or first(
                node, "function_declaration", "class_declaration", "lexical_declaration", "variable_declaration")
            return declaration(inner) if inner is not None else []
        return []

    return [n for child in parsed.tree.root_node.named_children for n in declaration(child)]


def css(text: str, **_context) -> list[Node] | None:
    """The rules by their selectors; @media, @supports and @keyframes with the
    rules inside them; @import and the other at-rules as they are written."""
    parsed = parse("css", text)
    if parsed is None:
        return None

    def rules(container) -> list[Node]:
        out = []
        for node in container.named_children:
            block = first(node, "block", "keyframe_block_list")
            if node.type == "rule_set":
                selectors = first(node, "selectors")
                if selectors is not None:
                    out.append(parsed.node("rule", selectors, parsed.paint.node_spans(selectors)))
            elif node.type == "keyframe_block":
                out.append(parsed.node("rule", node, parsed.line(node, block)))
            elif node.type.endswith("_statement") or node.type == "at_rule":
                label = parsed.line(node, block) if block is not None else parsed.line(node)
                label = _no_semicolon(label)
                out.append(parsed.node("at-rule", node, label, rules(block) if block is not None else []))
        return out

    return rules(parsed.tree.root_node)


def sql(text: str, **_context) -> list[Node] | None:
    """What the script creates: tables with their columns and types, views,
    indexes, functions, triggers..."""
    parsed = parse("sql", text)
    if parsed is None:
        return None
    kinds = {"create_table": "table", "create_view": "view", "create_materialized_view": "view",
             "create_index": "index", "create_function": "function", "create_procedure": "function",
             "create_trigger": "function", "create_type": "table", "create_schema": "namespace",
             "create_database": "namespace", "create_sequence": "const"}

    def created(node) -> Node | None:
        kind = kinds.get(node.type)
        if kind is None:
            return None
        name = first(node, "object_reference") if node.type != "create_index" else first(node, "identifier")
        name = name or first(node, "identifier", "object_reference")
        if name is None:
            return None
        label = default_kind(parsed.paint.spans(name.start_byte, name.end_byte), "ts.function" if kind == "function" else "ts.type")
        if node.type == "create_index":
            table = first(node, "object_reference")
            if table is not None:
                label = label + [(" on ", None)] + parsed.paint.spans(table.start_byte, table.end_byte)
        args = first(node, "function_arguments")
        if args is not None:
            label = label + parsed.paint.node_spans(args)
        columns = []
        definitions = first(node, "column_definitions")
        for column in named(definitions, "column_definition") if definitions is not None else []:
            column_name = first(column, "identifier")
            if column_name is None:
                continue
            kind_node = column_name.next_named_sibling
            label_c = default_kind(parsed.paint.spans(column_name.start_byte, column_name.end_byte), "ts.property")
            if kind_node is not None:
                label_c = label_c + [(" ", None)] + parsed.paint.node_spans(kind_node)
            columns.append(parsed.node("column", column_name, label_c))
        return parsed.node(kind, name, label, columns)

    out = []
    for statement in parsed.tree.root_node.named_children:
        for node in (statement.named_children if statement.type == "statement" else [statement]):
            found = created(node)
            if found is not None:
                out.append(found)
    return out


def shell(text: str, **_context) -> list[Node] | None:
    """The functions and the variables the script sets (every line of a ``.env``)."""
    parsed = parse("shell", text)
    if parsed is None:
        return None
    out = []
    for node in parsed.tree.root_node.named_children:
        if node.type == "function_definition":
            name = node.child_by_field_name("name")
            if name is not None:
                out.append(parsed.node("function", name, parsed.paint.spans(name.start_byte, name.end_byte) + [("()", None)]))
        assignments = [node] if node.type == "variable_assignment" else (
            named(node, "variable_assignment") if node.type == "declaration_command" else [])
        for assignment in assignments:
            name = assignment.child_by_field_name("name")
            if name is not None:
                out.append(parsed.node("variable", name, parsed.line(assignment)))
    return out
