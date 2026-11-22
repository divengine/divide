"""The Flow Designer: a Runner Flow drawn as a board of lanes and cards, edited from the keyboard.

The board (:mod:`divide.ui.flowlayout`) shows the Flow's Blocks as ordered
lanes, the first one marked ENTRY, their Steps as ordered cards, and every
``call`` (single line) and ``jump`` (double line) as a connection from the
card's port to its target. Like the Flow window it never owns the Flow: it
draws the code editor's buffer, and each change is one edit of that buffer
(:mod:`divide.run.flowedit`), verified by reading it back, undone by one
Ctrl+Z. While the YAML does not parse the board keeps the last design that
did, read-only, and says so.

Keys on the board (the help's Flow Designer page lists them):

- arrows: Step to Step in a lane (Up from the first, the lane's title), lane to lane;
  Home/End: the lane's title, its last Step; PgUp/PgDn scroll;
- Tab / Shift+Tab: the selected item's connections, one by one (those it has,
  then those leading to it); Enter on one goes to its other end; Backspace goes back;
- Enter edits (a Step: its id and attributes; a lane: the Block's id and
  description); Ins adds a Step, B a Block; Del deletes;
- C and J connect: choose the target on the board, Enter sets it, Del removes it, Esc cancels;
- Ctrl+Up/Down moves a Step in its Block, Ctrl+Left/Right moves the Block (Alt too);
- Ctrl+D the Flow window's tree, Ctrl+T the code, Alt+F9 checks, Ctrl+F9 runs, F2 saves.
"""

from __future__ import annotations

from divide.i18n import _

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.color import Color
from textual.geometry import Region, Size
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.widgets import Static
from textual_vision.button import Button
from textual_vision.constants import Command, OptionFlag
from textual_vision.group import TVViewMixin
from textual_vision.input_line import InputLine
from textual_vision.label import Label

from divide import themes
from divide.run import flowedit as fe
from divide.run import flowmodel as fm
from divide.ui.dialogs import _Dialog, confirm, information
from divide.ui.flowlayout import Board, Connection, Overlay
from divide.ui.flowmodel import FlowView, Key, StepDialog
from divide.ui.history import HistoryInput
from divide.ui.windows import EditorWindow, HRule, VRule

NARROW = 100  # below this many columns the inspector goes under the board


def card_width(columns: int) -> int:
    """Cards as wide as the board allows: 80 columns show two lanes, 160 four or five."""
    if columns < 70:
        return 20
    if columns < 110:
        return 22
    if columns < 150:
        return 24
    return 28


def board_styles() -> dict[str, Style]:
    """The board's styles from the theme: hue where the theme has it, and what does not need it
    (reverse video for the selection, bold for emphasis, the glyphs themselves) everywhere."""
    t = themes.current().token_styles()

    def tok(name: str, fallback: str = "") -> Style:
        """A syntax colour without its background: the board's surfaces are under it."""
        st = t.get(name) or (t.get(fallback) if fallback else None) or Style()
        return Style(color=st.color, bold=st.bold, italic=st.italic, underline=st.underline)

    out = {
        "": Style(), "text": Style(), "border": Style(), "rule": tok("div.comment"), "dim": tok("div.comment"),
        "id": tok("json.key") + Style(bold=True), "kw": tok("ts.keyword", "php.keyword"),
        # each row of a card in its own colour (bold: still told apart where the theme has one hue)
        "kw.condition": tok("ts.operator", "php.operator") + Style(bold=True),
        "kw.context": tok("php.variable", "div.var") + Style(bold=True),
        "kw.call": tok("ts.string", "json.string") + Style(bold=True),
        "kw.activity": tok("div.keyword", "php.keyword") + Style(bold=True),
        "kw.jump": tok("php.tag", "div.special") + Style(bold=True),
        "kw.pause": tok("ts.number", "json.number") + Style(bold=True),
        "title": Style(bold=True), "entry": Style(reverse=True, bold=True), "frame": Style(bold=True),
        "error": tok("diag.error"), "warning": tok("diag.warning"), "port": Style(bold=True),
        "call": tok("ts.string", "json.string"), "jump": tok("php.tag", "div.special"),
        "hot": Style(bold=True), "chosen": Style(reverse=True, bold=True), "mark": Style(bold=True, reverse=True),
        "taken": Style(bold=True, underline=True),
    }
    for name in list(out):  # the selection: the text reversed, its colours left out (bold kept)
        out["sel:" + name] = Style(reverse=True, bold=out[name].bold)
    return out


class FlowBoard(ScrollView, TVViewMixin, can_focus=True):
    """The board's cells, scrolled, with the selection kept in view."""

    DEFAULT_CSS = """
    FlowBoard {
        background: $window-content-background;
        color: $foreground;
        scrollbar-size: 1 1;
        scrollbar-background: $secondary;
        scrollbar-color: $background;
        scrollbar-corner-color: $secondary;
        width: 1fr;
        height: 1fr;
    }
    """
    BINDINGS = [
        Binding("up", "move(0, -1)", "Up", show=False),
        Binding("down", "move(0, 1)", "Down", show=False),
        Binding("left", "move(-1, 0)", "Left", show=False),
        Binding("right", "move(1, 0)", "Right", show=False),
        Binding("home", "edge(-1)", "Title", show=False),
        Binding("end", "edge(1)", "Last", show=False),
        Binding("pageup", "page(-1)", "Page up", show=False),
        Binding("pagedown", "page(1)", "Page down", show=False),
        Binding("enter", "enter", "Edit", show=False),
        Binding("backspace", "back", "Back", show=False),
        Binding("insert", "add_step", "Add Step", show=False),
        Binding("b", "add_block", "Add Block", show=False),
        Binding("delete", "delete", "Delete", show=False),
        Binding("c", "connect('call')", "Call", show=False),
        Binding("j", "connect('jump')", "Jump", show=False),
        Binding("x", "context", "Context", show=False),
        Binding("ctrl+up,alt+up", "reorder(0, -1)", "Step up", show=False),
        Binding("ctrl+down,alt+down", "reorder(0, 1)", "Step down", show=False),
        Binding("ctrl+left,alt+left", "reorder(-1, 0)", "Block left", show=False),
        Binding("ctrl+right,alt+right", "reorder(1, 0)", "Block right", show=False),
        Binding("ctrl+z", "undo", "Undo", show=False),
        Binding("ctrl+y", "redo", "Redo", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.tv_options = OptionFlag.SELECTABLE
        self.board: Board | None = None
        self._strips: list[Strip] = []

    def _window(self) -> "FlowDesignWindow":
        return next(a for a in self.ancestors if isinstance(a, FlowDesignWindow))

    def show(self, board: Board, selected: Key | None, connection: Connection | None, overlay: Overlay | None = None) -> None:
        self.board = board
        styles = board_styles()
        base = self.rich_style
        surfaces = self.surfaces()
        strips = []
        for row, fills in zip(board.paint(selected, connection, overlay), board.fill):
            segments, run, style = [], [], None
            for (ch, name), fill in zip(row, fills):
                if (name, fill) != style and run:
                    segments.append(Segment("".join(run), base + surfaces[style[1]] + styles.get(style[0] or "", Style())))
                    run = []
                style = (name, fill)
                run.append(ch)
            if run:
                segments.append(Segment("".join(run), base + surfaces[style[1]] + styles.get(style[0] or "", Style())))
            strips.append(Strip(segments, board.width))
        self._strips = strips
        filler, run_start = [], 0
        fills = board.filler()
        for x in range(1, len(fills) + 1):  # the columns carry on below the board, to the window's bottom
            if x == len(fills) or fills[x] != fills[run_start]:
                filler.append(Segment(" " * (x - run_start), base + surfaces[fills[run_start]]))
                run_start = x
        self._filler = Strip(filler, board.width)
        self.virtual_size = Size(board.width, board.height)
        self.refresh()
        box = board.boxes.get(selected) if selected is not None else None
        if box is not None:
            region = Region(max(0, box.x - 2), box.y - 1, box.w + 6, box.h + 2)
            if connection is not None and connection.cells:
                xs = [x for x, _y in connection.cells]
                ys = [y for _x, y in connection.cells]
                region = Region(min(xs), min(ys), max(xs) - min(xs) + 2, max(ys) - min(ys) + 2)
            # what is under the titles is hidden: the region must show below them
            region = Region(region.x, max(0, region.y - board.header_height), region.width,
                            region.height + board.header_height)
            self.call_after_refresh(lambda: self._reveal(region))

    def _reveal(self, region: Region) -> None:
        """Scroll as little as shows ``region``, horizontally to where a lane begins (no lane cut on the left)."""
        board = self.board
        width = self.size.width
        x = self.scroll_offset.x
        left, right = region.x, region.x + region.width
        if right > x + width:
            x = right - width
        if left < x:
            x = left
        if board is not None and board.lane_x and x != self.scroll_offset.x:
            later = [lx for lx in board.lane_x if lx >= x]
            earlier = [lx for lx in board.lane_x if lx <= left]
            if later and later[0] <= left:
                x = later[0]
            elif earlier:
                x = max(earlier) if max(earlier) + width >= min(right, board.width) else x
        self.scroll_to(x=max(0, x), animate=False, force=True)
        self.scroll_to_region(Region(max(0, x), region.y, 1, region.height), animate=False, force=True)

    def surfaces(self) -> dict[str, Style]:
        """The board's surfaces, as levels between the window's background and its text: the lanes a
        little lighter (or darker), their titles and the cards more. In a theme of one hue they are
        levels of light, so lanes and cards stand out in the monochrome themes too."""
        bg, fg = self.styles.background, self.styles.color
        if bg.a == 0:
            return {"": Style(), "lane": Style(), "lane.alt": Style(), "title": Style(), "card": Style()}

        def level(amount: float, towards=None) -> Style:
            return Style(bgcolor=bg.blend(towards or fg, amount).rich_color)
        # two columns far apart, one darker and one lighter than the window (still two colours where the
        # terminal has only 256 or 16), neither the window's own; the cards a level between them
        dark = Color(0, 0, 0)
        if bg.brightness < 0.1:  # a black (or nearly) window has nothing darker: both columns lighter, apart
            return {"": Style(), "lane": level(0.14), "lane.alt": level(0.36), "title": level(0.36), "card": level(0.25)}
        return {"": Style(), "lane": level(0.5, dark), "lane.alt": level(0.36), "title": level(0.36), "card": level(0.16)}

    def render_line(self, y: int) -> Strip:
        """The lane titles stay at the top (the rows above ``header_height``); the cards scroll under them."""
        scroll_x, scroll_y = self.scroll_offset
        header = self.board.header_height if self.board is not None else 0
        row = y if y < header else y + scroll_y
        width = self.size.width
        if row >= len(self._strips):
            if getattr(self, "_filler", None) is None:
                return Strip.blank(width, self.rich_style)
            return self._filler.crop_extend(scroll_x, scroll_x + width, self.rich_style)
        return self._strips[row].crop_extend(scroll_x, scroll_x + width, self.rich_style)

    def notify_style_update(self) -> None:
        super().notify_style_update()
        if self.board is not None and self.is_mounted:
            self.call_after_refresh(self._window().repaint)

    # ------------------------------------------------------------ keys
    def on_key(self, event: events.Key) -> None:
        """Tab and Shift+Tab go through the connections (a Turbo Vision group would take them to change
        windows before any binding), Esc leaves a connection or the choice of a target."""
        handlers = {"tab": lambda: self.action_connection(1), "shift+tab": lambda: self.action_connection(-1)}
        window = self._window()
        if event.key == "escape" and (window.connecting is not None or window.connection is not None):
            handlers["escape"] = self.action_escape
        if event.key in handlers:
            event.stop()
            event.prevent_default()
            handlers[event.key]()

    def action_move(self, dx: int, dy: int) -> None:
        self._window().move(dx, dy)

    def action_edge(self, where: int) -> None:
        self._window().to_edge(where)

    def action_page(self, where: int) -> None:
        self.scroll_to(y=self.scroll_offset.y + where * max(1, self.size.height - 2), animate=False)

    def action_connection(self, step: int) -> None:
        self._window().cycle_connection(step)

    def action_enter(self) -> None:
        self._window().enter()

    def action_escape(self) -> None:
        self._window().escape()

    def action_back(self) -> None:
        self._window().back()

    def action_add_step(self) -> None:
        self._window().add_step()

    def action_add_block(self) -> None:
        self._window().add_block()

    def action_delete(self) -> None:
        self._window().delete()

    def action_connect(self, key: str) -> None:
        self._window().connect(key)

    def action_context(self) -> None:
        self._window().edit_context()

    def action_reorder(self, dx: int, dy: int) -> None:
        self._window().reorder(dx, dy)

    def action_undo(self) -> None:
        self._window().source.editor.undo()

    def action_redo(self) -> None:
        self._window().source.editor.redo()

    def key_at(self, x: int, y: int) -> Key | None:
        """What is drawn at the widget's (x, y): the lane titles' rows are pinned, not scrolled."""
        if self.board is None:
            return None
        row = y if y < self.board.header_height else y + self.scroll_offset.y
        return self.board.at(x + self.scroll_offset.x, row)

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self.tv_select_self()
        if self.board is None:
            return
        key = self.key_at(event.x, event.y)
        if key is not None:
            self._window().select(key)

    def on_click(self, event: events.Click) -> None:
        if event.chain == 2 and self.board is not None:
            key = self.key_at(event.x, event.y)
            if key is not None:
                self._window().enter()


# ---------------------------------------------------------------- the Block dialog
class BlockDialog(_Dialog):
    """A Block's id and description; for a new one, its first Step too."""

    DEFAULT_CSS = """
    BlockDialog { width: 66; height: 13; }
    BlockDialog.new-block { height: 19; }
    BlockDialog InputLine { width: 1fr; }
    BlockDialog .flow-note { height: 2; margin-top: 1; color: $text; background: $surface; }
    """

    def __init__(self, title: str, block: fm.Block | None, *, offers: dict, note: str = "") -> None:
        super().__init__(title=title)
        self.new = block is None
        self.id_input = InputLine(max_len=128)
        self.description = InputLine(max_len=1024)
        self.step_input = InputLine(max_len=128)
        self.activity = InputLine(max_len=1024)
        if block is not None:
            self.id_input.data = block.id
            self.description.data = block.description
        else:
            self.step_input.data = "start"
            self.add_class("new-block")
        self.offers = offers
        self.note = note
        self.block_id = self.step_id = ""
        self.values: dict = {}

    def compose_content(self) -> ComposeResult:
        yield Label(_('Block ~i~d (letters, digits, _ and -)'), link=self.id_input)
        yield self.id_input
        yield Label(_('~D~escription (optional)'), link=self.description)
        yield self.description
        if self.new:
            yield Label(_('~F~irst Step id'), link=self.step_input)
            yield self.step_input
            yield Label(_('Its ~a~ctivity (a function that does the work)'), link=self.activity)
            offer = self.offers.get("activity")
            yield HistoryInput(self.activity, "flow-activity", offer=offer) if offer is not None else self.activity
        if self.note:
            yield Static(self.note, classes="flow-note", markup=False)
        with Horizontal(classes="dlg-buttons"):
            yield Button(_('O~K~'), Command.OK, is_default=True, id="ok")
            yield Button(_('Cancel'), Command.CANCEL, id="cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(lambda: (self.id_input.tv_select_self(), self.id_input.select_all()))

    def valid(self, command: Command) -> bool:
        if command != Command.OK:
            return True
        self.block_id = self.id_input.data.strip()
        if not fe.ID.match(self.block_id):
            self.app.notify(_('A Block id here is letters, digits, _ and -, starting with a letter or digit'), severity="error")
            return False
        if self.new:
            self.step_id = self.step_input.data.strip()
            if not fe.ID.match(self.step_id):
                self.app.notify(_('A Step id here is letters, digits, _ and -, starting with a letter or digit'), severity="error")
                return False
            if not self.activity.data.strip():
                self.app.notify(_('A Step needs something to do: an activity, a call, a jump, a pause...'), severity="error")
                return False
            self.values = {"activity": self.activity.data.strip()}
        return True


# ---------------------------------------------------------------- the window
class FlowDesignWindow(FlowView):
    """The board | the selected item, with Runner's verdict below (under the board when narrow)."""

    HINT = _('Enter edit · Ins Step · B Block · C/J connect · Tab links · ^T code')
    DEFAULT_CSS = """
    FlowDesignWindow .design-main { layout: horizontal; width: 1fr; height: 1fr; }
    FlowDesignWindow .design-left { width: 1fr; height: 1fr; }
    FlowDesignWindow .design-bar { height: auto; padding: 0 1; background: $foreground; color: $window-content-background; }
    FlowDesignWindow .design-right { width: 40; height: 1fr; }
    FlowDesignWindow.narrow .design-main { layout: vertical; }
    FlowDesignWindow.narrow .design-right { width: 1fr; height: 11; }
    FlowDesignWindow.narrow .design-vrule { display: none; }
    FlowDesignWindow.narrow .design-hrule-top { display: block; }
    FlowDesignWindow .design-hrule-top { display: none; }
    FlowDesignWindow .flow-inspector { width: 1fr; height: auto; padding: 0 1; background: $window-content-background; color: $foreground; }
    FlowDesignWindow VerticalScroll { background: $window-content-background; scrollbar-size: 1 1; }
    FlowDesignWindow .flow-verdict { height: 3; padding: 0 1; background: $window-content-background; color: $foreground; }
    FlowDesignWindow .design-summary { height: auto; padding: 0 1; background: $window-content-background; color: $foreground; }
    FlowDesignWindow.narrow .flow-verdict { height: 2; }
    """

    def __init__(self, source: EditorWindow, number: int = 0) -> None:
        super().__init__(source, number=number)
        self.board_view = FlowBoard()
        self.bar = Static("", classes="design-bar")
        self.summary = Static("", classes="design-summary")  # what the Flow holds and what the lines mean
        self.shown = self.doc if not self.doc.problems else fm.parse("")  # the design drawn: the last that parsed
        self.board: Board | None = None
        self.key: Key | None = None
        self.connection: int | None = None  # index into the selected item's connections
        self.connecting: tuple[str, Key] | None = None  # (call|jump, the Step) while its target is chosen
        self.history: list[Key] = []
        self.overlay: Overlay | None = None  # a playback's marks (divide #10); none in the Designer
        self._width = 0

    def _make_title(self) -> str:
        return f"Flow Designer: {self.source.display_name}"

    def compose_content(self) -> ComposeResult:
        with Vertical(classes="design-main"):
            with Vertical(classes="design-left"):
                yield self.board_view
            yield VRule(classes="design-vrule")
            yield HRule(classes="design-hrule-top")
            with Vertical(classes="design-right"):
                yield self.bar
                with VerticalScroll():
                    yield self.inspector
                yield HRule()
                yield self.summary
                yield HRule()
                yield self.verdict

    def on_mount(self) -> None:
        self.call_after_refresh(self.reload)
        self.call_after_refresh(self.board_view.focus)
        self.call_after_refresh(self._fit)
        self.app.theme_changed_signal.subscribe(self, lambda _theme: self.rebuild())

    def on_resize(self, event: events.Resize) -> None:
        self._narrow(event.size.width)
        self.call_after_refresh(self._fit)

    def _narrow(self, width: int) -> None:
        """Under NARROW columns the panel goes under the board (from the size itself: a Resize may come
        before the window is ready for it)."""
        if width and (width < NARROW) != self.has_class("narrow"):
            self.set_class(width < NARROW, "narrow")

    def _fit(self) -> None:
        self._narrow(self.size.width)
        width = card_width(self.board_view.size.width or self.size.width)
        if self.board is None or width != self.board.card_width:
            self.rebuild()

    # ------------------------------------------------------------ sync
    @property
    def read_only(self) -> bool:
        return bool(self.doc.problems)

    def reload(self) -> None:
        text = self.source.editor.text
        if text == self._built:
            self.show_selected()
            return
        was = self.read_only
        self.doc = fm.parse(text)
        if not self.doc.problems:
            self.shown = self.doc
        if was != self.read_only and hasattr(self.app, "check_flow"):
            self.app.check_flow(self.source.editor)  # the verdict follows: broken, or good again
        self.rebuild()

    def _severity(self, item) -> str | None:
        if self.read_only:
            return None
        if isinstance(item, fm.Step):
            problems = self._step_problems(item)
        else:
            problems = self.problems_in(item.key_start, item.key_end + 1)
            problems += [p for s in item.steps for p in self._step_problems(s)]
        if not problems:
            return None
        return "error" if any(p.severity == "error" for p in problems) else "warning"

    def rebuild(self, cursor: Key | None = None) -> None:
        if not self.doc.problems:
            self.shown = self.doc
        self._built = self.doc.text
        columns = self.board_view.size.width or max(40, (self.size.width or 120) - 42)
        self.board = Board(self.shown, card_width=card_width(columns), severity=self._severity)
        key = cursor or self.key
        if key is None or key not in self.board.boxes:
            key = self._nearest(key)
        if key != self.key:
            self.connection = None
        self.key = key
        self.repaint()

    def _nearest(self, key: Key | None) -> Key | None:
        """Where the selection goes when its item is gone: the same place in its lane, else the first Step."""
        board = self.board
        if not board.lanes:
            return None
        if key is not None:
            block = key[1]
            lane = next((l for l in board.lanes if l[0] == ("block", block)), None)
            if lane is not None:
                return lane[min(1, len(lane) - 1)]
        first = board.lanes[0]
        return first[1] if len(first) > 1 else first[0]

    def connections(self) -> list[Connection]:
        return self.board.connections_of(self.key) if self.board is not None and self.key is not None else []

    def chosen(self) -> Connection | None:
        conns = self.connections()
        return conns[self.connection] if self.connection is not None and self.connection < len(conns) else None

    def repaint(self) -> None:
        if self.board is None or not self.is_mounted:
            return
        self.board_view.show(self.board, self.key, self.chosen(), self.overlay)
        self.show_bar()
        self.show_selected()

    def show_bar(self) -> None:
        """What is going on (choosing a target, read-only, ids taken), at the top of the panel in reverse
        video: it stands out in every theme, and only while it is so."""
        bar = Text()
        strong = Style(bold=True)
        if self.connecting is not None:
            key, source = self.connecting
            bar.append(f"{key.upper()} ", style=strong)
            bar.append(_('from {step}').format(step=f"{source[1]}.{source[2]}") + "\n", style=strong)
            bar.append(_('Choose its target on the board.') + "\n")
            bar.append(_('Enter sets it · Del removes it · Esc cancels'))
        elif self.board is not None and self.board.duplicates:
            bar.append(_('Not drawn') + "\n", style=strong)
            bar.append(_('Their id is taken: {names}.').format(names=", ".join(self.board.duplicates)) + "\n")
            bar.append(_('Ctrl+T: fix it in the code'))
        elif self.read_only:
            bar.append(_('READ-ONLY') + "\n", style=strong)
            bar.append(_('The YAML has errors: the board is the last design that parsed.') + "\n")
            bar.append(_('Ctrl+T: fix it in the code'))
        self.bar.display = bool(bar.plain)
        self.bar.update(bar)
        self.show_summary()

    def show_summary(self) -> None:
        doc = self.shown
        dim = themes.current().token_styles().get("div.comment")
        text = Text()
        text.append(_('{blocks} Block(s), {steps} Step(s)').format(blocks=len(doc.blocks), steps=len(doc.steps())))
        if doc.blocks:
            text.append(" · " + _('starts at {block}').format(block=doc.blocks[0].id), style=dim)
        text.append("\n")
        text.append("─", style=Style(bold=True))
        text.append(_(' CALL returns  '))
        text.append("═", style=Style(bold=True))
        text.append(_(' JUMP goes on  '))
        text.append(_('? no target'), style=dim)
        self.summary.update(text)

    # ------------------------------------------------------------ the selection
    def selected(self) -> fm.Block | fm.Step | None:
        key = self.key
        if key is None:
            return None
        if key[0] == "block":
            return self.shown.block(key[1])
        return self.shown.step(key[1], key[2])

    def select(self, key: Key, *, remember: bool = True) -> None:
        if self.board is None:
            self.key = key
            return
        if key not in self.board.boxes:
            self.rebuild(cursor=key)
            return
        if remember and self.key is not None and key != self.key:
            self.history.append(self.key)
            del self.history[:-50]
        self.key = key
        self.connection = None
        self.repaint()

    def describe(self, item) -> Text:
        if self.read_only:
            text = Text()
            text.append(_('The YAML has errors: the board shows the last design that parsed and edits nothing.') + "\n\n")
            for p in self.diagnostics[:10] or [fm.Problem(p.start, p.end, p.message) for p in self.doc.problems]:
                text.append(f"! {p.message}\n", style=themes.current().token_styles().get("diag.error"))
            return text
        text = Text()
        conn = self.chosen()
        if conn is not None:
            strong = Style(reverse=True, bold=True)
            mine = conn.source == self.key
            text.append(f" {conn.key.upper()} ", style=strong)
            what = _('returns here when the called Block ends') if conn.key == "call" else _('goes on from there, does not return')
            if mine:
                where = f"{conn.target[1]}.{conn.target[2]}" if conn.target and conn.target[0] == "step" else \
                    (_('Block {block}').format(block=conn.target[1]) if conn.target else _('nowhere: not in the Flow'))
                text.append(" -> " + where + "\n")
            else:
                text.append(" " + _('from {step}').format(step=f"{conn.source[1]}.{conn.source[2]}") + "\n")
            text.append(f"{conn.key} {conn.text}: {what}\n", style=themes.current().token_styles().get("div.comment"))
            text.append(_('Enter goes there, Tab the next one, Esc back to the card') + "\n\n",
                        style=themes.current().token_styles().get("div.comment"))
        text.append_text(super().describe(item))
        return text

    # ------------------------------------------------------------ moving around
    def move(self, dx: int, dy: int) -> None:
        board = self.board
        if board is None or self.key is None:
            return
        place = board.lane_of(self.key)
        if place is None:
            return
        lane, index = place
        if dx:
            lane = max(0, min(len(board.lanes) - 1, lane + dx))
            index = min(index, len(board.lanes[lane]) - 1)
        else:
            index = max(0, min(len(board.lanes[lane]) - 1, index + dy))
        self.select(board.lanes[lane][index], remember=False)

    def to_edge(self, where: int) -> None:
        board = self.board
        place = board.lane_of(self.key) if board is not None and self.key is not None else None
        if place is None:
            return
        lane = board.lanes[place[0]]
        self.select(lane[0] if where < 0 else lane[-1], remember=False)

    def cycle_connection(self, step: int) -> None:
        conns = self.connections()
        if not conns:
            self.app.notify(_('No call or jump leads from or to it'), timeout=2)
            return
        if self.connection is None:
            self.connection = 0 if step > 0 else len(conns) - 1
        else:
            self.connection = (self.connection + step) % len(conns)
        self.repaint()

    def follow(self) -> None:
        conn = self.chosen()
        if conn is None:
            return
        other = conn.target if conn.source == self.key else conn.source
        if other is None:
            self.app.notify(f"{conn.key} {conn.text}: " + _('not in the Flow'), severity="error", timeout=3)
            return
        self.select(other)

    def back(self) -> None:
        while self.history:
            key = self.history.pop()
            if self.board is not None and key in self.board.boxes:
                self.select(key, remember=False)
                return

    def escape(self) -> None:
        if self.connecting is not None:
            self.connecting = None
            self.repaint()
        elif self.connection is not None:
            self.connection = None
            self.repaint()

    def goto_target(self) -> bool:
        """Ctrl+Enter: the chosen connection's other end, else the Step's first call or jump target."""
        if self.chosen() is not None:
            self.follow()
            return True
        return super().goto_target()

    def enter(self) -> None:
        if self.connecting is not None:
            self._run(self._connect_here())
        elif self.chosen() is not None:
            self.follow()
        elif self.key is not None and self.key[0] == "block":
            self._run(self._edit_block())
        else:
            self._run(self._edit_step())

    # ------------------------------------------------------------ edits
    async def _can_edit(self) -> bool:
        if self.read_only:
            await self.app.run_dialog(information(  # type: ignore[attr-defined]
                _('Flow'), _('Fix the YAML in the code first (Ctrl+T):\n{error}').format(error=self.doc.problems[0].message)))
            return False
        return True

    async def _say(self, exc: Exception) -> None:
        await self.app.run_dialog(information(_('Flow Designer'), str(exc)))  # type: ignore[attr-defined]

    async def _plan(self, make, cursor: Key) -> bool:
        try:
            plan = make()
        except fm.EditError as exc:
            await self._say(exc)
            return False
        if plan is None:
            return False
        return self.apply_plan(plan, cursor)

    async def _edit_step(self) -> None:
        step = self.selected()
        if not isinstance(step, fm.Step) or not await self._can_edit():
            return
        if step.why is not None:
            await self._say(fm.EditError(_('{step} cannot be edited here: {why}').format(step=step.name, why=step.why)))
            return
        odd = next((a.why for a in step.attrs.values() if a.why and a.key in fm.ATTRS), None)
        note = odd or _("Another id renames the Step and the calls and jumps to it; its activity's result is then "
                        "stored under the new id.")
        dialog = StepDialog(_('Step {name}').format(name=step.name), step, new_id=False, rename=True,
                            offers=self._offers(), note=note)
        if await self.app.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        # only what was changed in the dialog: its other fields still say what the Step said before a
        # rename rewrote them (a jump to the Step itself, say)
        values = {k: v for k, v in dialog.values.items()
                  if not fm._unchanged(step.attrs.get(k), k, fm.normalize({k: v}).get(k))}
        block_id, old, new = step.block, step.id, dialog.step_id
        await self._plan(lambda: fe.chain(
            self.doc,
            lambda d: fe.rename_step(d, d.step(block_id, old), new),
            lambda d: fe.edit_step(d, d.step(block_id, new), values)), ("step", block_id, new))

    async def _edit_block(self) -> None:
        block = self.selected()
        if not isinstance(block, fm.Block) or not await self._can_edit():
            return
        dialog = BlockDialog(_('Block {block}').format(block=block.id), block, offers={},
                             note=_('Another id renames the Block and the calls and jumps that name it.'))
        if await self.app.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        old, new, description = block.id, dialog.block_id, dialog.description.data
        await self._plan(lambda: fe.chain(
            self.doc,
            lambda d: fe.rename_block(d, d.block(old), new),
            lambda d: fe.edit_block(d, d.block(new), description)), ("block", new))

    def add_block(self) -> None:
        self._run(self._add_block())

    async def _add_block(self) -> None:
        if not await self._can_edit():
            return
        item = self.selected()
        after = self.doc.block(item.block if isinstance(item, fm.Step) else item.id) if item is not None else None
        where = _('after {block}').format(block=after.id) if after is not None else _('at the end')
        dialog = BlockDialog(_('New Block'), None, offers=self._offers(),
                             note=_('Written {where}, indented as the other Blocks, with its first Step.').format(where=where))
        if await self.app.run_dialog(dialog) != Command.OK:  # type: ignore[attr-defined]
            return
        block_id, step_id, values, description = dialog.block_id, dialog.step_id, dialog.values, dialog.description.data
        await self._plan(lambda: fe.add_block(self.doc, after, block_id, step_id, values, description),
                         ("step", block_id, step_id))

    def delete(self) -> None:
        self._run(self._delete())

    async def _delete(self) -> None:
        item = self.selected()
        if self.connecting is not None:
            await self.remove_in_connect()
            return
        if item is None or not await self._can_edit():
            return
        if self.connection is not None:
            await self._remove_connection()
            return
        doc = self.doc
        is_step = isinstance(item, fm.Step)
        if is_step:
            refs = [r for r in fe.incoming(doc, item) if r.step_part and r.step is not item]
        else:
            refs = [r for r in fe.incoming(doc, item) if r.step.block != item.id]
        try:
            lost = fm.comments_in(doc, *fe.unit(doc, item))
        except fm.EditError as exc:
            await self._say(exc)
            return
        name = item.name if is_step else item.id
        text = (_('Delete Step {name}?') if is_step else _('Delete Block {name} and its {count} Step(s)?')).format(
            name=name, count=0 if is_step else len(item.steps))
        if refs:
            text += "\n" + _('These lead to it and lose their {what}: {refs}.').format(
                what="call/jump", refs=", ".join(r.describe() for r in refs))
        if not is_step and doc.blocks and doc.blocks[0] is item and len(doc.blocks) > 1:
            text += "\n" + _('It is the entry Block: the Flow will start at {block}.').format(block=doc.blocks[1].id)
        if lost:
            text += "\n" + _('The {count} comment(s) written in it go with it.').format(count=lost)
        if await self.app.run_dialog(confirm(_('Delete'), text)) != Command.YES:  # type: ignore[attr-defined]
            return
        if is_step:
            block = doc.block(item.block)
            rest = [s.id for s in block.steps if s.id != item.id] if block is not None else []
            index = [s.id for s in block.steps].index(item.id) if block is not None else 0
            cursor: Key = ("step", item.block, rest[min(index, len(rest) - 1)]) if rest else ("block", item.block)
            await self._plan(lambda: fe.delete_step(doc, item, unlink=True), cursor)
        else:
            index = doc.blocks.index(item)
            others = [b.id for b in doc.blocks if b is not item]
            cursor = ("block", others[min(index, len(others) - 1)]) if others else ("flow",)
            await self._plan(lambda: fe.delete_block(doc, item, unlink=True), cursor)

    async def _remove_connection(self) -> None:
        conn = self.chosen()
        if conn is None:
            return
        step = self.doc.step(conn.source[1], conn.source[2])
        if step is None:
            return
        if await self.app.run_dialog(confirm(_('Remove'), _('Remove {key} {target} from {step}?').format(  # type: ignore[attr-defined]
                key=conn.key, target=conn.text, step=step.name))) != Command.YES:
            return
        key = self.key
        await self._plan(lambda: fe.set_target(self.doc, step, conn.key, None), key)

    # ------------------------------------------------------------ the context
    def edit_context(self) -> None:
        self._run(self._edit_context())

    async def _edit_context(self) -> None:
        """X: the selected Step's context as a tree or JSON (ContextDialog), written as one edit."""
        from divide.ui.flowcontext import ContextDialog
        step = self.selected()
        if not isinstance(step, fm.Step) or not await self._can_edit():
            return
        attr = step.attrs.get("context")
        try:
            if step.why is not None:
                raise fm.EditError(_('{step} cannot be edited here: {why}').format(step=step.name, why=step.why))
            value = fm.context_data(attr.raw if attr is not None else "")
        except fm.EditError as exc:
            await self._say(exc)
            return
        dialog = ContextDialog(_('Context of {step}').format(step=step.name), value)
        if await self.app.run_dialog(dialog) != Command.OK or dialog.result is None:  # type: ignore[attr-defined]
            return
        text = fm.render_context(dialog.result) if dialog.result else ""
        block_id, step_id = step.block, step.id
        await self._plan(lambda: fe.edit_step(self.doc, self.doc.step(block_id, step_id), {"context": text}),
                         ("step", block_id, step_id))

    # ------------------------------------------------------------ connecting
    def connect(self, key: str) -> None:
        item = self.selected()
        if self.read_only:
            self._run(self._can_edit())
            return
        if not isinstance(item, fm.Step):
            self.app.notify(_('Choose the Step that calls or jumps first'), timeout=3)
            return
        self.connecting = (key, ("step", item.block, item.id))
        self.connection = None
        self.repaint()

    async def _connect_here(self) -> None:
        key, source = self.connecting
        target = self.key
        self.connecting = None
        step = self.doc.step(source[1], source[2])
        if step is None or target is None:
            self.repaint()
            return
        value = f"{target[1]}.{target[2]}" if target[0] == "step" else f"{target[1]}."
        await self._plan(lambda: fe.set_target(self.doc, step, key, value), source)
        self.repaint()

    async def remove_in_connect(self) -> None:
        key, source = self.connecting
        self.connecting = None
        step = self.doc.step(source[1], source[2])
        if step is not None and step.get(key):
            await self._plan(lambda: fe.set_target(self.doc, step, key, None), source)
        self.repaint()

    # ------------------------------------------------------------ reordering
    def reorder(self, dx: int, dy: int) -> None:
        self._run(self._reorder(dx, dy))

    async def _reorder(self, dx: int, dy: int) -> None:
        item = self.selected()
        if item is None or not await self._can_edit():
            return
        doc = self.doc
        if dy:
            if not isinstance(item, fm.Step):
                self.app.notify(_('Ctrl+Left/Right moves a Block; Ctrl+Up/Down moves a Step'), timeout=3)
                return
            block = doc.block(item.block)
            index = block.steps.index(item)
            other = index + dy
            if 0 <= other < len(block.steps) and 0 in (index, other):
                refs = fe.first_step_refs(doc, block)
                new_first = block.steps[other] if index == 0 else item
                if refs and await self.app.run_dialog(confirm(_('Move'), _(  # type: ignore[attr-defined]
                        '{refs} lead(s) to the first Step of {block}: it will be {step}. Move it?').format(
                        refs=", ".join(r.describe() for r in refs), block=block.id, step=new_first.id))) != Command.YES:
                    return
            await self._plan(lambda: fe.move_step(doc, item, dy), ("step", item.block, item.id))
            return
        block = doc.block(item.block) if isinstance(item, fm.Step) else item
        index = doc.blocks.index(block)
        other = index + dx
        if 0 <= other < len(doc.blocks) and 0 in (index, other):
            entry = doc.blocks[other] if index == 0 else block
            if await self.app.run_dialog(confirm(_('Entry Block'), _(  # type: ignore[attr-defined]
                    'The first Block is where the Flow starts: it will be {block}. Move it?').format(block=entry.id))) != Command.YES:
                return
        key = self.key
        await self._plan(lambda: fe.move_block(doc, block, dx), key)

