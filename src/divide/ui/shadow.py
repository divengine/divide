"""Turbo Vision drop shadows.

In Turbo Vision every window, dialog and menu casts a shadow two columns to
the right and one row down; the cells under it keep their characters but are
drawn dark gray on black. Textual has no notion of this, so screens that want
it use a compositor that post-processes the composited lines: after the
normal front-to-back composition, the shadow cells are restyled.

A shadow only darkens what is *behind* its caster: cells covered by anything
in front of the caster (a window above it, an open menu) are left alone.
"""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

from rich.segment import Segment
from rich.style import Style
from textual._compositor import Compositor
from textual.geometry import Region
from textual.screen import Screen
from textual.strip import Strip
from textual.widget import Widget

SHADOW_STYLE = Style(color="#555555", bgcolor="#000000", bold=False, italic=False, underline=False, reverse=False, dim=False)
SHADOW_X, SHADOW_Y = 2, 1

Spans = dict[int, list[tuple[int, int]]]  # row -> sorted, disjoint [x0, x1) ranges


def shadow_regions(region: Region) -> list[Region]:
    """The parts of ``region`` shifted by the shadow offset that ``region`` does not cover."""
    x, y, w, h = region
    if w <= 0 or h <= 0:
        return []
    return [Region(x + w, y + SHADOW_Y, SHADOW_X, h), Region(x + SHADOW_X, y + h, max(0, w - SHADOW_X), SHADOW_Y)]


def _subtract(spans: list[tuple[int, int]], a: int, b: int) -> list[tuple[int, int]]:
    out = []
    for x0, x1 in spans:
        if b <= x0 or a >= x1:
            out.append((x0, x1))
            continue
        if x0 < a:
            out.append((x0, a))
        if b < x1:
            out.append((b, x1))
    return out


def _union(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for x0, x1 in sorted(spans):
        if merged and x0 <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], x1))
        else:
            merged.append((x0, x1))
    return merged


def compute_shadow_spans(
    widgets: Sequence[tuple[Widget, Region, Region]], casts_shadow: Callable[[Widget], bool]
) -> tuple[Spans, list[Region]]:
    """Shadow cells for a front-to-back list of (widget, region, clip).

    Returns the cells to darken and the shadow rectangles (for dirty tracking).
    """
    spans: Spans = {}
    rects: list[Region] = []
    for index, (caster, region, clip) in enumerate(widgets):
        if not casts_shadow(caster):
            continue
        # Everything in front of the caster that is not part of it hides its shadow.
        in_front = [
            r.intersection(c)
            for w, r, c in widgets[:index]
            if w is not caster and caster not in w.ancestors
        ]
        for rect in shadow_regions(region):
            rect = rect.intersection(clip)
            if not rect.area:
                continue
            rects.append(rect)
            for y in range(rect.y, rect.bottom):
                row = [(rect.x, rect.right)]
                for front in in_front:
                    if front.y <= y < front.bottom:
                        row = _subtract(row, front.x, front.right)
                        if not row:
                            break
                if row:
                    spans.setdefault(y, []).extend(row)
    return {y: _union(row) for y, row in spans.items()}, rects


def darken(strip: Strip, start: int, end: int) -> Strip:
    """Restyle cells [start, end) of ``strip`` as shadow, keeping the characters."""
    length = strip.cell_length
    start, end = max(0, start), min(end, length)
    if start >= end:
        return strip
    before, middle, after = strip.divide([start, end, length])
    shaded = Strip(
        [seg if seg.control else Segment(seg.text, (seg.style or Style.null()) + SHADOW_STYLE) for seg in middle],
        middle.cell_length,
    )
    return Strip.join([before, shaded, after])


class ShadowCompositor(Compositor):
    def __init__(self, casts_shadow: Callable[[Widget], bool]) -> None:
        super().__init__()
        self._casts_shadow = casts_shadow
        self._shadow_key: object = None
        self._shadow_spans: Spans = {}
        self._shadow_rects: list[Region] = []

    def _shadows(self) -> Spans:
        visible = self.visible_widgets
        if visible is not self._shadow_key:
            self._shadow_key = visible
            widgets = [(w, region, clip) for w, (region, clip) in visible.items()]
            self._shadow_spans, rects = compute_shadow_spans(widgets, self._casts_shadow)
            if rects != self._shadow_rects:
                # Moved / opened / closed casters: repaint where shadows were and are.
                self._dirty_regions.update(self._shadow_rects)
                self._dirty_regions.update(rects)
                self._shadow_rects = rects
        return self._shadow_spans

    def render_update(self, full: bool = False, screen_stack=None, simplify: bool = False):
        self._shadows()  # may widen the dirty regions before the update is planned
        return super().render_update(full=full, screen_stack=screen_stack, simplify=simplify)

    def _render_chops(self, crop: Region, is_rendered_line: Callable[[int], bool]) -> Sequence[Mapping[int, Strip]]:
        chops = super()._render_chops(crop, is_rendered_line)
        spans = self._shadows()
        if not spans:
            return chops
        for y, row in spans.items():
            if not (0 <= y < len(chops)):
                continue
            line = chops[y]
            for cut, strip in list(line.items()):
                if strip is None:
                    continue
                cut_end = cut + strip.cell_length
                for x0, x1 in row:
                    if x0 < cut_end and x1 > cut:
                        strip = darken(strip, x0 - cut, x1 - cut)
                line[cut] = strip  # type: ignore[index]
        return chops


def casts_tv_shadow(widget: Widget) -> bool:
    """Windows, dialogs and drop-down menus cast shadows, as in Turbo Vision."""
    from textual_vision.menus import MenuBox
    from textual_vision.window import Window

    return isinstance(widget, (Window, MenuBox)) or getattr(widget, "tv_shadow", False)


def install_shadows(screen: Screen, casts_shadow: Callable[[Widget], bool] = casts_tv_shadow) -> None:
    """Give ``screen`` a shadow-drawing compositor (call from its ``__init__``)."""
    screen._compositor = ShadowCompositor(casts_shadow)


class ShadowScreen(Screen):
    """A plain screen whose windows and menus cast Turbo Vision shadows."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        install_shadows(self)
