"""Outlines of documents: the elements of HTML and XML, the headings of Markdown."""

from __future__ import annotations

from divide.outline import Node, Span, default_kind, first, named, parse

_HTML_ELEMENTS = ("element", "script_element", "style_element")


def html(text: str, **_context) -> list[Node] | None:
    """Every element, nested as written, by its tag, id and classes: ``main#main.page``
    (``src`` or ``href`` for scripts, links and images)."""
    parsed = parse("html", text)
    if parsed is None:
        return None

    def attributes(tag) -> dict[str, str]:
        out = {}
        for attr in named(tag, "attribute"):
            name = first(attr, "attribute_name")
            value = first(attr, "quoted_attribute_value", "attribute_value")
            if name is not None:
                out[parsed.text(name).lower()] = parsed.text(value).strip("\"'") if value is not None else ""
        return out

    def element(node) -> Node | None:
        tag = first(node, "start_tag", "self_closing_tag")
        name = first(tag, "tag_name") if tag is not None else None
        if name is None:
            return None
        attrs = attributes(tag)
        label: list[Span] = list(parsed.paint.spans(name.start_byte, name.end_byte)) or [(parsed.text(name), "ts.tag")]
        if attrs.get("id"):
            label.append(("#" + attrs["id"], "ts.constant"))
        for cls in attrs.get("class", "").split():
            label.append(("." + cls, "ts.type"))
        for key in ("src", "href"):
            if attrs.get(key):
                label.append((" " + attrs[key], "ts.string"))
                break
        return parsed.node("element", name, label, elements(node))

    def elements(container) -> list[Node]:
        out = []
        for child in container.named_children:
            if child.type in _HTML_ELEMENTS:
                found = element(child)
                if found is not None:
                    out.append(found)
            elif child.type == "erroneous_end_tag":
                continue
        return out

    return elements(parsed.tree.root_node)


def xml(text: str, **_context) -> list[Node] | None:
    """Every element, nested as written, by its name and its ``name``, ``id`` or
    first attribute: ``testsuite name="unit"``."""
    parsed = parse("xml", text)
    if parsed is None:
        return None

    def element(node) -> Node | None:
        tag = first(node, "STag", "EmptyElemTag")
        name = first(tag, "Name") if tag is not None else None
        if name is None:
            return None
        label = list(parsed.paint.spans(name.start_byte, name.end_byte))
        attrs = named(tag, "Attribute")
        chosen = next((a for a in attrs if first(a, "Name") is not None
                       and parsed.text(first(a, "Name")) in ("name", "id", "key")), attrs[0] if attrs else None)
        if chosen is not None:
            label += [(" ", None)] + parsed.paint.spans(chosen.start_byte, chosen.end_byte)
        content = first(node, "content")
        return parsed.node("element", name, default_kind(label, "ts.tag"), elements(content) if content is not None else [])

    def elements(container) -> list[Node]:
        return [found for child in named(container, "element") if (found := element(child)) is not None]

    return elements(parsed.tree.root_node)


def markdown(text: str, **_context) -> list[Node] | None:
    """The headings, each one holding the headings below it of a deeper level."""
    parsed = parse("markdown", text)
    if parsed is None:
        return None

    def heading(node) -> Node | None:
        if node.type == "atx_heading":
            content = first(node, "inline")
        elif node.type == "setext_heading":
            paragraph = first(node, "paragraph")
            content = first(paragraph, "inline") if paragraph is not None else None
        else:
            return None
        if content is None:
            return None
        return parsed.node("heading", content, default_kind(parsed.line(content), "ts.heading"))

    def section(node) -> list[Node]:
        out: list[Node] = []
        head: Node | None = None
        for child in node.named_children:
            if child.type == "section":
                (head.children if head is not None else out).extend(section(child))
            elif (found := heading(child)) is not None:
                if head is None:
                    head = found
                    out.append(found)
                else:  # a setext heading the grammar left inside the section before
                    head.children.append(found)
        return out

    return section(parsed.tree.root_node)
