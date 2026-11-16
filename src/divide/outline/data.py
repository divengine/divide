"""Outlines of data: the keys of JSON, YAML and TOML, the sections and keys of
INI, the columns of CSV. A key holding a value shows it beside it; one
holding an object or a list holds its keys, and says how many items a list has."""

from __future__ import annotations

from divide.outline import Node, Painter, Span, first, named, parse, tidy

MAX_VALUE = 40


def _value(spans: list[Span]) -> list[Span]:
    return tidy(spans, MAX_VALUE)


# --------------------------------------------------------------------- JSON
def json(text: str, **_context) -> list[Node] | None:
    """Div JSON (comments and references allowed), by its keys; the objects of a
    list as ``[0]``, ``[1]``... with their first key and value beside them."""
    from divide.lang import divjson

    tokens = [t for t in divjson.tokenize(text) if t.kind not in ("json.comment", "json.error")]
    paint = Painter(text, tokens)
    at = [0]

    def peek(offset: int = 0):
        i = at[0] + offset
        return tokens[i] if i < len(tokens) else None

    def punct(tok, char: str) -> bool:
        return tok is not None and tok.kind == "json.punct" and text[tok.start:tok.end] == char

    def value() -> tuple[str, int, int, list[Node], int]:
        """(kind, start, end, children, items) of the value at the cursor, moving past it."""
        tok = peek()
        if tok is None:
            return "key", 0, 0, [], 0
        if punct(tok, "{"):
            at[0] += 1
            children = members("}")
            return "object", tok.start, tok.end, children, len(children)
        if punct(tok, "["):
            at[0] += 1
            children, count = items()
            return "array", tok.start, tok.end, children, count
        at[0] += 1
        return "key", tok.start, tok.end, [], 0

    def members(close: str) -> list[Node]:
        out: list[Node] = []
        while (tok := peek()) is not None and not punct(tok, close):
            if tok.kind == "json.key" and punct(peek(1), ":"):
                at[0] += 2
                kind, start, end, children, count = value()
                label = paint.spans(tok.start, tok.end)
                if kind == "key":
                    label = label + [(": ", None)] + _value(paint.spans(start, end))
                elif kind == "array":
                    label = label + [(f" [{count}]", None)]
                out.append(Node(kind, label, tok.start, tok.end, children=children))
            else:
                at[0] += 1  # a comma, or what an error left
        at[0] += 1
        return out

    def items() -> tuple[list[Node], int]:
        out: list[Node] = []
        count = 0
        while (tok := peek()) is not None and not punct(tok, "]"):
            if punct(tok, ","):
                at[0] += 1
                continue
            kind, start, end, children, inner = value()
            if kind == "object":
                label: list[Span] = [(f"[{count}]", None)]
                if children and not children[0].children:
                    label += [(" ", None)] + children[0].label
                out.append(Node("object", label, start, end, children=children))
            elif kind == "array":
                out.append(Node("array", [(f"[{count}] [{inner}]", None)], start, end, children=children))
            count += 1
        at[0] += 1
        return out, count

    first_token = peek()
    if punct(first_token, "{"):
        at[0] += 1
        return members("}")
    if punct(first_token, "["):
        at[0] += 1
        return items()[0]
    return []


# --------------------------------------------------------------------- YAML
def yaml(text: str, **_context) -> list[Node] | None:
    """The keys, nested; the mappings of a list as ``-`` with their first key."""
    parsed = parse("yaml", text)
    if parsed is None:
        return None

    def inner(node):
        """The mapping or the sequence a value is, past its block_node / flow_node."""
        while node is not None and node.type in ("block_node", "flow_node"):
            node = first(node, "block_mapping", "block_sequence", "flow_mapping", "flow_sequence",
                         "plain_scalar", "double_quote_scalar", "single_quote_scalar", "block_scalar") or None
        return node

    def mapping(node) -> list[Node]:
        out = []
        for pair in named(node, "block_mapping_pair", "flow_pair"):
            key = pair.child_by_field_name("key")
            if key is None:
                continue
            val = inner(pair.child_by_field_name("value"))
            label = parsed.paint.node_spans(key)
            if val is not None and val.type in ("block_mapping", "flow_mapping"):
                out.append(parsed.node("object", key, label, mapping(val)))
            elif val is not None and val.type in ("block_sequence", "flow_sequence"):
                children, count = sequence(val)
                out.append(parsed.node("array", key, label + [(f" [{count}]", None)], children))
            else:
                text_value = _value(parsed.line(val)) if val is not None else []
                out.append(parsed.node("key", key, label + ([(": ", None)] + text_value if text_value else [])))
        return out

    def sequence(node) -> tuple[list[Node], int]:
        out, count = [], 0
        for item in named(node, "block_sequence_item", "flow_node", "block_node"):
            val = inner(first(item, "block_node", "flow_node") if item.type == "block_sequence_item" else item)
            if val is not None and val.type in ("block_mapping", "flow_mapping"):
                children = mapping(val)
                label: list[Span] = [("-", None)]
                if children and not children[0].children:
                    label += [(" ", None)] + children[0].label
                out.append(parsed.node("object", item, label, children))
            count += 1
        return out, count

    out = []
    for document in named(parsed.tree.root_node, "document"):
        root = inner(first(document, "block_node", "flow_node"))
        if root is not None and root.type in ("block_mapping", "flow_mapping"):
            out += mapping(root)
        elif root is not None and root.type in ("block_sequence", "flow_sequence"):
            out += sequence(root)[0]
    return out


# --------------------------------------------------------------------- TOML
def toml(text: str, **_context) -> list[Node] | None:
    """The tables (``[owner]``, ``[[products]]``) with their keys and values."""
    parsed = parse("toml", text)
    if parsed is None:
        return None

    def pairs(node) -> list[Node]:
        out = []
        for pair in named(node, "pair"):
            key = pair.named_children[0] if pair.named_children else None
            if key is not None:
                value = pair.named_children[-1] if len(pair.named_children) > 1 else None
                label = parsed.paint.node_spans(key)
                if value is not None:
                    label = label + [(" = ", None)] + _value(parsed.line(value))
                out.append(parsed.node("key", key, label))
        return out

    out = pairs(parsed.tree.root_node)
    for table in named(parsed.tree.root_node, "table", "table_array_element"):
        key = table.named_children[0] if table.named_children else table
        header = parsed.source.find(b"]", key.end_byte)
        label = parsed.paint.spans(table.start_byte, (header + (2 if table.type == "table_array_element" else 1))
                                   if header >= 0 else key.end_byte)
        out.append(parsed.node("array" if table.type == "table_array_element" else "table", key, label, pairs(table)))
    return out


# ---------------------------------------------------------------- INI, CSV
def ini(text: str, **_context) -> list[Node] | None:
    """The sections, each with its keys and their values (``php.ini``, ``.editorconfig``)."""
    from divide.lang import plain

    tokens = plain.ini_tokens(text)
    paint = Painter(text, tokens)
    out: list[Node] = []
    section: Node | None = None
    for tok in tokens:
        if tok.kind == "ini.section":
            section = Node("section", paint.spans(tok.start, tok.end), tok.start, tok.end)
            out.append(section)
        elif tok.kind == "ini.key":
            end = text.find("\n", tok.start)
            label = _value(paint.spans(tok.start, end if end >= 0 else len(text)))
            (section.children if section is not None else out).append(Node("key", label, tok.start, tok.end))
    return out


def csv(text: str, path=None, **_context) -> list[Node] | None:
    """The columns, by the names in the first row."""
    from divide.lang import plain

    tsv = path is not None and str(path).lower().endswith(".tsv")
    tokens = plain.csv_tokens(text, plain.csv_separator(text, tsv))
    paint = Painter(text, tokens)
    end = text.find("\n")
    end = len(text) if end < 0 else end
    return [Node("column", paint.spans(tok.start, tok.end) or [(f"({n + 1})", None)], tok.start, tok.end)
            for n, tok in enumerate(t for t in tokens if t.start < end and t.kind.startswith("csv.col"))]
