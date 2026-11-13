"""A tiny language server for the tests (pygls): completion, hover,
definition, and a warning on every ``BAD`` in the text."""

import re

from lsprotocol import types
from pygls.lsp.server import LanguageServer

server = LanguageServer("fake-php", "1")


def publish(uri: str, text: str) -> None:
    diagnostics = []
    for line, row in enumerate(text.split("\n")):
        for m in re.finditer("BAD", row):
            diagnostics.append(types.Diagnostic(
                range=types.Range(start=types.Position(line=line, character=m.start()), end=types.Position(line=line, character=m.end())),
                message="BAD is not allowed", severity=types.DiagnosticSeverity.Warning, source="fake"))
    server.text_document_publish_diagnostics(types.PublishDiagnosticsParams(uri=uri, diagnostics=diagnostics))


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(params: types.DidOpenTextDocumentParams) -> None:
    publish(params.text_document.uri, params.text_document.text)


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(params: types.DidChangeTextDocumentParams) -> None:
    doc = server.workspace.get_text_document(params.text_document.uri)
    publish(doc.uri, doc.source)


@server.feature(types.TEXT_DOCUMENT_COMPLETION, types.CompletionOptions(trigger_characters=["$", ">"], resolve_provider=True))
def completion(params: types.CompletionParams) -> types.CompletionList:
    return types.CompletionList(is_incomplete=False, items=[
        types.CompletionItem(label="total", kind=types.CompletionItemKind.Method, detail="float",
                             insert_text="total($0)", insert_text_format=types.InsertTextFormat.Snippet, sort_text="1"),
        types.CompletionItem(label="taxes", kind=types.CompletionItemKind.Method, sort_text="2"),
        types.CompletionItem(label="name", kind=types.CompletionItemKind.Property, sort_text="3"),
        # a class from another namespace: the server adds its `use` line (phpactor's way)
        types.CompletionItem(label="Tpl (Engine)", insert_text="Tpl", kind=types.CompletionItemKind.Class, sort_text="4",
                             additional_text_edits=[
                                 types.TextEdit(range=types.Range(start=types.Position(line=1, character=0), end=types.Position(line=1, character=0)), new_text="\nuse Engine\\Tpl;"),
                                 types.TextEdit(range=types.Range(start=types.Position(line=1, character=0), end=types.Position(line=1, character=0)), new_text="\n"),
                             ]),
    ])


@server.feature(types.COMPLETION_ITEM_RESOLVE)
def resolve(item: types.CompletionItem) -> types.CompletionItem:
    if item.label == "total":
        item.documentation = types.MarkupContent(kind=types.MarkupKind.Markdown, value="### Shop::total\n\nAdds it all up.")
    return item


@server.feature(types.TEXT_DOCUMENT_SIGNATURE_HELP, types.SignatureHelpOptions(trigger_characters=["(", ","]))
def signature(params: types.SignatureHelpParams) -> types.SignatureHelp | None:
    doc = server.workspace.get_text_document(params.text_document.uri)
    line = doc.lines[params.position.line][: params.position.character]
    call = line.rfind("total(")
    if call < 0 or ")" in line[call:]:
        return None
    return types.SignatureHelp(
        signatures=[types.SignatureInformation(
            label="total(int $a, string $b): float",
            documentation="Adds it all up.",
            parameters=[types.ParameterInformation(label="int $a"), types.ParameterInformation(label="string $b")])],
        active_signature=0, active_parameter=line[call:].count(","))


@server.feature(types.TEXT_DOCUMENT_HOVER)
def hover(params: types.HoverParams) -> types.Hover:
    return types.Hover(contents=types.MarkupContent(kind=types.MarkupKind.Markdown, value="```php\n<?php class Shop\n```\nA shop."))


@server.feature(types.TEXT_DOCUMENT_DEFINITION)
def definition(params: types.DefinitionParams) -> types.Location:
    return types.Location(uri=params.text_document.uri, range=types.Range(
        start=types.Position(line=1, character=0), end=types.Position(line=3, character=1)))


if __name__ == "__main__":
    server.start_io()
