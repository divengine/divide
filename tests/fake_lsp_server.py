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


@server.feature(types.TEXT_DOCUMENT_COMPLETION, types.CompletionOptions(trigger_characters=["$", ">"]))
def completion(params: types.CompletionParams) -> types.CompletionList:
    return types.CompletionList(is_incomplete=False, items=[
        types.CompletionItem(label="total", kind=types.CompletionItemKind.Method, detail="float",
                             insert_text="total($0)", insert_text_format=types.InsertTextFormat.Snippet, sort_text="1"),
        types.CompletionItem(label="taxes", kind=types.CompletionItemKind.Method, sort_text="2"),
        types.CompletionItem(label="name", kind=types.CompletionItemKind.Property, sort_text="3"),
    ])


@server.feature(types.TEXT_DOCUMENT_HOVER)
def hover(params: types.HoverParams) -> types.Hover:
    return types.Hover(contents=types.MarkupContent(kind=types.MarkupKind.Markdown, value="```php\n<?php class Shop\n```\nA shop."))


@server.feature(types.TEXT_DOCUMENT_DEFINITION)
def definition(params: types.DefinitionParams) -> types.Location:
    return types.Location(uri=params.text_document.uri, range=types.Range(
        start=types.Position(line=1, character=0), end=types.Position(line=3, character=1)))


if __name__ == "__main__":
    server.start_io()
