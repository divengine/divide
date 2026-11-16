"""Debug > Render trace: how Div mutated a template into its output.

A render is not stepped line by line: Div rewrites the whole template again
and again until nothing changes. The trace window replays that: the list at
the bottom has one row per mutation (in Div's words: "Condition {$x} > 0 >
The condition 2 > 0 is true", "Trying to include layout/header.tpl"), the
sub-parses Div starts (each item of a list, each condition) indented, and the
fixed points; the view at the top shows the template as it was at that row,
what the mutation wrote marked in green. Space shows it before the mutation,
what it took away in red.

Keys, the debugger's: Up / Down every row, F8 the next row of the same parse
(over sub-parses), F7 the next row (into them), Shift+F8 out to the parse
that started this one.
"""

from __future__ import annotations

from divide.i18n import _, ngettext

from pathlib import Path

from textual import events
from textual.app import ComposeResult

from divide.run.render import RenderError
from divide.run.script import size_text
from divide.run.trace import Mutation, RenderTrace, trace_render
from divide.ui.dialogs import information
from divide.ui.progress import ProgressDialog, run_with_progress
from divide.ui.runner import PickList
from divide.ui.windows import EditorView, HRule, IndicatorFrame, _TVWindow

LIST_HEIGHT = 9


class TraceList(PickList):
    """The mutations; moving the bar shows the row in the view above."""

    DEFAULT_CSS = PickList.DEFAULT_CSS + f"\nTraceList {{ height: {LIST_HEIGHT}; width: 1fr; }}\n"

    def focus_item(self, item: int) -> None:
        super().focus_item(item)
        window = self.parent.parent if self.parent is not None else None
        if isinstance(window, TraceWindow):
            window.show_row(self.focused)


def row_text(m: Mutation) -> str:
    """``  -30    Condition {$x} > 0 > The condition 2 > 0 is true``: bytes, then the step;
    sub-parses indented."""
    indent = "  " * max(0, m.level - 1)
    size = f"{m.delta:+6d}" if m.kind == "change" else " " * 6
    mark = {"start": "► ", "end": "■ ", "output": "■ "}.get(m.kind, "  ")
    return f"{size}  {indent if m.kind != 'output' else ''}{mark}{m.label}"


class TraceWindow(_TVWindow):
    """The view of the template at a row, the rule, the rows."""

    HINT = _('F8 step · F7 into · Shift+F8 out · Space before/after')

    def __init__(self, number: int = 0) -> None:
        super().__init__(_('Render trace'), number=number)
        self.view = EditorView("", read_only=True)
        self.list = TraceList([])
        self.template: Path | None = None
        self.rows: list[Mutation] = []
        self.before = False  # Space: the row's source before the mutation
        self.trace: RenderTrace | None = None

    def compose_content(self) -> ComposeResult:
        yield self.view
        yield HRule()
        yield self.list

    # ------------------------------------------------------------ load
    def load(self, template: Path, trace: RenderTrace) -> None:
        self.template, self.trace = template, trace
        self.title = _('Render trace: {name}').format(name=template.name)
        self.rows = list(trace.mutations)
        if trace.result.output or not self.rows:
            self.rows.append(Mutation("output", 0, 0, 0, self.rows[-1].after if self.rows else "", trace.result.output))
        self.view.set_path(template)  # Div highlighting (the view never saves)
        self.list.set_list([row_text(m) for m in self.rows])
        self.before = False
        self.list.focus_item(0)
        self.show_row(0)

    # ------------------------------------------------------------ view
    def show_row(self, index: int) -> None:
        if not 0 <= index < len(self.rows):
            return
        m = self.rows[index]
        (b0, b1), (a0, a1) = m.changed() if m.kind == "change" else ((0, 0), (0, 0))
        if self.before and m.kind == "change":
            text, mark, style = m.before, (b0, b1), "trace.old"
        else:
            text, mark, style = m.after, (a0, a1), "trace.new"
        if text != self.view.text:
            self.view.load_text(text)
        self.view.set_marks([(mark[0], mark[1], style)] if mark[1] > mark[0] else [])
        here = self.view.document.get_location_from_index(min(mark[0], len(text)))
        self.view.move_cursor(here)
        self.view.reveal_cursor()
        frame = self.query_one(IndicatorFrame) if self.is_mounted else None
        if frame is not None:
            side = "before" if self.before and m.kind == "change" else "after"
            what = {"start": "start", "end": "fixed point", "output": "output"}.get(m.kind, f"{m.delta:+d} · {side}")
            cycle = f" · cycle {m.cycle}" if m.kind == "change" else ""
            frame.set_indicator(f"{index + 1}/{len(self.rows)}{cycle} · {what}")
        if self.is_attached and self.app.active_window() is self:  # type: ignore[attr-defined]
            self.app.update_status()  # type: ignore[attr-defined]

    def hint(self) -> str:
        """The row in full, for the status line."""
        index = self.list.focused
        if not 0 <= index < len(self.rows):
            return self.HINT
        return f"{self.rows[index].label} · {self.HINT}"

    def toggle_before(self) -> None:
        self.before = not self.before
        self.show_row(self.list.focused)

    # ----------------------------------------------------------- steps
    def step(self, how: str) -> None:
        """``into`` the next row, ``over`` the next of this parse, ``out`` to the parse above."""
        here = self.list.focused
        if not 0 <= here < len(self.rows):
            return
        current = self.rows[here]
        for index in range(here + 1, len(self.rows)):
            row = self.rows[index]
            if how == "into":
                break
            if how == "over" and (row.run == current.run or row.level < current.level or row.kind == "output"):
                break
            if how == "out" and (row.level < current.level or row.kind == "output"):
                break
        else:
            return
        self.list.focus_item(index)

    def on_key(self, event: events.Key) -> None:
        steps = {"f7": "into", "f8": "over", "shift+f8": "out"}
        if event.key in steps:
            event.stop()
            event.prevent_default()
            self.step(steps[event.key])
        elif event.key == "space":
            event.stop()
            event.prevent_default()
            self.toggle_before()


class TraceMixin:
    """Debug > Render trace (mixed into the Divide app)."""

    def trace_window(self) -> TraceWindow | None:
        return next((w for w in self.windows() if isinstance(w, TraceWindow)), None)

    async def trace_render_command(self) -> None:
        inputs = await self.render_inputs(_('Render trace'))
        if inputs is None:
            return
        template, engine, code, data_path, data = inputs
        dialog = ProgressDialog(_('Tracing'), [
            (_('Template'), self._relative(template)),
            (_('Data'), self._relative(data_path) if data is not None else _('(none)')),
            (_('Engine'), self._relative(engine)),
        ])

        def verdict(trace: RenderTrace) -> tuple[str, bool, list[tuple[str, str]]]:
            changes = sum(m.kind == "change" for m in trace.mutations)
            parses = sum(m.kind == "start" for m in trace.mutations)
            rows = [(_("Mutations"), ngettext("{changes} in {n} parse", "{changes} in {n} parses", parses).format(changes=changes, n=parses)),
                    (_("Output"), size_text(trace.result.output))]
            if trace.truncated:
                rows.append((_("Trace"), _('too long: cut')))
            if trace.result.fatal:
                return _("Errors"), False, rows
            return _("Success"), not trace.truncated, rows

        try:
            with self.busy(f"Tracing {template.name}..."):
                trace = await run_with_progress(self, dialog, trace_render(engine, template, code, data, cwd=self.root), verdict)
        except RenderError as exc:
            await self.run_dialog(information(_('Render trace'), str(exc)))
            return
        if trace is None:
            return
        self.last_template = template
        window = self.trace_window()
        if window is None:
            window = TraceWindow(number=self._free_number())
            self._place(window)  # the whole desktop (beside the project window)
            self.insert_window(window)
        self.raise_window(window)
        window.load(template, trace)
        window.list.focus()
        self.render_messages = trace.result.messages
        self.refresh_messages(template)
        self.update_status()
