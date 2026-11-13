"""Language servers in the IDE: which one runs, its documents, its answers.

``LspMixin`` is part of the app. A server starts when the first file of its
language opens (a spinner turns meanwhile) and learns about every change;
its diagnostics join the language's own checker in the editor and the
Messages window, its completions fill the completion list, Ctrl+F1 shows
its hover and Ctrl+Enter goes to its definitions.

``ServersDialog`` is Options > Language servers: automatic, a given server
or none, and the command to run it when it is not in the project or the PATH.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from lsprotocol import types
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.cluster import RadioButtons
from textual_vision.constants import Command
from textual_vision.input_line import InputLine
from textual_vision.label import Label

from divide import config, lsp
from divide.lang.div.complete import CARET, Completion, CompletionResult
from divide.lsp.client import LspSession, diagnostics_in
from divide.ui.dialogs import _Dialog, browse_into, information

CM_LSP_BROWSE = Command.USER + 101

KIND = {k.value: k.name.lower() for k in types.CompletionItemKind}
_WORD = re.compile(r"[A-Za-z0-9_$\\]*$")


def lsp_settings() -> tuple[dict[str, str], dict[str, list[str]]]:
    """``(choice per language, command per server)`` from the config."""
    data = config.load()
    choice = data.get("lsp") if isinstance(data.get("lsp"), dict) else {}
    commands = data.get("lsp_commands") if isinstance(data.get("lsp_commands"), dict) else {}
    return dict(choice), {k: list(v) for k, v in commands.items() if isinstance(v, list) and v}


class LspMixin:
    """Language servers (mixed into the Divide app)."""

    def _lsp_init(self) -> None:
        self._lsp: dict[str, LspSession] = {}  # server name -> session
        self._lsp_starting: dict[str, asyncio.Future] = {}
        self._lsp_failed: dict[str, str] = {}
        self._lsp_timers: dict[int, object] = {}
        self._lsp_completion_gen: dict[int, int] = {}
        self._lsp_progress: dict[tuple[str, str], int] = {}  # (server, token) -> status line busy token

    # ------------------------------------------------------------ which server
    def lsp_server_for(self, language: str) -> tuple[lsp.ServerSpec, list[str]] | None:
        choice, commands = lsp_settings()
        wanted = choice.get(language, lsp.AUTO)
        if wanted == lsp.OFF:
            return None
        candidates = lsp.servers_for(language)
        if wanted != lsp.AUTO:
            candidates = [s for s in candidates if s.name == wanted]
        for server in candidates:
            command = lsp.find_command(server, self.root, commands.get(server.name))  # type: ignore[attr-defined]
            if command is not None:
                return server, command
        return None

    def lsp_session(self, language: str) -> LspSession | None:
        found = self.lsp_server_for(language)
        if found is None:
            return None
        session = self._lsp.get(found[0].name)
        return session if session is not None and session.running else None

    async def lsp_ensure(self, language: str) -> LspSession | None:
        """The running session of the language's server, started if needed."""
        found = self.lsp_server_for(language)
        if found is None:
            return None
        server, command = found
        session = self._lsp.get(server.name)
        if session is not None and session.running:
            return session
        if server.name in self._lsp_failed:
            return None
        pending = self._lsp_starting.get(server.name)
        if pending is not None:
            return await asyncio.shield(pending)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._lsp_starting[server.name] = future
        session = LspSession(server, command, self.root,  # type: ignore[attr-defined]
                             on_diagnostics=self._lsp_diagnostics, on_message=self._lsp_message,
                             on_progress=lambda token, title, name=server.name: self._lsp_progress_changed(name, token, title))
        with self.busy(f"Starting {server.name}…"):  # type: ignore[attr-defined]
            ok = await session.start()
        self._lsp_starting.pop(server.name, None)
        if ok:
            self._lsp[server.name] = session
            self.notify(f"{server.name} is ready", timeout=2)  # type: ignore[attr-defined]
        else:
            self._lsp_failed[server.name] = session.failed or "it did not start"
            self.notify(f"Language server: {self._lsp_failed[server.name]}", severity="warning", timeout=5)  # type: ignore[attr-defined]
            session = None
        future.set_result(session)
        if session is not None:
            for win in self.editor_windows():  # type: ignore[attr-defined]
                if win.editor.lang == language and win.path is not None:
                    session.open(win.path, win.editor.text, language)
        self.update_status()  # type: ignore[attr-defined]
        return session

    async def lsp_stop_all(self) -> None:
        for key in list(self._lsp_progress):
            self._lsp_progress_changed(key[0], key[1], None)
        sessions, self._lsp = list(self._lsp.values()), {}
        self._lsp_failed.clear()
        await asyncio.gather(*(s.stop() for s in sessions), return_exceptions=True)

    # ------------------------------------------------------------ documents
    def lsp_changed(self, ed) -> None:
        """The editor's text changed (or it opened): tell the server soon."""
        if ed.path is None or not lsp.servers_for(ed.lang or ""):
            return
        timer = self._lsp_timers.pop(id(ed), None)
        if timer is not None:
            timer.stop()  # type: ignore[attr-defined]
        self._lsp_timers[id(ed)] = self.set_timer(0.25, lambda: self.lsp_sync(ed))  # type: ignore[attr-defined]

    @work(group="lsp-sync")
    async def lsp_sync(self, ed) -> None:
        self._lsp_timers.pop(id(ed), None)
        if ed.path is None or not ed.is_attached:
            return
        session = await self.lsp_ensure(ed.lang)
        if session is not None:
            session.open(ed.path, ed.text, ed.lang)

    def lsp_saved(self, path: Path, language: str | None) -> None:
        session = self.lsp_session(language or "")
        if session is not None:
            session.save(path)

    def lsp_closed(self, path: Path | None, language: str | None) -> None:
        session = self.lsp_session(language or "") if path is not None else None
        if session is not None:
            session.close(path)  # type: ignore[arg-type]

    def _lsp_diagnostics(self, path: Path, items: list[types.Diagnostic]) -> None:
        win = self.window_for(path)  # type: ignore[attr-defined]
        if win is None:
            return
        session = next((s for s in self._lsp.values() if path in s.versions), None)
        text = session.texts.get(path, win.editor.text) if session else win.editor.text
        if text != win.editor.text:
            return  # about an older text: the server will publish again
        name = session.server.name if session else "server"
        win.editor.set_server_diagnostics(diagnostics_in(text, items, name))
        self.update_status()  # type: ignore[attr-defined]

    def _lsp_progress_changed(self, server: str, token: str, title: str | None) -> None:
        """The server works on its own (indexing…): the spinner says so."""
        status = self.status_line  # type: ignore[attr-defined]
        if not hasattr(status, "start_busy"):
            return
        key = (server, token)
        if title is not None and key not in self._lsp_progress:
            self._lsp_progress[key] = status.start_busy(f"{server}: {title}…")
        elif title is None and key in self._lsp_progress:
            status.stop_busy(self._lsp_progress.pop(key))

    @property
    def lsp_working(self) -> bool:
        """A server is busy with work of its own (indexing)."""
        return bool(self._lsp_progress)

    def _lsp_message(self, message: str) -> None:
        self.notify(message, severity="warning", timeout=4)  # type: ignore[attr-defined]

    # ------------------------------------------------------------ completion
    def lsp_complete(self, view, explicit: bool) -> None:
        """Ask the server for completions at the cursor of ``view``; shown when they come."""
        text = view.text
        offset = view._caret_index()
        if offset is None:
            view.hide_completion()
            return
        session = self.lsp_session(view.lang)
        before = text[max(0, offset - 1):offset]
        prefix = _WORD.search(text[:offset]).group(0)  # type: ignore[union-attr]
        trigger = None
        if session is not None and before and before in session.trigger_characters and before in "$>:\\":
            trigger = before
        if not explicit and not trigger and not re.fullmatch(r"[A-Za-z_]\w*", prefix.lstrip("$\\")):
            view.hide_completion()
            return
        gen = self._lsp_completion_gen[id(view)] = self._lsp_completion_gen.get(id(view), 0) + 1
        self._lsp_completion(view, text, offset, prefix, trigger, explicit, gen)

    @work(group="lsp-completion")
    async def _lsp_completion(self, view, text: str, offset: int, prefix: str, trigger: str | None, explicit: bool, gen: int) -> None:
        session = await self.lsp_ensure(view.lang)
        if session is None or view.path is None:
            if explicit and session is None:
                self.notify(self.lsp_status(view.lang), timeout=3)  # type: ignore[attr-defined]
            return
        session.open(view.path, text, view.lang)  # the text the cursor is in
        items, _ = await session.completion(view.path, offset, trigger)
        if self._lsp_completion_gen.get(id(view)) != gen or view.text != text or view._caret_index() != offset:
            return  # typed meanwhile: a newer question is on its way
        view.show_completion(completion_result(text, offset, prefix, items), explicit)

    # ------------------------------------------------------------ hover, definition
    async def lsp_hover(self, ed) -> bool:
        """Ctrl+F1 in a file with a server: what the server knows about the word."""
        session = await self.lsp_ensure(ed.lang)
        if session is None or ed.path is None:
            return False
        session.open(ed.path, ed.text, ed.lang)
        offset = ed.document.get_index_from_location(ed.selection.end)
        with self.busy(f"Asking {session.server.name}…"):  # type: ignore[attr-defined]
            hover = await session.hover(ed.path, offset)
        text = clean_hover(lsp.plain_markup(hover.contents) if hover else "")
        word = _WORD.search(ed.text[:offset]).group(0) + re.match(r"\w*", ed.text[offset:]).group(0)  # type: ignore[union-attr]
        if not text:
            self.notify(f"{session.server.name} knows nothing about {word or 'this'}", timeout=2)  # type: ignore[attr-defined]
            return True
        await self.run_dialog(information(word or session.server.name, text))  # type: ignore[attr-defined]
        return True

    async def lsp_definition(self, win) -> bool:
        """Ctrl+Enter on a symbol: where the server says it is defined."""
        ed = win.editor
        session = await self.lsp_ensure(ed.lang)
        if session is None or win.path is None:
            return False
        session.open(win.path, ed.text, ed.lang)
        offset = ed.document.get_index_from_location(ed.selection.end)
        with self.busy(f"Asking {session.server.name}…"):  # type: ignore[attr-defined]
            found = await session.definition(win.path, offset)
        if not found:
            self.notify(f"{session.server.name} does not know where this is defined", timeout=2)  # type: ignore[attr-defined]
            return True
        text = ed.text
        word = (re.search(r"[\w$]*$", text[:offset]).group(0) + re.match(r"\w*", text[offset:]).group(0)).lstrip("$")  # type: ignore[union-attr]
        place = found[0]
        target = self.window_for(place.path) or self.open_file(place.path)  # type: ignore[attr-defined]
        if target is None:
            return True
        text = target.editor.text
        start = lsp.to_offset(text, place.line, place.character)
        # the place may be the whole declaration ("class Shop {"): select the name in it
        line_end = text.find("\n", start)
        line = text[start:line_end if line_end >= 0 else len(text)]
        m = re.search(rf"(?<![\w$]){re.escape(word)}(?!\w)", line) if word else None
        if m is not None:
            self._select_in(target, start + m.start(), start + m.end())  # type: ignore[attr-defined]
        else:
            self._select_in(target, start)  # type: ignore[attr-defined]
        return True

    def lsp_status(self, language: str) -> str:
        """For the status line and messages: which server, or why none."""
        found = self.lsp_server_for(language)
        if found is None:
            choice, _ = lsp_settings()
            if choice.get(language) == lsp.OFF:
                return "no language server (Options > Language servers)"
            names = " or ".join(s.name for s in lsp.servers_for(language))
            return f"no language server: install {names}, or set one in Options > Language servers"
        server = found[0]
        if server.name in self._lsp_failed:
            return f"{server.name} failed: {self._lsp_failed[server.name]}"
        session = self._lsp.get(server.name)
        if session is not None and session.running:
            return server.name
        return f"{server.name} starting…" if server.name in self._lsp_starting else server.name

    async def choose_servers(self, language: str = "php") -> None:
        dialog = ServersDialog(language, self.root)  # type: ignore[attr-defined]
        if await self.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        data = config.load()
        choice = data.get("lsp") if isinstance(data.get("lsp"), dict) else {}
        commands = data.get("lsp_commands") if isinstance(data.get("lsp_commands"), dict) else {}
        choice[language] = dialog.choice
        if dialog.choice not in (lsp.AUTO, lsp.OFF):
            if dialog.command:
                commands[dialog.choice] = dialog.command
            else:
                commands.pop(dialog.choice, None)
        data["lsp"], data["lsp_commands"] = choice, commands
        config.save(data)
        await self.lsp_stop_all()
        for win in self.editor_windows():  # type: ignore[attr-defined]
            win.editor.set_server_diagnostics([])
            if win.editor.lang == language:
                self.lsp_changed(win.editor)
        self.update_status()  # type: ignore[attr-defined]


def clean_hover(text: str) -> str:
    """Markdown fences and PHP open tags out of a hover, blank runs squeezed."""
    text = re.sub(r"```\w*\n?", "", text)
    text = re.sub(r"<\?php\s*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def completion_result(text: str, offset: int, prefix: str, items: list[types.CompletionItem]) -> CompletionResult:
    """The server's items as divide's completion list, filtered by what is typed."""
    start = offset - len(prefix)
    key = prefix.lstrip("\\").lower()
    out: list[tuple[str, Completion]] = []
    for item in items:
        insert = item.insert_text or item.label
        edit = item.text_edit
        if edit is not None:
            insert = edit.new_text
            rng = getattr(edit, "range", None) or getattr(edit, "insert", None)
            if rng is not None:
                edit_start = lsp.to_offset(text, rng.start.line, rng.start.character)
                if edit_start < start:  # the server replaces more than the word: keep it
                    insert = insert[start - edit_start:] if text[edit_start:start] == insert[:start - edit_start] else insert
        if item.insert_text_format == types.InsertTextFormat.Snippet:
            insert = lsp.from_snippet(insert, CARET)
        name = (item.filter_text or item.label).lower()
        if key and not (name.startswith(key) or name.lstrip("$").startswith(key.lstrip("$"))):
            continue
        detail = item.detail or KIND.get(item.kind or 0, "")
        detail = " ".join(detail.split())[:40]
        out.append((item.sort_text or item.label, Completion(item.label, insert, detail)))
    out.sort(key=lambda pair: pair[0])
    return CompletionResult(start, prefix, [c for _, c in out[:200]], context="lsp")


class ServersDialog(_Dialog):
    """Options > Language servers: which server runs for a language."""

    DEFAULT_CSS = """
    ServersDialog { width: 70; height: 19; }
    ServersDialog InputLine { width: 1fr; }
    ServersDialog Cluster { width: 1fr; margin-bottom: 1; }
    ServersDialog .dlg-hint { color: $text-muted; background: $surface; height: auto; }
    """

    def __init__(self, language: str, root: Path) -> None:
        super().__init__(title="Language servers")
        self.language = language
        self.root = root
        self.servers = lsp.servers_for(language)
        choice, commands = lsp_settings()
        self.commands = commands
        names = [lsp.AUTO] + [s.name for s in self.servers] + [lsp.OFF]
        labels = ["~A~utomatic: the first one found"] + [f"~{s.name[0]}~{s.name[1:]}" for s in self.servers] + ["~N~one"]
        self.names = names
        self.radio = RadioButtons(labels)
        current = choice.get(language, lsp.AUTO)
        self.radio.value = 1 << (names.index(current) if current in names else 0)
        self.input = InputLine(max_len=1024)
        chosen = names[self._index()]
        self.input.data = " ".join(commands.get(chosen, []))
        self.choice = current
        self.command: list[str] = []

    def _index(self) -> int:
        value = self.radio.value
        return max(0, value.bit_length() - 1)

    def _found(self) -> str:
        parts = []
        for server in self.servers:
            command = lsp.find_command(server, self.root, self.commands.get(server.name))
            parts.append(f"{server.name}: {command[0] if command else 'not found'}")
        return "\n".join(parts)

    def compose_content(self) -> ComposeResult:
        yield Label(f"Server for {self.language.upper()} files", link=self.radio)
        yield self.radio
        yield Label("~C~ommand of the server chosen (empty: the project's or the PATH's)", link=self.input)
        yield self.input
        yield Static(self._found(), classes="dlg-hint", markup=False)
        with Horizontal(classes="dlg-buttons"):
            yield Button("O~K~", Command.OK, is_default=True, id="ok")
            yield Button("~B~rowse...", CM_LSP_BROWSE, id="browse")
            yield Button("Cancel", Command.CANCEL, id="cancel")

    def on_command_message(self, message) -> None:
        if message.command == CM_LSP_BROWSE:
            message.stop()
            message.prevent_default()
            self.run_worker(browse_into(self, self.input, "Language server: browse", "*", self.root), exclusive=True)

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        self.choice = self.names[self._index()]
        self.command = self.input.data.split()
        return True
