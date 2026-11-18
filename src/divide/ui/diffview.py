"""A diff as a code review shows it: unified, or side by side.

``DiffView`` reads git's diff (``divide.run.git.parse_diff``) and draws it
itself: each file under a bar with its path and ``+N −M``; each hunk under a
row with where it starts and the function it is in; each line after its old
and new numbers, with the whole row on red (removed), green (added) or the
editor's colour (unchanged), and inside a changed line the words that changed
in a stronger shade. Side by side, the old file is at the left and the new one
at the right, a removed line next to the added line that replaced it.

A bar goes over the rows (Up, Down, PgUp, PgDn, Home, End; Left and Right
scroll sideways): Enter asks to open the file at that line (``LineChosen``),
N and P go to the next and the previous hunk, S changes between unified and
side by side (remembered in the settings).
"""

from __future__ import annotations

from divide.i18n import _

from dataclasses import dataclass

from rich.cells import cell_len
from rich.segment import Segment
from rich.style import Style
from textual.binding import Binding
from textual.geometry import Size
from textual.message import Message
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual_vision.constants import OptionFlag
from textual_vision.group import TVViewMixin

from divide import config, themes
from divide.run import git

SETTING = "git_diff_side_by_side"
TAB = 4
SYNTAX_LINES = 20000  # a longer diff is shown without syntax colours (they take a moment per file)


def syntax_of(path: str, text: str) -> list[list[tuple[int, int, str]]]:
    """The editor's colours for ``text`` as a file at ``path``: per line, (start, end, token kind)
    by character. A hidden editor colours it, so every language comes out as it does in the editor."""
    from pathlib import Path

    from divide.ui.windows import EditorView

    editor = EditorView(text, path=Path(path), read_only=True)
    if editor.lang is None:
        return []
    editor._build_highlight_map()
    out: list[list[tuple[int, int, str]]] = []
    for row, line in enumerate(text.split("\n")):
        spans = []
        for start, end, kind in editor._highlights.get(row, []):
            if line.isascii():
                a, b = start, len(line) if end is None else end
            else:  # the editor counts bytes
                raw = line.encode("utf-8")
                a = len(raw[:start].decode("utf-8", "ignore"))
                b = len(line) if end is None else len(raw[:end].decode("utf-8", "ignore"))
            if b > a:
                spans.append((a, b, kind))
        out.append(spans)
    return out


@dataclass(frozen=True)
class Row:
    """What a row of the view shows."""

    kind: str  # text, file, hunk, line, pair, note, conflict
    text: str = ""
    style: str = ""  # text and conflict rows: meta, mod, add or ""
    file: git.DiffFile | None = None
    hunk: git.Hunk | None = None
    left: git.DiffLine | None = None  # line: the line; pair: the old side
    right: git.DiffLine | None = None  # pair: the new side
    left_spans: tuple = ()
    right_spans: tuple = ()
    left_syntax: tuple = ()  # (start, end, token kind): the editor's colours of the line
    right_syntax: tuple = ()


def _spans_for(hunk: git.Hunk) -> dict[int, tuple]:
    """The changed words of each removed or added line that has a partner (by id of the line)."""
    out: dict[int, tuple] = {}
    for old, new in git.pairs(hunk):
        if old is not None and new is not None and old.kind == "-" and new.kind == "+":
            a, b = git.changed_spans(old.text, new.text)
            if len(old.text) and sum(e - s for s, e in a) > 0.6 * len(old.text):
                a = []  # nearly all of it changed: no words to point at
            if len(new.text) and sum(e - s for s, e in b) > 0.6 * len(new.text):
                b = []
            out[id(old)] = tuple(a)
            out[id(new)] = tuple(b)
    return out


class DiffView(ScrollView, TVViewMixin, can_focus=True):
    """A diff, unified or side by side, with a bar over its rows."""

    BINDINGS = [
        Binding("up", "move(-1)", show=False),
        Binding("down", "move(1)", show=False),
        Binding("pageup", "page(-1)", show=False),
        Binding("pagedown", "page(1)", show=False),
        Binding("home,ctrl+home", "edge(0)", show=False),
        Binding("end,ctrl+end", "edge(1)", show=False),
        Binding("left", "sideways(-8)", show=False),
        Binding("right", "sideways(8)", show=False),
        Binding("enter", "choose", show=False),
        Binding("n", "jump(1)", show=False),
        Binding("p", "jump(-1)", show=False),
        Binding("s", "toggle", show=False),
    ]
    DEFAULT_CSS = """
    DiffView { width: 1fr; height: 1fr; scrollbar-size: 1 1; }
    """

    class LineChosen(Message):
        """Enter on a line: open ``path`` at ``line`` (1-based, in the new file when it has one)."""

        def __init__(self, view: "DiffView", path: str, line: int) -> None:
            super().__init__()
            self.view = view
            self.path = path
            self.line = line

    def __init__(self) -> None:
        super().__init__()
        self.tv_options = OptionFlag.SELECTABLE
        self.text = ""
        self.diff = git.Diff([], [])
        self.conflict = False
        self.message: list[str] | None = None
        self.rows: list[Row] = []
        self.cursor = 0
        self.side_by_side = bool(config.load().get(SETTING, False))
        self.path = ""  # a conflict's file (its colours)
        self._syntax: dict[int, tuple] = {}  # id of a DiffLine -> its colours

    def on_mount(self) -> None:
        self.app.theme_changed_signal.subscribe(self, lambda _theme: self.refresh())

    # ------------------------------------------------------------ content
    def show(self, text: str, conflict: bool = False, path: str = "") -> None:
        """A diff (git's text); with ``conflict``, a file in conflict (git's markers, our side, theirs),
        ``path`` the file (for its colours)."""
        if text == self.text and conflict == self.conflict and self.message is None:
            return
        self.text, self.conflict, self.message, self.path = text, conflict, None, path
        self.diff = git.Diff([], []) if conflict else git.parse_diff(text)
        self._syntax = self._colour(self.diff)
        if not conflict and not self.diff.files and not any(line.strip() for line in self.diff.preamble):
            self.message = git.lines(text)
        self._build(keep=False)

    def show_message(self, text: str) -> None:
        """Plain text where the diff goes (what an area holds, why there is nothing)."""
        self.text, self.conflict, self.message = text, False, git.lines(text)
        self.diff = git.Diff([], [])
        self._build(keep=False)

    @staticmethod
    def _colour(diff: git.Diff) -> dict[int, tuple]:
        """Each line's syntax colours: the old side (context and removed lines) and the new side
        (context and added ones) of every file, coloured as a whole by the editor."""
        out: dict[int, tuple] = {}
        total = 0
        for f in diff.files:
            total += sum(len(h.lines) for h in f.hunks)
            if total > SYNTAX_LINES or f.status == "binary" or not f.hunks:
                continue
            for side in ("-", "+"):
                lines = [line for h in f.hunks for line in h.lines if line.kind in (" ", side)]
                if not any(line.kind == side for line in lines) and side == "-":
                    continue
                try:
                    colours = syntax_of(f.path, "\n".join(line.text for line in lines))
                except Exception:  # a grammar that fails on a piece of a file: no colours, the diff stays
                    colours = []
                for line, spans in zip(lines, colours):
                    if line.kind == side or side == "+":
                        out[id(line)] = tuple(spans)
        return out

    def _build(self, keep: bool = True) -> None:
        here = self.rows[self.cursor] if keep and 0 <= self.cursor < len(self.rows) else None
        rows: list[Row] = []
        if self.message is not None:
            rows = [Row("text", line) for line in self.message]
        elif self.conflict:
            try:
                colours = syntax_of(self.path, self.text) if self.path else []
            except Exception:
                colours = []
            for i, (line, kind) in enumerate(zip(git.lines(self.text), git.conflict_kinds(self.text))):
                syntax = tuple(colours[i]) if i < len(colours) and kind != "meta" else ()
                rows.append(Row("conflict", line, kind, left_syntax=syntax))
        else:
            for line in self.diff.preamble:
                meta = line.startswith(("commit ", "Author", "Commit", "Date", "Merge:"))
                rows.append(Row("text", line.expandtabs(TAB), "meta" if meta else ""))
            for f in self.diff.files:
                rows.append(Row("file", file=f))
                if f.status == "binary":
                    rows.append(Row("note", _("Binary file: not shown")))
                elif not f.hunks:
                    rows.append(Row("note", {"renamed": _("Renamed, its content unchanged"),
                                             "mode": _("Only its mode changed")}.get(f.status, _("No changes in its text"))))
                for h in f.hunks:
                    rows.append(Row("hunk", file=f, hunk=h))
                    spans = _spans_for(h)
                    if self.side_by_side:
                        for old, new in git.pairs(h):
                            rows.append(Row("pair", file=f, hunk=h, left=old, right=new,
                                            left_spans=spans.get(id(old), ()) if old is not None else (),
                                            right_spans=spans.get(id(new), ()) if new is not None else (),
                                            left_syntax=self._syntax.get(id(old), ()) if old is not None else (),
                                            right_syntax=self._syntax.get(id(new), ()) if new is not None else ()))
                        notes = [line for line in h.lines if line.kind == "\\"]
                        rows += [Row("note", n.text) for n in notes[:1]]
                    else:
                        for line in h.lines:
                            if line.kind == "\\":
                                rows.append(Row("note", line.text))
                            else:
                                rows.append(Row("line", file=f, hunk=h, left=line, left_spans=spans.get(id(line), ()),
                                                left_syntax=self._syntax.get(id(line), ())))
        self.rows = rows
        self.cursor = self._first_line()
        if here is not None:  # the same place, in the other layout
            target = here.left or here.right
            for i, row in enumerate(rows):
                if target is not None and (row.left is target or row.right is target):
                    self.cursor = i
                    break
        self.virtual_size = Size(self._content_width(), len(rows))
        if not keep:
            self.scroll_to(0, 0, animate=False)
        self._reveal()
        self.refresh()

    def _first_line(self) -> int:
        return next((i for i, r in enumerate(self.rows) if r.kind in ("line", "pair")), 0)

    def _content_width(self) -> int:
        longest = max((cell_len(r.left.text if r.left else r.right.text if r.right else r.text) for r in self.rows), default=0)
        return longest + self._gutter() * 2 + 4

    def rows_text(self) -> list[str]:
        """The rows as they read (for tests and copying): unified or side by side."""
        return [Strip(self._row_segments(i, 200)).text.rstrip() for i in range(len(self.rows))]

    # ------------------------------------------------------------ drawing
    def _digits(self) -> int:
        top = 1
        for f in self.diff.files:
            for h in f.hunks:
                top = max(top, h.old_start + len(h.lines), h.new_start + len(h.lines))
        return len(str(top))

    def _gutter(self) -> int:
        return self._digits() + 1

    def render_line(self, y: int) -> Strip:
        index = y + int(self.scroll_offset.y)
        width = self.size.width
        palette = themes.current()
        if not 0 <= index < len(self.rows):
            return Strip([Segment(" " * width, palette.style("editor-text", "editor-bg"))], width)
        return Strip(self._row_segments(index, width), width).crop(0, width)

    def _row_segments(self, index: int, width: int) -> list[Segment]:
        palette = themes.current()
        row = self.rows[index]
        base = palette.style("editor-text", "editor-bg")
        x = int(self.scroll_offset.x)
        on_bar = index == self.cursor and self.has_focus
        if row.kind == "file":
            f = row.file
            assert f is not None
            mark = {"added": "A", "deleted": "D", "renamed": "R", "binary": "B", "mode": "T"}.get(f.status, "M")
            name = f"{f.old_path} -> {f.new_path}" if f.status == "renamed" else f.path
            counts = f"  +{f.added} -{f.removed}" if f.hunks else ""
            style = palette.style("diff-file", "diff-file-bg", bold=True)
            return self._fill([Segment(f" {mark} {name}{counts}", style)], width, style)
        if row.kind == "hunk":
            h = row.hunk
            assert h is not None
            text = f"@@ -{h.old_start} +{h.new_start} @@ {h.header}".rstrip()
            style = palette.style("diff-hunk", "editor-bg")
            gutter = self._gutter() * (1 if self.side_by_side else 2)
            return self._fill([Segment(" " * gutter, base), Segment(text, style)], width, base)
        if row.kind in ("text", "note"):
            style = palette.style("diff-meta", "editor-bg", bold=True) if row.style == "meta" else base
            if row.kind == "note":
                style = palette.style("editor-gutter", "editor-bg", italic=True)
                return self._fill([Segment(" " * (self._gutter() * 2) + row.text, style)], width, base)
            return self._fill(self._code(row.text, (), style, style, x), width, base)
        if row.kind == "conflict":
            colour = {"meta": "diff-file-bg", "mod": "diff-mod-line", "add": "diff-add-line"}.get(row.style)
            style = palette.style("diff-text" if colour else "editor-text", colour or "editor-bg",
                                  bold=row.style == "meta")
            gutter = Segment(f"{index + 1:>{self._digits()}} ", self._gutter_style(style, on_bar))
            return self._fill([gutter, *self._code(row.text, (), style, style, x, row.left_syntax)], width, style)
        if row.kind == "line":
            return self._fill(self._side(row.left, row.left_spans, x, both=True, on_bar=on_bar,
                                         syntax=row.left_syntax), width, self._line_style(row.left))
        # side by side
        half = max(10, (width - 1) // 2)
        left = self._fill(self._side(row.left, row.left_spans, x, both=False, on_bar=on_bar, old=True,
                                     syntax=row.left_syntax), half,
                          self._line_style(row.left, empty=True), hatch=row.left is None)
        right = self._fill(self._side(row.right, row.right_spans, x, both=False, on_bar=on_bar, old=False,
                                      syntax=row.right_syntax),
                           width - half - 1, self._line_style(row.right, empty=True), hatch=row.right is None)
        return [*left, Segment("│", palette.style("editor-gutter", "editor-bg")), *right]

    def _line_style(self, line: git.DiffLine | None, empty: bool = False) -> Style:
        palette = themes.current()
        if line is None:
            return palette.style("editor-gutter", "editor-bg") if empty else palette.style("editor-text", "editor-bg")
        if line.kind == "+":
            return palette.style("diff-text", "diff-add-line")
        if line.kind == "-":
            return palette.style("diff-text", "diff-del-line")
        return palette.style("editor-text", "editor-bg")

    def _gutter_style(self, row_style: Style, on_bar: bool) -> Style:
        palette = themes.current()
        if on_bar:
            return palette.style("editor-selection", "editor-selection-bg")
        return Style(color=palette.colour("editor-gutter"), bgcolor=row_style.bgcolor)

    def _side(self, line: git.DiffLine | None, spans: tuple, x: int, *, both: bool, on_bar: bool,
              old: bool = True, syntax: tuple = ()) -> list[Segment]:
        palette = themes.current()
        digits = self._digits()
        if line is None:  # nothing on this side: hatched, as far as the side goes (``_fill``)
            style = palette.style("editor-gutter", "editor-bg")
            bar = self._gutter_style(style, on_bar)
            return [Segment(" " * (digits + 1), bar)]
        style = self._line_style(line)
        word = palette.style("diff-text", "diff-add-word" if line.kind == "+" else "diff-del-word", bold=True)
        gutter = self._gutter_style(style, on_bar)
        if both:
            numbers = f"{line.old if line.old is not None else '':>{digits}} {line.new if line.new is not None else '':>{digits}} "
        else:
            number = line.old if old else line.new
            numbers = f"{number if number is not None else '':>{digits}} "
        sign = {"+": "+", "-": "-"}.get(line.kind, " ")
        return [Segment(numbers, gutter), Segment(sign + " ", style),
                *self._code(line.text, spans, style, word, x, syntax)]

    @staticmethod
    def _code(text: str, spans: tuple, style: Style, word: Style, x: int, syntax: tuple = ()) -> list[Segment]:
        """``text`` from column ``x`` on: the row's colours, the syntax's on them (their foreground),
        the changed ``spans`` in ``word``; tabs to the next stop of ``TAB``."""
        styles = [style] * len(text)
        if syntax:
            tokens = themes.current().token_styles()
            for start, end, kind in syntax:
                token = tokens.get(kind)
                if token is None:
                    continue
                fg = Style(color=token.color, bold=token.bold, italic=token.italic, underline=token.underline)
                for i in range(max(0, start), min(end, len(text))):
                    styles[i] = style + fg
        for start, end in spans:
            for i in range(max(0, start), min(end, len(text))):
                styles[i] = word
        segments: list[Segment] = []
        column = 0
        run, run_style = [], None
        for ch, st in zip(text, styles):
            piece = " " * (TAB - column % TAB) if ch == "\t" else ch
            column += len(piece)
            if st != run_style and run:
                segments.append(Segment("".join(run), run_style))
                run = []
            run.append(piece)
            run_style = st
        if run:
            segments.append(Segment("".join(run), run_style))
        if x <= 0:
            return segments
        strip = Strip(segments)
        return list(strip.crop(x, max(x, strip.cell_length)))

    @staticmethod
    def _fill(segments: list[Segment], width: int, style: Style, hatch: bool = False) -> list[Segment]:
        used = sum(cell_len(s.text) for s in segments)
        if used < width:
            return [*segments, Segment(("░" if hatch else " ") * (width - used), style)]
        return list(Strip(segments).crop(0, width))

    # ------------------------------------------------------------ the bar
    def _reveal(self) -> None:
        height = max(1, self.scrollable_content_region.height)
        top = int(self.scroll_offset.y)
        if self.cursor < top:
            self.scroll_to(y=self.cursor, animate=False)
        elif self.cursor >= top + height:
            self.scroll_to(y=self.cursor - height + 1, animate=False)

    def _set_cursor(self, index: int) -> None:
        if not self.rows:
            return
        self.cursor = max(0, min(len(self.rows) - 1, index))
        self._reveal()
        self.refresh()

    def action_move(self, by: int) -> None:
        self._set_cursor(self.cursor + by)

    def action_page(self, by: int) -> None:
        self._set_cursor(self.cursor + by * max(1, self.scrollable_content_region.height - 1))

    def action_edge(self, end: int) -> None:
        self._set_cursor(len(self.rows) - 1 if end else 0)

    def action_sideways(self, by: int) -> None:
        self.scroll_to(x=max(0, self.scroll_offset.x + by), animate=False)

    def action_jump(self, direction: int) -> None:
        """To the next (or previous) hunk's first line."""
        starts = [i + 1 for i, r in enumerate(self.rows) if r.kind == "hunk" and i + 1 < len(self.rows)]
        if direction > 0:
            target = next((i for i in starts if i > self.cursor), None)
        else:
            target = next((i for i in reversed(starts) if i < self.cursor - 1), None)
        if target is not None:
            self._set_cursor(target)
            self.scroll_to(y=max(0, target - 3), animate=False)

    def action_toggle(self) -> None:
        if self.message is not None or self.conflict:
            return
        self.side_by_side = not self.side_by_side
        config.set_value(SETTING, self.side_by_side)
        self._build()

    def action_choose(self) -> None:
        if not 0 <= self.cursor < len(self.rows):
            return
        row = self.rows[self.cursor]
        f = row.file
        if f is None or f.status in ("deleted", "binary"):
            return
        line = (row.right or row.left) if row.kind == "pair" else row.left
        number = None
        if line is not None:
            number = line.new if line.new is not None else line.old
        elif row.hunk is not None:
            number = row.hunk.new_start
        self.post_message(self.LineChosen(self, f.path, max(1, number or 1)))

    def on_focus(self) -> None:
        self.refresh()

    def on_blur(self) -> None:
        self.refresh()

    def on_click(self, event) -> None:
        index = event.y + int(self.scroll_offset.y)
        if 0 <= index < len(self.rows):
            self._set_cursor(index)
            if event.chain >= 2:
                self.action_choose()
