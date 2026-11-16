"""How Div rendered a template: its mutations, one by one (UI-independent).

Rendering in Div is not a top-down pass over lines: the template is mutated
again and again (conditions decided, includes pasted in, lists unrolled,
values replaced...) until a whole cycle changes nothing, a fixed point. Parts
are parsed by sub-engines of their own (each item of a list, each condition's
expression), deeper in the parse level.

The bridge's "trace" operation renders as usual with a subclass of Div whose
``logger()`` (Div's log mode calls it at every step of the parser) notes the
step, the engine, its parse level and the template's source whenever it
changed. ``mutations`` turns those notes into a list of what changed and why:
Div's own words for the steps that ran since the engine's previous note.
"""

from __future__ import annotations

from divide.i18n import _, ngettext

import re
from dataclasses import dataclass, field
from pathlib import Path

from divide.run.render import RenderMessage, RenderResult, _call_bridge, references

TIMEOUT = 60.0
_START = ("Parsing all...", "Parsing from the original source", "Parsing with '")  # Div's log: not translated
_CYCLE = "Template | size:"
_END = "Parser duration:"
_QUIET = (_CYCLE, "Parsing all...", "Parsing from the original source", "Parsing with '", _END)


@dataclass(frozen=True)
class Event:
    engine: int
    level: int
    message: str
    src: str | None  # the source when it changed since this engine's last event


@dataclass
class Mutation:
    """One row of the trace.

    ``kind``: "start" (an engine begins parsing ``after``), "change" (``before``
    became ``after`` because of ``causes``), "end" (the engine reached its
    fixed point; ``after`` is its result) or "output" (what the render returned)."""

    kind: str
    engine: int
    level: int
    cycle: int
    before: str
    after: str
    causes: list[str] = field(default_factory=list)
    context: str = ""  # for a start: what the parent engine was doing
    run: int = 0  # which parse this belongs to: 1 the template, 2... its sub-parses, in order

    @property
    def label(self) -> str:
        if self.kind == "start":
            return ("Template" if self.level <= 1 else "Sub-parse") + (f": {self.context}" if self.context else "")
        if self.kind == "output":
            return _('Output: what Div returns')
        if self.kind == "end":
            return ngettext("Fixed point: nothing changes after {n} cycle", "Fixed point: nothing changes after {n} cycles",
                            self.cycle).format(n=self.cycle)
        return cause_text(self.causes)

    @property
    def delta(self) -> int:
        return len(self.after) - len(self.before)

    def changed(self) -> tuple[tuple[int, int], tuple[int, int]]:
        """The part that differs: (start, end) in ``before`` and in ``after``."""
        return changed_span(self.before, self.after)


@dataclass
class RenderTrace:
    result: RenderResult
    mutations: list[Mutation]
    truncated: bool = False
    events: int = 0


def changed_span(before: str, after: str) -> tuple[tuple[int, int], tuple[int, int]]:
    """The common prefix and suffix left out: what was there and what is now."""
    limit = min(len(before), len(after))
    head = 0
    while head < limit and before[head] == after[head]:
        head += 1
    tail = 0
    while tail < limit - head and before[-1 - tail] == after[-1 - tail]:
        tail += 1
    return (head, len(before) - tail), (head, len(after) - tail)


def _step(message: str) -> str:
    text = message.strip()
    text = re.sub(r" in '.*$", "", text, flags=re.S)  # "Parsing match: x in '<the source>'"
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^Parsing (the )?", "", text)
    text = re.sub(r"\s*\(from \d+ to \d+\)", "", text)
    text = re.sub(r"\.{2,}$", "", text).strip()
    return text[:1].upper() + text[1:] if text else message


def cause_text(causes: list[str]) -> str:
    """The steps behind a change, the most telling last: "conditions > condition {$x} > 0 > true"."""
    items = sum(m.startswith("Parsing item ") for m in causes)
    steps = [m for m in causes if not m.startswith(_QUIET + ("Parsing item ", "Checking logical order"))]
    if not steps:
        return _('(between cycles)')
    detail = list(dict.fromkeys(_step(m) for m in steps))
    # "Parsing conditions..." then "Parsing condition: x" then "The condition x is true": keep the last two
    text = " > ".join(detail[-2:])
    if items:
        text += " (" + ngettext("{n} item", "{n} items", items).format(n=items) + ")"
    return text


def mutations(events: list[Event]) -> list[Mutation]:
    """The trace as rows: starts, changes (with their causes) and fixed points."""
    rows: list[Mutation] = []
    runs: dict[int, int] = {}  # engine -> its current parse
    src: dict[int, str] = {}
    pending: dict[int, list[str]] = {}
    fresh: dict[int, bool] = {}
    cycle: dict[int, int] = {}
    last_of_level: dict[int, str] = {}  # what each level was last doing (context for a sub-engine)
    for e in events:
        eid = e.engine
        current = src.get(eid, "")
        changed = e.src is not None and e.src != current
        if e.message.startswith("Parsing all..."):
            src[eid] = e.src if e.src is not None else current
            fresh[eid], pending[eid], cycle[eid] = True, [], 0
            context = _step(last_of_level.get(e.level - 1, "")) if e.level > 1 else ""
            runs[eid] = sum(r.kind == "start" for r in rows) + 1
            rows.append(Mutation("start", eid, e.level, 0, "", src[eid], context=context, run=runs[eid]))
            continue
        if eid not in runs:
            continue  # a clone Div uses on a value (a match): it never parses on its own
        if fresh.get(eid) and (changed or e.message.startswith(_START)):
            if changed:  # still starting: from the original source, with its item
                src[eid] = e.src  # type: ignore[assignment]
                rows[_last_start(rows, eid)].after = src[eid]
            if not e.message.startswith(_START):
                fresh[eid] = False
                pending[eid] = [e.message]
            continue
        fresh[eid] = False
        if changed:
            rows.append(Mutation("change", eid, e.level, cycle.get(eid, 0), current, e.src,  # type: ignore[arg-type]
                                 list(pending.get(eid, [])), run=runs[eid]))
            src[eid] = e.src  # type: ignore[assignment]
            pending[eid] = []
        if e.message.startswith(_CYCLE):
            cycle[eid] = cycle.get(eid, 0) + 1
        if e.message.startswith(_END):
            rows.append(Mutation("end", eid, e.level, cycle.get(eid, 0), src.get(eid, ""), src.get(eid, ""), run=runs[eid]))
            pending[eid] = []
            continue
        pending.setdefault(eid, []).append(e.message)
        if not e.message.startswith(_QUIET):
            last_of_level[e.level] = e.message
    return rows


def _last_start(rows: list[Mutation], engine: int) -> int:
    for index in range(len(rows) - 1, -1, -1):
        if rows[index].kind == "start" and rows[index].engine == engine:
            return index
    raise LookupError(engine)


async def trace_render(
    engine: Path,
    template: Path,
    code: str,
    data: str | None,
    *,
    cwd: Path,
    php: str | None = None,
    timeout: float = TIMEOUT,
) -> RenderTrace:
    """Render ``code`` as ``render`` does, keeping every mutation Div made."""
    import time

    request = {"engine": str(engine), "op": "trace", "path": str(template), "code": code, "data": data}
    started = time.monotonic()
    reply = await _call_bridge(request, cwd=cwd, php=php, timeout=timeout)
    result = RenderResult(
        output=reply.get("output") or "",
        messages=[RenderMessage(m.get("level", "?"), m.get("text", "")) for m in reply.get("messages", [])],
        fatal=bool(reply.get("fatal")),
        version=reply.get("version"),
        seconds=time.monotonic() - started,
    )
    if data and references(data):
        result.messages.append(RenderMessage("NOTE", "the data uses $references: Div decodes a data file before any variable exists"))
    trace = reply.get("trace") or {}
    events = [
        Event(int(e.get("engine", 0)), int(e.get("level", 0)), str(e.get("message", "")), e.get("src"))
        for e in trace.get("events", []) if isinstance(e, dict)
    ]
    return RenderTrace(result, mutations(events), bool(trace.get("truncated")), len(events))
