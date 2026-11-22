"""The Flow Designer's board, laid out as character cells (no Textual: the tests read it as text).

A Flow is drawn as what Runner runs: its Blocks as ordered **lanes**, side by
side (the first one is the entry), and each Block's Steps as ordered **cards**
in its lane, one under the other. A card reads in Runner's order of a Step:
``IF`` condition, ``SET`` context, ``CALL``, ``DO`` activity, ``JUMP``,
``PAUSE``.

Every ``call`` and ``jump`` is a **connection** derived from the YAML (never
stored): a line from the card's port (its ``CALL`` or ``JUMP`` row, on the
card's right edge) to the target's card (or the lane's title, for a Block with
no Steps), ending in an arrow. A call is a single line (``─ │``, port ``├``),
a jump a double one (``═ ║``, port ``╞``), so they are told apart without
colour; a target the Flow does not have ends in ``?``.

Lines run only in the gutters between lanes and in the bands between rows of
cards, never over a card: each connection has its own track in a gutter and,
when it crosses lanes, its own channel in a band; crossings are drawn as
crossings (``┼ ╫ ╪ ╬``). All glyphs are CP437 and one cell wide.

The layout is built once per text and width (:class:`Board`); selection,
emphasis and a future playback (:class:`Overlay`: current, visited, skipped,
paused and failed Steps, connections taken) are painted over it
(:meth:`Board.paint`).
"""

from __future__ import annotations

from divide.i18n import _

from dataclasses import dataclass, field

from divide.glyphs import screen_text
from divide.run import flowedit as fe
from divide.run import flowmodel as fm

Key = tuple  # ("block", id) | ("step", block, id)

N, E, S, W = "n", "e", "s", "w"
_OPPOSITE = {N: S, S: N, E: W, W: E}
# (n, e, s, w) -> glyphs for (single, double, vertical double + horizontal single, vertical single + horizontal double)
_GLYPHS = {
    (1, 0, 1, 0): "│║║│", (1, 0, 0, 0): "│║║│", (0, 0, 1, 0): "│║║│",
    (0, 1, 0, 1): "─══─", (0, 1, 0, 0): "─══─", (0, 0, 0, 1): "─══─",
    (0, 1, 1, 0): "┌╔╓╒", (0, 0, 1, 1): "┐╗╖╕", (1, 1, 0, 0): "└╚╙╘", (1, 0, 0, 1): "┘╝╜╛",
    (1, 1, 1, 0): "├╠╟╞", (1, 0, 1, 1): "┤╣╢╡", (0, 1, 1, 1): "┬╦╥╤", (1, 1, 0, 1): "┴╩╨╧",
    (1, 1, 1, 1): "┼╬╫╪",
}
MARKS = {"current": "►", "visited": "√", "skipped": "-", "paused": "=", "failed": "X"}  # playback (divide #10)


def glyph(dirs: dict[str, str]) -> str:
    """The box-drawing character joining ``dirs`` (direction -> "s" single or "d" double)."""
    if not dirs:
        return " "
    shape = tuple(int(d in dirs) for d in (N, E, S, W))
    vertical = "d" if "d" in (dirs.get(N), dirs.get(S)) else "s"
    horizontal = "d" if "d" in (dirs.get(E), dirs.get(W)) else "s"
    if not (dirs.get(N) or dirs.get(S)):
        vertical = horizontal
    if not (dirs.get(E) or dirs.get(W)):
        horizontal = vertical
    index = {("s", "s"): 0, ("d", "d"): 1, ("d", "s"): 2, ("s", "d"): 3}[(vertical, horizontal)]
    return _GLYPHS[shape][index]


@dataclass
class Overlay:
    """What a playback would show over the board (divide #10): nothing yet in the Designer."""

    marks: dict[Key, str] = field(default_factory=dict)  # Step -> current, visited, skipped, paused, failed
    taken: set[tuple[Key, str]] = field(default_factory=set)  # (Step, call|jump) connections taken


@dataclass
class Box:
    key: Key
    x: int
    y: int
    w: int
    h: int

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h


@dataclass
class Connection:
    """A ``call`` or ``jump``, as drawn."""

    source: Key  # the Step that has it
    key: str  # call, jump
    text: str  # the target as written
    target: Key | None  # the Step (or Block) it leads to; None: not in the Flow
    cells: list[tuple[int, int]] = field(default_factory=list)  # where its line is drawn

    @property
    def kind(self) -> str:
        return "d" if self.key == "jump" else "s"


def step_lines(step: fm.Step) -> list[tuple[str, str]]:
    """A card's rows, in Runner's order of a Step: (what, text)."""
    module = step.get("module")
    prefix = f"{module}:" if module else ""
    out: list[tuple[str, str]] = []
    if step.get("condition"):
        out.append(("condition", f"IF {prefix}{step.get('condition')}()"))
    if "context" in step.attrs:
        shown = step.get("context").strip()
        if shown.startswith("{") and shown.endswith("}"):
            shown = shown[1:-1].strip()
        out.append(("context", f"SET {shown}"))
    if step.get("call"):
        out.append(("call", f"CALL {step.get('call')}"))
    if step.get("activity"):
        out.append(("activity", f"DO {prefix}{step.get('activity')}()"))
    if step.get("jump"):
        out.append(("jump", f"JUMP {step.get('jump')}"))
    if step.get("pause").lower() == "true":
        out.append(("pause", "PAUSE"))
    if not out:
        out.append(("empty", _('(nothing to do)')))
    return out


def _cut(text: str, width: int) -> str:
    """What fits in ``width`` cells (a cut marked ~), any character a terminal could draw wide made safe."""
    text = screen_text(text)
    return text if len(text) <= width else text[:max(0, width - 1)] + "~"


def _intervals(items: list[tuple[object, object, object]]) -> dict[object, int]:
    """Greedy colouring of closed intervals (low, high, id) -> id: its track, none sharing a point."""
    tracks: list[object] = []  # the last high of each track
    out = {}
    for low, high, ident in sorted(items, key=lambda i: (i[0], i[1])):
        for t, last in enumerate(tracks):
            if last < low:
                tracks[t] = high
                out[ident] = t
                break
        else:
            tracks.append(high)
            out[ident] = len(tracks) - 1
    return out


class Board:
    """A Flow as lanes of cards and the connections between them, in character cells."""

    HEADER = 3  # a lane's title, its description, its rule

    def __init__(self, doc: fm.FlowDoc, *, card_width: int = 26, severity=None) -> None:
        """``severity(item)``: "error", "warning" or None for a Block or a Step (its diagnostics)."""
        self.doc = doc
        self.card_width = max(16, card_width)
        self.severity = severity or (lambda item: None)
        self.boxes: dict[Key, Box] = {}
        self.lanes: list[list[Key]] = []  # each lane: its title, then its cards
        self.connections: list[Connection] = []
        self.chars: list[list[str]] = []
        self.styles: list[list[str]] = []
        self.width = self.height = 0
        self.header_height = 0
        self.lane_x: list[int] = []
        self.duplicates: list[str] = []  # Blocks and Steps not drawn: their id is taken by an earlier one
        self._build()

    # ------------------------------------------------------------ building
    def _build(self) -> None:
        doc, cw = self.doc, self.card_width + 2  # a lane: its cards and a column of margin on each side
        # a Block or Step whose id is taken by an earlier one is not drawn (Runner refuses it too): said
        blocks, seen = [], set()
        for b in doc.blocks:
            if b.id in seen:
                self.duplicates.append(b.id)
            else:
                seen.add(b.id)
                blocks.append(b)
        steps_of: list[list[fm.Step]] = []
        for b in blocks:
            mine, ids = [], set()
            for st in b.steps:
                if st.id in ids:
                    self.duplicates.append(st.name)
                else:
                    ids.add(st.id)
                    mine.append(st)
            steps_of.append(mine)
        lane_of = {id(b): i for i, b in enumerate(blocks)}
        lines = {id(s): step_lines(s) for st_list in steps_of for s in st_list}
        pad: dict[tuple[int, int], int] = {}  # blank rows a card gets when more arrows arrive than it has rows
        incoming: dict[Key, int] = {}
        for ref in fe.references(doc):
            if ref.target is not None:
                k = ("step", ref.target.block, ref.target.id)
                incoming[k] = incoming.get(k, 0) + 1
        self._incoming = incoming

        def height(i: int, row: int) -> int:
            if row < 0:
                return self.HEADER + max((v for (_l, r), v in pad.items() if r < 0), default=0)
            return 2 + len(lines[id(steps_of[i][row])]) + pad.get((i, row), 0)

        rows = max((len(st) for st in steps_of), default=0)

        # the connections: from the port (lane i, row a, offset p) to (lane j, row b) or nowhere
        routes = []
        for ref in fe.references(doc):
            step = ref.step
            block = doc.block(step.block)
            if block is None or id(block) not in lane_of or step not in steps_of[lane_of[id(block)]]:
                continue
            i, a = lane_of[id(block)], steps_of[lane_of[id(block)]].index(step)
            port = 1 + [k for k, _t in lines[id(step)]].index(ref.key)
            source: Key = ("step", step.block, step.id)
            if ref.block is not None and id(ref.block) in lane_of:
                j = lane_of[id(ref.block)]
                b = steps_of[j].index(ref.target) if ref.target is not None and ref.target in steps_of[j] else -1
                if ref.target is None and ref.step_part:
                    routes.append([Connection(source, ref.key, str(ref.attr.value), None), i, a, port, None, None])
                    continue
                target: Key = ("step", ref.block.id, ref.target.id) if ref.target is not None else ("block", ref.block.id)
                routes.append([Connection(source, ref.key, str(ref.attr.value), target), i, a, port, j, b])
            else:
                routes.append([Connection(source, ref.key, str(ref.attr.value), None), i, a, port, None, None])

        # where each arrives: a free row of the target's side (left: from lanes to its left)
        ports = {(i, r): {1 + n for n, (k, _t) in enumerate(lines[id(st)]) if k in fm.TARGET_ATTRS}
                 for i, st_list in enumerate(steps_of) for r, st in enumerate(st_list)}
        # a gutter's rows are taken by the ports of the lane on its left and by the arrows into the
        # lanes on both its sides: each arrow gets a row of its target no other line of that gutter uses
        # (a card short of free rows grows by a blank row, and the arrows are placed again)
        for _attempt in range(64):
            taken: set[tuple[int, int, int, int]] = {(i, r, 1, o) for (i, r), offsets in ports.items() for o in offsets}
            short = None
            for route in routes:
                del route[6:]
                conn, i, a, port, j, b = route
                if j is None:
                    route.extend([None, None])
                    continue
                side = "left" if j > i else "right"
                gutter = j - 1 if side == "left" else j
                free = [o for o in range(0, height(j, b) - 1) if (gutter, b, 1, o) not in taken]
                if not free and short is None:
                    short = (j, b)
                entry = free[0] if free else 0
                taken.add((gutter, b, 1, entry))
                route.extend([side, entry])
            if short is None:
                break
            pad[short] = pad.get(short, 0) + 1
        row_height = [max((height(i, r) for i, st in enumerate(steps_of) if r < len(st)), default=3) for r in range(rows)]

        # tracks in gutters (abstract y: (row, 0 band / 1 card, sub)) and channels in bands
        channel_items, track_items = {}, {}
        for n, (conn, i, a, port, j, b, side, entry) in enumerate(routes):
            if j is None:
                continue
            if j == i or j == i + 1:
                lo, hi = sorted([(a, 1, port), (b, 1, entry)])
                track_items.setdefault(i, []).append((lo, hi, (n, 0)))
            else:
                g2 = j - 1 if j > i else j
                channel_items.setdefault(b, []).append((min(i, g2), max(i, g2), n))
        channels = {band: _intervals(items) for band, items in channel_items.items()}
        band_count = {band: (max(c.values()) + 1 if c else 0) for band, c in channels.items()}
        for n, (conn, i, a, port, j, b, side, entry) in enumerate(routes):
            if j is None or j == i or j == i + 1:
                continue
            g2 = j - 1 if j > i else j
            c = channels[b][n]
            lo, hi = sorted([(a, 1, port), (b, 0, c)])
            track_items.setdefault(i, []).append((lo, hi, (n, 0)))
            track_items.setdefault(g2, []).append(((b, 0, c), (b, 1, entry), (n, 1)))
        tracks = {g: _intervals(items) for g, items in track_items.items()}
        gutter_tracks = [max(tracks.get(g, {0: -1}).values(), default=-1) + 1 for g in range(len(blocks))]

        # geometry
        gutter_width = [max(4, t + 3) for t in gutter_tracks]
        lane_x, x = [], 1
        for g in range(len(blocks)):
            lane_x.append(x)
            x += cw + gutter_width[g]
        self.width = max(x, cw + 2)
        self.lane_x = [lx - 1 for lx in lane_x]  # where a lane begins: what horizontal scrolling snaps to
        gutter_x = [lane_x[g] + cw for g in range(len(blocks))]
        band_y, card_y = {}, {}
        y = 0
        band_y[-1] = y
        y += band_count.get(-1, 0)
        card_y[-1] = y
        y += height(0, -1) if blocks else self.HEADER
        self.header_height = y  # the rows the lane titles take: kept in view while the cards scroll
        for r in range(rows):
            band_y[r] = y
            y += band_count.get(r, 0) + 1
            card_y[r] = y
            y += row_height[r]
        self.height = y + 1

        def ay(point: tuple) -> int:
            row, phase, sub = point
            return band_y[row] + sub if phase == 0 else card_y[row] + sub

        self.chars = [[" "] * self.width for _ in range(self.height)]
        self.styles = [[""] * self.width for _ in range(self.height)]
        self.fill = [[""] * self.width for _ in range(self.height)]  # the surface under each cell: lane, title, card
        bits: dict[tuple[int, int], dict[str, str]] = {}
        owner: dict[tuple[int, int], int] = {}

        # lanes and cards
        for i, block in enumerate(blocks):
            lane: list[Key] = [("block", block.id)]
            # a Block is a column of its own colour, from its left edge to the next one's, down to the end;
            # neighbours alternate, so the colour alone tells one Block from the next
            right = lane_x[i + 1] - 1 if i + 1 < len(blocks) else self.width
            for yy in range(self.height):
                for xx in range(0 if i == 0 else lane_x[i] - 1, right):
                    self.fill[yy][xx] = self.column_fill(i)
            self._lane_title(i, block, lane_x[i], card_y[-1], height(i, -1))
            for r, step in enumerate(steps_of[i]):
                key: Key = ("step", block.id, step.id)
                lane.append(key)
                self._card(key, step, r, lines[id(step)] + [("pad", "")] * pad.get((i, r), 0), lane_x[i] + 1, card_y[r])
            self.lanes.append(lane)

        # connections
        def walk(n: int, points: list[tuple[int, int]], kind: str) -> None:
            for (x0, y0), (x1, y1) in zip(points, points[1:]):
                dx = (x1 > x0) - (x1 < x0)
                dy = (y1 > y0) - (y1 < y0)
                cx, cy = x0, y0
                while (cx, cy) != (x1, y1):
                    nx, ny = cx + dx, cy + dy
                    d = E if dx > 0 else W if dx < 0 else S if dy > 0 else N
                    bits.setdefault((cx, cy), {})[d] = kind if bits.get((cx, cy), {}).get(d) != "d" else "d"
                    bits.setdefault((nx, ny), {})[_OPPOSITE[d]] = kind if bits.get((nx, ny), {}).get(_OPPOSITE[d]) != "d" else "d"
                    owner.setdefault((cx, cy), n)
                    owner.setdefault((nx, ny), n)
                    cx, cy = nx, ny

        arrows: list[tuple[int, int, str, int]] = []
        for n, (conn, i, a, port, j, b, side, entry) in enumerate(routes):
            kind = conn.kind
            py = card_y[a] + port
            port_x = gutter_x[i] - 2  # the card's right edge (a margin and the lane's frame after it)
            start = (gutter_x[i] - 1, py)
            self.chars[py][port_x] = "├" if kind == "s" else "╞"
            self.styles[py][port_x] = "port"
            cells: list[tuple[int, int]] = []
            if j is None:  # nowhere to go: a ? right at the port, on the port's own row of the gutter
                arrows.append((gutter_x[i] - 1, py, "?", n))
                conn.cells = [start]
                self.connections.append(conn)
                continue
            ey = ay((b, 1, entry))
            if j == i or j == i + 1:
                tx = gutter_x[i] + 1 + tracks[i][(n, 0)]
                if j == i:
                    end, head = (gutter_x[i] - 1, ey), "◄"
                else:
                    end, head = (lane_x[j], ey), "►"
                points = [(port_x, py), (tx, py), (tx, ey), end]
            else:
                g2 = j - 1 if j > i else j
                cy = ay((b, 0, channels[b][n]))
                tx = gutter_x[i] + 1 + tracks[i][(n, 0)]
                ux = gutter_x[g2] + 1 + tracks[g2][(n, 1)]
                if j > i:
                    end, head = (lane_x[j], ey), "►"
                else:
                    end, head = (gutter_x[j] - 1, ey), "◄"
                points = [(port_x, py), (tx, py), (tx, cy), (ux, cy), (ux, ey), end]
            points = [p for k, p in enumerate(points) if k == 0 or p != points[k - 1]]
            walk(n, points, kind)
            bits.get((port_x, py), {}).clear()  # the port itself is drawn on the card's edge
            arrows.append((end[0], end[1], head, n))
            for (x0, y0), (x1, y1) in zip(points, points[1:]):  # in the order the line runs: the arrow last
                dx, dy = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
                cx, cy = x0, y0
                while True:
                    if (cx, cy) not in cells and (cx, cy) != (port_x, py):
                        cells.append((cx, cy))
                    if (cx, cy) == (x1, y1):
                        break
                    cx, cy = cx + dx, cy + dy
            conn.cells = cells
            self.connections.append(conn)

        for (cx, cy), dirs in bits.items():
            if dirs and 0 <= cy < self.height and 0 <= cx < self.width and self.chars[cy][cx] == " ":
                self.chars[cy][cx] = glyph(dirs)
                self.styles[cy][cx] = "jump" if "d" in dirs.values() else "call"
        for ax, ay_, head, n in arrows:
            self.chars[ay_][ax] = head
            self.styles[ay_][ax] = "error" if head == "?" else ("jump" if routes[n][0].kind == "d" else "call")

    @staticmethod
    def column_fill(index: int) -> str:
        return "lane" if index % 2 == 0 else "lane.alt"

    def filler(self) -> list[str]:
        """A row under the board: each Block's column carries on to the bottom of the window."""
        return self.fill[-1][:] if self.fill else []

    def _put(self, x: int, y: int, text: str, style: str) -> None:
        row, styles = self.chars[y], self.styles[y]
        for k, ch in enumerate(text):
            if 0 <= x + k < self.width:
                row[x + k] = ch
                styles[x + k] = style

    def _lane_title(self, index: int, block: fm.Block, x: int, y: int, h: int = 3) -> None:
        cw = self.card_width + 2
        key: Key = ("block", block.id)
        entry = _('ENTRY') if index == 0 else ""
        flag = {"error": "!E", "warning": "!W"}.get(self.severity(block) or "", "")
        right = " ".join(t for t in (flag, entry) if t)
        title = _cut(f"{index + 1} {block.id}", cw - len(right) - 3)
        self._put(x, y, " " + title + " " * (cw - len(title) - len(right) - 2) + right + " ", "title")
        if entry:
            self._put(x + cw - len(entry) - 1, y, entry, "entry")
        if flag:
            self._put(x + cw - len(right) - 1, y, flag, "error" if flag == "!E" else "warning")
        count = len(block.steps)
        under = block.description or (_('{n} Step(s)').format(n=count) if count else _('(no Steps)'))
        self._put(x, y + 1, " " + _cut(under, cw - 2), "dim")
        self.boxes[key] = Box(key, x, y, cw, h)

    def _card(self, key: Key, step: fm.Step, row: int, lines: list[tuple[str, str]], x: int, y: int) -> None:
        cw = self.card_width
        h = 2 + len(lines)
        severity = self.severity(step)
        flags = " ".join(t for t in ({"error": "!E", "warning": "!W"}.get(severity or "", ""), "RO" if step.why else "") if t)
        right = f" {flags} " if flags else ""
        title = _cut(f" {row + 1} {step.id} ", cw - 3 - len(right))
        self._put(x, y, "┌" + title + "─" * (cw - 2 - len(title) - len(right)) + right + "┐", "border")
        self._put(x + 1, y, title, "id")
        if flags:
            self._put(x + cw - 1 - len(right), y, right, "error" if severity == "error" else "warning" if severity == "warning" else "dim")
        for n, (what, text) in enumerate(lines):
            self._put(x, y + 1 + n, "│" + " " * (cw - 2) + "│", "border")
            word, _sp, rest = text.partition(" ") if what not in ("empty", "pause") else (text, "", "")
            shown = _cut(text, cw - 4)
            self._put(x + 2, y + 1 + n, shown, "text")
            if what in ("empty",):
                self._put(x + 2, y + 1 + n, shown, "dim")
            else:
                self._put(x + 2, y + 1 + n, shown[:len(word)], "kw." + what)
        bottom = "└" + "─" * (cw - 2) + "┘"
        count = self._incoming.get(key, 0)
        if count:
            mark = f" ◄{count} "
            bottom = "└" + "─" * (cw - 3 - len(mark)) + mark + "─┘"
        self._put(x, y + h - 1, bottom, "border")
        for yy in range(y, y + h):
            for xx in range(x, x + cw):
                self.fill[yy][xx] = "card"
        self.boxes[key] = Box(key, x, y, cw, h)

    # ------------------------------------------------------------ reading it
    def connections_of(self, key: Key) -> list[Connection]:
        """``key``'s connections: those it has (in the order of its card), then those leading to it."""
        mine = [c for c in self.connections if c.source == key]
        theirs = [c for c in self.connections if c.target == key and c.source != key]
        return mine + theirs

    def at(self, x: int, y: int) -> Key | None:
        return next((box.key for box in self.boxes.values() if box.contains(x, y)), None)

    def lane_of(self, key: Key) -> tuple[int, int] | None:
        for i, lane in enumerate(self.lanes):
            if key in lane:
                return i, lane.index(key)
        return None

    def paint(self, selected: Key | None = None, connection: Connection | None = None,
              overlay: Overlay | None = None) -> list[list[tuple[str, str]]]:
        """The board's cells as (char, style), the selection and emphasis painted over the layout:
        the selected card or title reversed, its connections ``hot``, the selected one ``chosen``."""
        chars = [row[:] for row in self.chars]
        styles = [row[:] for row in self.styles]
        if overlay is not None:
            for key, mark in overlay.marks.items():
                box = self.boxes.get(key)
                if box is not None and mark in MARKS:
                    chars[box.y][box.x + 1] = MARKS[mark]
                    styles[box.y][box.x + 1] = "mark"
            for conn in self.connections:
                if (conn.source, conn.key) in overlay.taken:
                    for cx, cy in conn.cells:
                        styles[cy][cx] = "taken"
        if selected is not None:
            for conn in self.connections_of(selected):
                for cx, cy in conn.cells:
                    styles[cy][cx] = "hot"
        if connection is not None:
            for cx, cy in connection.cells:
                styles[cy][cx] = "chosen"
        box = self.boxes.get(selected) if selected is not None else None
        if box is not None:
            for yy in range(box.y, box.y + box.h):
                for xx in range(box.x, box.x + box.w):
                    styles[yy][xx] = "sel:" + (styles[yy][xx] or "text")
        return [list(zip(c, s)) for c, s in zip(chars, styles)]

    def text(self, selected: Key | None = None) -> str:
        """The board as plain text (the tests read it)."""
        return "\n".join("".join(ch for ch, _s in row).rstrip() for row in self.paint(selected))
