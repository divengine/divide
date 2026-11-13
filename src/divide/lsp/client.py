"""One language server for one project: the conversation, on pygls's client.

``LspSession`` starts the server, says hello (initialize), keeps it informed
of the documents open in divide (open, change, save, close: the whole text
each time) and asks it for completions, hovers and definitions. What the
server publishes on its own (diagnostics) goes to a callback.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from lsprotocol import types
from pygls.lsp.client import BaseLanguageClient
from pygls.uris import from_fs_path, to_fs_path

from divide import __version__
from divide.lsp import ServerSpec, line_starts, to_offset, to_position

logging.getLogger("pygls").setLevel(logging.CRITICAL)  # the servers' quirks are not divide's errors


@dataclass
class ServerDiagnostic:
    start: int
    end: int
    severity: str  # "error" | "warning"
    message: str


@dataclass
class Location:
    path: Path
    line: int
    character: int  # UTF-16, as the protocol says; converted when the file is read


def uri_of(path: Path) -> str:
    return from_fs_path(str(path)) or path.as_uri()


class LspSession:
    """A running language server (``start``), its documents and its answers."""

    def __init__(self, server: ServerSpec, command: list[str], root: Path,
                 on_diagnostics: Callable[[Path, list[types.Diagnostic]], None] | None = None,
                 on_message: Callable[[str], None] | None = None,
                 on_progress: Callable[[str, str | None], None] | None = None) -> None:
        self.server = server
        self.command = command
        self.root = root
        self.on_diagnostics = on_diagnostics
        self.on_message = on_message
        self.on_progress = on_progress  # (token, title or None when it ends)
        self.working: dict[str, str] = {}  # progress token -> title, while the server works
        self.client = BaseLanguageClient("divide", __version__)
        self.capabilities: types.ServerCapabilities | None = None
        self.versions: dict[Path, int] = {}
        self.texts: dict[Path, str] = {}
        self.ready = False
        self.failed: str | None = None
        self.stderr: list[str] = []
        self._register()

    # ------------------------------------------------------------ lifecycle
    def _register(self) -> None:
        client = self.client

        @client.feature(types.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
        def _diagnostics(params: types.PublishDiagnosticsParams) -> None:
            path = to_fs_path(params.uri)
            if path and self.on_diagnostics is not None:
                self.on_diagnostics(Path(path), list(params.diagnostics))

        @client.feature(types.WINDOW_SHOW_MESSAGE)
        def _show(params: types.ShowMessageParams) -> None:
            if self.on_message is not None and params.type in (types.MessageType.Error, types.MessageType.Warning):
                self.on_message(params.message)

        @client.feature(types.WINDOW_LOG_MESSAGE)
        def _log(params: types.LogMessageParams) -> None:
            pass

        @client.feature(types.WORKSPACE_CONFIGURATION)
        def _configuration(params: types.ConfigurationParams):
            return [None for _ in params.items]

        @client.feature(types.WINDOW_WORK_DONE_PROGRESS_CREATE)
        def _progress_create(params: types.WorkDoneProgressCreateParams) -> None:
            return None

        @client.feature(types.PROGRESS)
        def _progress(params: types.ProgressParams) -> None:
            token, value = str(params.token), params.value
            kind = value.get("kind") if isinstance(value, dict) else getattr(value, "kind", None)
            title = value.get("title") if isinstance(value, dict) else getattr(value, "title", None)
            if kind == "begin":
                self.working[token] = title or self.server.name
                if self.on_progress is not None:
                    self.on_progress(token, self.working[token])
            elif kind == "end" and self.working.pop(token, None) is not None:
                if self.on_progress is not None:
                    self.on_progress(token, None)

        @client.feature(types.CLIENT_REGISTER_CAPABILITY)
        def _register_capability(params: types.RegistrationParams) -> None:
            return None

        @client.feature(types.CLIENT_UNREGISTER_CAPABILITY)
        def _unregister_capability(params: types.UnregistrationParams) -> None:
            return None

        @client.feature(types.WORKSPACE_WORKSPACE_FOLDERS)
        def _folders(params: None):
            return [types.WorkspaceFolder(uri=uri_of(self.root), name=self.root.name or str(self.root))]

        @client.feature(types.WINDOW_SHOW_MESSAGE_REQUEST)
        def _ask(params: types.ShowMessageRequestParams) -> None:
            return None  # divide does not answer the server's questions: as if dismissed

    async def start(self, timeout: float = 30.0) -> bool:
        """Start the server and initialize it; False (and ``failed``) when it does not answer."""
        try:
            await self.client.start_io(*self.command, cwd=str(self.root))
        except OSError as exc:
            self.failed = f"cannot start {self.command[0]}: {exc.strerror or exc}"
            return False
        process = self.client._server
        if process is not None and process.stderr is not None:
            self.client._async_tasks.append(asyncio.create_task(self._drain(process.stderr)))
        params = types.InitializeParams(
            process_id=None,
            root_uri=uri_of(self.root),
            root_path=str(self.root),
            workspace_folders=[types.WorkspaceFolder(uri=uri_of(self.root), name=self.root.name or str(self.root))],
            client_info=types.ClientInfo(name="divide", version=__version__),
            initialization_options=self.server.init_options or None,
            capabilities=types.ClientCapabilities(
                general=types.GeneralClientCapabilities(position_encodings=[types.PositionEncodingKind.Utf16]),
                workspace=types.WorkspaceClientCapabilities(workspace_folders=True, configuration=True),
                window=types.WindowClientCapabilities(work_done_progress=True),
                text_document=types.TextDocumentClientCapabilities(
                    synchronization=types.TextDocumentSyncClientCapabilities(did_save=True),
                    completion=types.CompletionClientCapabilities(
                        completion_item=types.ClientCompletionItemOptions(
                            snippet_support=True,
                            documentation_format=[types.MarkupKind.PlainText, types.MarkupKind.Markdown],
                        ),
                    ),
                    hover=types.HoverClientCapabilities(content_format=[types.MarkupKind.PlainText, types.MarkupKind.Markdown]),
                    definition=types.DefinitionClientCapabilities(link_support=False),
                    publish_diagnostics=types.PublishDiagnosticsClientCapabilities(),
                ),
            ),
        )
        try:
            result = await asyncio.wait_for(self.client.initialize_async(params), timeout)
        except Exception as exc:  # timeout, the server died, a protocol error
            self.failed = self._why(exc)
            await self.stop()
            return False
        self.capabilities = result.capabilities
        self.client.initialized(types.InitializedParams())
        self.ready = True
        return True

    def _why(self, exc: Exception) -> str:
        detail = self.stderr[-1].strip() if self.stderr else ""
        if isinstance(exc, asyncio.TimeoutError):
            return f"{self.server.name} did not answer" + (f": {detail}" if detail else "")
        return f"{self.server.name}: {detail or exc}"

    async def _drain(self, stream: asyncio.StreamReader) -> None:
        """Read the server's stderr (a full pipe would stop it); keep the last lines."""
        while True:
            line = await stream.readline()
            if not line:
                return
            self.stderr.append(line.decode("utf-8", "replace"))
            del self.stderr[:-20]

    @property
    def running(self) -> bool:
        process = self.client._server
        return self.ready and process is not None and process.returncode is None

    async def stop(self) -> None:
        """Shut the server down politely, then make sure it is gone."""
        process = self.client._server
        if self.ready and process is not None and process.returncode is None:
            try:
                await asyncio.wait_for(self.client.shutdown_async(None), 3)
                self.client.exit(None)
            except Exception:
                pass
        self.ready = False
        if process is not None and process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), 2)
            except asyncio.TimeoutError:
                process.kill()
        try:
            await asyncio.wait_for(self.client.stop(), 2)
        except Exception:
            pass

    # ------------------------------------------------------------ documents
    def open(self, path: Path, text: str, language: str) -> None:
        if not self.running:
            return
        if path in self.versions:
            self.change(path, text)
            return
        self.versions[path] = 1
        self.texts[path] = text
        self.client.text_document_did_open(types.DidOpenTextDocumentParams(
            text_document=types.TextDocumentItem(uri=uri_of(path), language_id=language, version=1, text=text)))

    def change(self, path: Path, text: str) -> None:
        if not self.running or path not in self.versions or self.texts.get(path) == text:
            return
        self.versions[path] += 1
        self.texts[path] = text
        self.client.text_document_did_change(types.DidChangeTextDocumentParams(
            text_document=types.VersionedTextDocumentIdentifier(uri=uri_of(path), version=self.versions[path]),
            content_changes=[types.TextDocumentContentChangeWholeDocument(text=text)]))

    def save(self, path: Path) -> None:
        if self.running and path in self.versions:
            self.client.text_document_did_save(types.DidSaveTextDocumentParams(
                text_document=types.TextDocumentIdentifier(uri=uri_of(path)), text=self.texts.get(path)))

    def close(self, path: Path) -> None:
        if self.running and self.versions.pop(path, None) is not None:
            self.texts.pop(path, None)
            self.client.text_document_did_close(types.DidCloseTextDocumentParams(
                text_document=types.TextDocumentIdentifier(uri=uri_of(path))))

    # ------------------------------------------------------------ questions
    def _where(self, path: Path, offset: int) -> types.TextDocumentPositionParams:
        line, character = to_position(self.texts.get(path, ""), offset)
        return types.TextDocumentPositionParams(
            text_document=types.TextDocumentIdentifier(uri=uri_of(path)),
            position=types.Position(line=line, character=character))

    async def completion(self, path: Path, offset: int, trigger: str | None = None,
                         timeout: float = 5.0) -> tuple[list[types.CompletionItem], bool]:
        """``(items, incomplete)`` at ``offset`` of the document as last sent."""
        if not self.running or path not in self.versions:
            return [], False
        where = self._where(path, offset)
        context = (types.CompletionContext(trigger_kind=types.CompletionTriggerKind.TriggerCharacter, trigger_character=trigger)
                   if trigger else types.CompletionContext(trigger_kind=types.CompletionTriggerKind.Invoked))
        params = types.CompletionParams(text_document=where.text_document, position=where.position, context=context)
        try:
            result = await asyncio.wait_for(self.client.text_document_completion_async(params), timeout)
        except Exception:
            return [], False
        if result is None:
            return [], False
        if isinstance(result, types.CompletionList):
            return list(result.items), bool(result.is_incomplete)
        return list(result), False

    async def hover(self, path: Path, offset: int, timeout: float = 5.0) -> types.Hover | None:
        if not self.running or path not in self.versions:
            return None
        where = self._where(path, offset)
        try:
            return await asyncio.wait_for(self.client.text_document_hover_async(
                types.HoverParams(text_document=where.text_document, position=where.position)), timeout)
        except Exception:
            return None

    async def definition(self, path: Path, offset: int, timeout: float = 5.0) -> list[Location]:
        if not self.running or path not in self.versions:
            return []
        where = self._where(path, offset)
        try:
            result = await asyncio.wait_for(self.client.text_document_definition_async(
                types.DefinitionParams(text_document=where.text_document, position=where.position)), timeout)
        except Exception:
            return []
        if result is None:
            return []
        items = result if isinstance(result, (list, tuple)) else [result]
        found: list[Location] = []
        for item in items:
            uri = getattr(item, "uri", None) or getattr(item, "target_uri", None)
            rng = getattr(item, "range", None) or getattr(item, "target_selection_range", None)
            fs = to_fs_path(uri) if uri else None
            if fs and rng is not None:
                found.append(Location(Path(fs), rng.start.line, rng.start.character))
        return found

    @property
    def trigger_characters(self) -> list[str]:
        provider = self.capabilities.completion_provider if self.capabilities else None
        return list(provider.trigger_characters or []) if provider else []


def diagnostics_in(text: str, items: list[types.Diagnostic], source: str) -> list[ServerDiagnostic]:
    """The server's diagnostics as text ranges; hints and information are left out."""
    starts = line_starts(text)
    out: list[ServerDiagnostic] = []
    for d in items:
        severity = d.severity or types.DiagnosticSeverity.Error
        if severity > types.DiagnosticSeverity.Warning:
            continue
        start = to_offset(text, d.range.start.line, d.range.start.character, starts)
        end = to_offset(text, d.range.end.line, d.range.end.character, starts)
        if end <= start:
            end = min(len(text), start + 1)
        label = d.source or source
        out.append(ServerDiagnostic(start, end, "error" if severity == types.DiagnosticSeverity.Error else "warning",
                                    f"{d.message} ({label})"))
    return out
