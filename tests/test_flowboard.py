"""The Flow Designer: the board's layout read as text, and the board driven with the keyboard.

The layout tests need nothing but the parser. The window tests run divide on a copy of
examples/runner; those that check or run the Flow need php and the Runner installed by
Composer there (``composer install --working-dir examples/runner``) and skip without them.
"""

import shutil
from pathlib import Path

import pytest
from rich.cells import cell_len

from divide.glyphs import CP437
from divide.run import flowmodel as fm
from divide.ui.flowlayout import MARKS, Board, Overlay, glyph, step_lines

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "runner"
BOOTSTRAP = EXAMPLE / "vendor" / "divengine" / "runner" / "bin" / "run.php"
needs_runner = pytest.mark.skipif(not (shutil.which("php") and BOOTSTRAP.is_file()),
                                  reason="needs php and composer install --working-dir examples/runner")

FLOW = """\
id: order
blocks:
  main:
    description: Takes it
    steps:
      total:
        activity: compute_total
      review:
        condition: needs_approval   # large ones
        call: review.check
      receipt:
        module: billing
        activity: format_receipt
        jump: .total
  review:
    steps:
      check:
        activity: mark_reviewed
        context: {reviewed: true}
      approve:
        jump: approval.
  approval:
    steps:
      ask:
        pause: true
      record:
        call: review.approve
      lost:
        jump: main.nope
"""
CROSSINGS = set("┼╫╪╬")


def board(text: str = FLOW, width: int = 24) -> Board:
    return Board(fm.parse(text), card_width=width)


# ------------------------------------------------------------------ the layout
def test_lanes_in_order_the_first_is_the_entry():
    b = board()
    assert [lane[0] for lane in b.lanes] == [("block", "main"), ("block", "review"), ("block", "approval")]
    assert [lane[1:] for lane in b.lanes][0] == [("step", "main", "total"), ("step", "main", "review"), ("step", "main", "receipt")]
    rows = b.text().split("\n")
    top = b.boxes[("block", "main")].y
    assert "1 main" in rows[top] and "ENTRY" in rows[top] and rows[top].count("ENTRY") == 1
    assert "2 review" in rows[top] and "3 approval" in rows[top] and "Takes it" in rows[top + 1]
    xs = [b.boxes[lane[0]].x for lane in b.lanes]
    assert xs == sorted(xs)  # lanes left to right
    ys = [b.boxes[k].y for k in b.lanes[0][1:]]
    assert ys == sorted(ys)  # cards top to bottom, in execution order


def test_a_card_reads_in_runners_order_of_a_step():
    doc = fm.parse(FLOW)
    assert [k for k, _t in step_lines(doc.step("main", "review"))] == ["condition", "call"]
    assert step_lines(doc.step("main", "receipt")) == [("activity", "DO billing:format_receipt()"), ("jump", "JUMP .total")]
    assert step_lines(doc.step("review", "check")) == [("context", "SET reviewed: true"), ("activity", "DO mark_reviewed()")]
    assert step_lines(doc.step("approval", "ask")) == [("pause", "PAUSE")]
    text = board().text()
    for words in ("IF needs_approval()", "CALL review.check", "JUMP approval.", "PAUSE", "SET reviewed: true"):
        assert words in text


def test_connections_are_derived_from_the_yaml():
    b = board()
    found = {(c.source, c.key): c.target for c in b.connections}
    assert found == {
        (("step", "main", "review"), "call"): ("step", "review", "check"),
        (("step", "main", "receipt"), "jump"): ("step", "main", "total"),
        (("step", "review", "approve"), "jump"): ("step", "approval", "ask"),  # approval. is its first Step
        (("step", "approval", "record"), "call"): ("step", "review", "approve"),
        (("step", "approval", "lost"), "jump"): None,  # not in the Flow
    }
    assert [c.key for c in b.connections_of(("step", "review", "approve"))] == ["jump", "call"]  # its own, then incoming


def test_lines_never_cross_a_card_and_end_in_an_arrow_at_their_target():
    b = board()
    for conn in b.connections:
        for x, y in conn.cells:
            assert not any(box.contains(x, y) for box in b.boxes.values()), (conn.source, x, y)
        end = conn.cells[-1]
        head = b.chars[end[1]][end[0]]
        if conn.target is None:
            assert head == "?"
            continue
        box = b.boxes[conn.target]
        assert head in "►◄"
        assert end[0] in (box.x - 1, box.x + box.w) and box.y <= end[1] < box.y + box.h
        port = conn.cells[0]
        source = b.boxes[conn.source]
        assert b.chars[port[1]][source.x + source.w - 1] == ("├" if conn.key == "call" else "╞")


def test_calls_are_single_lines_jumps_double_and_shared_cells_are_crossings():
    b = board()
    single, double = set("─│┌┐└┘├┤┬┴"), set("═║╔╗╚╝╠╣╦╩")
    seen: dict[tuple[int, int], int] = {}
    for conn in b.connections:
        for cell in conn.cells[:-1]:
            seen[cell] = seen.get(cell, 0) + 1
    for conn in b.connections:
        for cell in conn.cells[:-1]:
            ch = b.chars[cell[1]][cell[0]]
            if seen[cell] > 1:
                assert ch in CROSSINGS or ch in "►◄?", (cell, ch)
            elif ch not in "►◄?":
                assert ch in (double if conn.key == "jump" else single), (conn.key, cell, ch)


def test_every_glyph_is_one_cell_of_cp437():
    text = board(FLOW.replace("Takes it", "Tómalo 中文 “pronto”")).text()
    for ch in text.replace("\n", ""):
        assert ord(ch) < 128 or ch in CP437, ch
        assert cell_len(ch) == 1
    for n in "sd":
        for e in "sd":
            assert glyph({"n": n, "e": e, "s": n, "w": e}) in CROSSINGS


def test_selection_and_emphasis_are_painted_without_colour():
    b = board()
    selected = ("step", "main", "review")
    painted = b.paint(selected, b.connections_of(selected)[0])
    box = b.boxes[selected]
    assert all(painted[box.y][x][1].startswith("sel:") for x in range(box.x, box.x + box.w))  # reverse video
    call = b.connections_of(selected)[0]
    assert all(painted[y][x][1] == "chosen" for x, y in call.cells)
    other = b.connections_of(("step", "main", "receipt"))[0]
    assert all(painted[y][x][1] != "chosen" for x, y in other.cells if (x, y) not in call.cells)


def test_a_playback_overlay_marks_steps_and_connections():
    b = board()
    overlay = Overlay(marks={("step", "main", "total"): "visited", ("step", "main", "review"): "current",
                             ("step", "approval", "ask"): "paused", ("step", "main", "receipt"): "failed"},
                      taken={(("step", "main", "review"), "call")})
    painted = b.paint(None, None, overlay)
    for key, mark in overlay.marks.items():
        box = b.boxes[key]
        assert painted[box.y][box.x + 1] == (MARKS[mark], "mark")
    call = next(c for c in b.connections if c.source == ("step", "main", "review"))
    assert all(painted[y][x][1] == "taken" for x, y in call.cells)


def test_problems_and_read_only_steps_are_flagged_in_words():
    text = FLOW.replace("      ask:\n        pause: true\n", "      ask: {pause: true}\n")
    b = Board(fm.parse(text), card_width=24,
              severity=lambda item: "error" if getattr(item, "id", "") == "lost" else None)
    shown = b.text()
    assert "!E" in shown and "RO" in shown


def test_widths():
    from divide.ui.flowboard import card_width
    assert [card_width(c) for c in (60, 78, 118, 160)] == [20, 22, 24, 28]
    for width in (20, 28):
        b = board(width=width)
        assert all(box.w == (width if key[0] == "step" else width + 2) for key, box in b.boxes.items())
        assert all(len(row) == b.width for row in b.chars)


def test_an_empty_or_unreadable_flow_draws_what_there_is():
    assert board("id: x\nblocks:\n").lanes == []
    b = board("blocks:\n  a:\n    steps: {}\n  b:\n    steps:\n      x:\n        jump: a.\n")
    assert [lane[0] for lane in b.lanes] == [("block", "a"), ("block", "b")]
    assert b.connections[0].target == ("block", "a")  # a Block without Steps: its title


# ------------------------------------------------------------------ the window
@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "runner"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("*.context.json", ".div", "vendor"))
    if BOOTSTRAP.is_file():
        (root / "vendor").symlink_to(EXAMPLE / "vendor", target_is_directory=True)
    return root


async def wait(pilot, condition, what: str, tries: int = 200) -> None:
    for _ in range(tries):
        await pilot.pause(0.05)
        if condition():
            return
    pytest.fail(what)


def dialog_of(app, kind):
    return getattr(app.screen, "dialog", None) if isinstance(getattr(app.screen, "dialog", None), kind) else None


async def open_designer(app, pilot):
    from divide.app import CM_FLOW_DESIGN
    from divide.ui.flowboard import FlowDesignWindow
    await pilot.pause(0.3)
    app.run_command(CM_FLOW_DESIGN)
    await wait(pilot, lambda: isinstance(app.active_window(), FlowDesignWindow) and app.active_window().board is not None,
               "no Flow Designer")
    return app.active_window()


def key_of(window):
    return window.key


async def test_moving_around_the_board_and_its_connections(project):
    from divide.app import Divide

    flow = project / "flows/fulfil.yml"
    app = Divide(project, [flow])
    async with app.run_test(size=(160, 44)) as pilot:
        window = await open_designer(app, pilot)
        assert window.key == ("step", "main", "total")
        await pilot.press("down")
        assert window.key == ("step", "main", "review")
        await pilot.press("up", "up")
        assert window.key == ("block", "main")  # the lane's title
        await pilot.press("right", "down")
        assert window.key == ("step", "review", "check")
        await pilot.press("end")
        assert window.key == ("step", "review", "approve")
        window.select(("step", "main", "review"))
        await pilot.press("tab")  # its call
        await wait(pilot, lambda: window.chosen() is not None, "no connection chosen")
        assert (window.chosen().key, window.chosen().target) == ("call", ("step", "review", "check"))
        assert "CALL" in str(window.inspector.render()) and "returns here" in str(window.inspector.render())
        await pilot.press("enter")  # goes there
        assert window.key == ("step", "review", "check")
        await pilot.press("tab")  # here: the call that leads in
        assert window.chosen().source == ("step", "main", "review")
        await pilot.press("escape")
        assert window.chosen() is None
        await pilot.press("backspace")  # back where it came from
        assert window.key == ("step", "main", "review")
        await pilot.press("ctrl+j")  # Ctrl+Enter: the call's target, as in the Flow window
        assert window.key == ("step", "review", "check")


@needs_runner
async def test_build_a_flow_from_scratch_connect_validate_and_run(project):
    """From an empty Flow: a Block with its first Step, a second Block, Steps, a call and a jump
    chosen on the board, a rename, a reorder; checked by Runner, saved and run."""
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox
    from divide.ui.flow import FlowDialog, save_flow_settings
    from divide.ui.flowboard import BlockDialog
    from divide.ui.flowmodel import StepDialog

    flow = project / "flows/new.yml"
    flow.write_text("# made in the Designer\nid: made\nblocks:\n")
    save_flow_settings(flow.resolve(), {"context": '{"name": "Ana", "items": [{"price": 3, "qty": 2}]}',
                                        "root": "functions", "save": ""})
    app = Divide(project, [flow])
    async with app.run_test(size=(160, 44)) as pilot:
        window = await open_designer(app, pilot)
        code = window.source
        assert window.board.lanes == []

        async def new_block(block_id, step_id, activity):
            await pilot.press("b")
            await wait(pilot, lambda: dialog_of(app, BlockDialog), "no Block dialog")
            dialog = dialog_of(app, BlockDialog)
            dialog.id_input.data, dialog.step_input.data, dialog.activity.data = block_id, step_id, activity
            await pilot.press("alt+k")
            await wait(pilot, lambda: window.key == ("step", block_id, step_id), f"{block_id} not added")

        async def new_step(step_id, **values):
            await pilot.press("insert")
            await wait(pilot, lambda: dialog_of(app, StepDialog), "no Step dialog")
            dialog = dialog_of(app, StepDialog)
            dialog.id_input.data = step_id
            for key, value in values.items():
                dialog.inputs[key].data = value
            await pilot.press("alt+k")
            await wait(pilot, lambda: window.key is not None and window.key[-1] == step_id, f"{step_id} not added")

        await new_block("main", "greet", "greet")
        await new_step("total", activity="compute_total")
        await new_block("check", "mark", "mark_reviewed")
        await new_step("again", condition="stock_short", context="{retried: true}")
        # connect: main.greet calls check.mark, chosen on the board
        window.select(("step", "main", "greet"))
        await pilot.press("c")
        assert window.connecting == ("call", ("step", "main", "greet"))
        await pilot.press("right")  # the same place in the next lane: check.mark
        await pilot.press("enter")
        await wait(pilot, lambda: "call: check.mark" in code.editor.text, "the call was not written")
        # check.again jumps to check.mark: the same lane
        window.select(("step", "check", "again"))
        await pilot.press("j", "up", "enter")
        await wait(pilot, lambda: "jump: check.mark" in code.editor.text, "the jump was not written")
        assert code.editor.text == (
            "# made in the Designer\nid: made\nblocks:\n"
            "  main:\n    steps:\n      greet:\n        activity: greet\n        call: check.mark\n"
            "      total:\n        activity: compute_total\n"
            "  check:\n    steps:\n      mark:\n        activity: mark_reviewed\n"
            "      again:\n        condition: stock_short\n        context: {retried: true}\n        jump: check.mark\n")
        assert {(c.source, c.key, c.target) for c in window.board.connections} == {
            (("step", "main", "greet"), "call", ("step", "check", "mark")),
            (("step", "check", "again"), "jump", ("step", "check", "mark"))}
        # rename check.mark: the call and the jump follow
        window.select(("step", "check", "mark"))
        await pilot.press("enter")
        await wait(pilot, lambda: dialog_of(app, StepDialog), "no Step dialog")
        dialog_of(app, StepDialog).id_input.data = "review"
        await pilot.press("alt+k")
        await wait(pilot, lambda: "call: check.review" in code.editor.text and "jump: check.review" in code.editor.text,
                   "the references did not follow the rename")
        assert "      review:\n        activity: mark_reviewed\n" in code.editor.text
        # one undo undoes the whole rename
        await pilot.press("ctrl+z")
        await wait(pilot, lambda: "call: check.mark" in code.editor.text and "jump: check.mark" in code.editor.text, "undo")
        await pilot.press("ctrl+y")
        await wait(pilot, lambda: "call: check.review" in code.editor.text, "redo")
        # reorder: total before greet (Ctrl+Up)
        window.select(("step", "main", "total"))
        await pilot.press("ctrl+up")
        await wait(pilot, lambda: code.editor.text.index("      total:") < code.editor.text.index("      greet:"), "not moved")
        assert window.key == ("step", "main", "total")
        # Runner compiles it, it is saved and run
        await pilot.press("alt+f9")
        await wait(pilot, lambda: "compiles" in str(window.verdict.render()), "Runner gave no verdict")
        await pilot.press("escape")
        app.raise_window(window)
        await pilot.press("f2")
        await wait(pilot, lambda: not code.dirty, "not saved")
        assert flow.read_text() == code.editor.text and flow.read_text().startswith("# made in the Designer\n")
        await pilot.press("ctrl+f9")
        await wait(pilot, lambda: dialog_of(app, FlowDialog), "no Run Flow dialog")
        await pilot.press("enter")
        await wait(pilot, lambda: app.output_window() is not None and "State: done" in app.output_window().view.text,
                   "the Flow did not run")
        report = app.output_window().view.text
        assert '"greet": "Hello Ana"' in report and '"total": 6' in report and '"retried": true' in report

        # moving a Block to the front changes the entry: asked
        app.raise_window(window)
        window.select(("block", "check"))
        await pilot.press("ctrl+left")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "the entry change was not asked")
        assert "check" in str(dialog_of(app, MessageBox)._text)
        await pilot.press("n")
        await pilot.pause(0.3)
        assert code.editor.text.index("  main:") < code.editor.text.index("  check:")


async def test_deleting_what_others_lead_to_says_so_and_unlinks(project):
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox

    flow = project / "flows/fulfil.yml"
    flow.write_text(flow.read_text().replace("call: review.check          # and back here", "call: review.check"))
    before = flow.read_text()
    app = Divide(project, [flow])
    async with app.run_test(size=(160, 44)) as pilot:
        window = await open_designer(app, pilot)
        code = window.source
        window.select(("step", "stock", "reserve"))
        await pilot.press("delete")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "deleting was not asked")
        said = dialog_of(app, MessageBox)._text
        assert "main.stock (call stock.reserve)" in said and "stock.short (jump .reserve)" in said
        await pilot.press("n")
        await pilot.pause(0.2)
        assert code.editor.text == before
        # main.stock would be left with nothing to do: refused, nothing changed
        await pilot.press("delete")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "deleting was not asked")
        await pilot.press("y")
        await wait(pilot, lambda: dialog_of(app, MessageBox) and "nothing left to do" in dialog_of(app, MessageBox)._text,
                   "not refused")
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert code.editor.text == before
        # a Block another one calls: its call goes with it, one undo brings both back
        window.select(("block", "review"))
        await pilot.press("delete")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "deleting was not asked")
        assert "main.review (call review.check)" in dialog_of(app, MessageBox)._text
        await pilot.press("y")
        await wait(pilot, lambda: "\n  review:\n" not in code.editor.text, "not deleted")
        assert "call: review.check" not in code.editor.text and "      review:\n        condition: needs_approval   # only large orders\n      stock:" in code.editor.text
        await pilot.press("ctrl+z")
        await wait(pilot, lambda: code.editor.text == before, "one undo did not bring it back")


async def test_invalid_yaml_keeps_the_last_design_read_only(project):
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox

    flow = project / "flows/fulfil.yml"
    app = Divide(project, [flow])
    async with app.run_test(size=(120, 34)) as pilot:
        window = await open_designer(app, pilot)
        ed = window.source.editor
        lanes = [lane[0] for lane in window.board.lanes]
        at = ed.text.index("      approve:") + len("      approve:")
        ed.insert(" [", ed.document.get_location_from_index(at))
        await wait(pilot, lambda: window.read_only, "not read-only")
        broken = ed.text
        assert [lane[0] for lane in window.board.lanes] == lanes  # the last design that parsed
        assert "READ-ONLY" in str(window.bar.render())
        window.board_view.focus()
        for keys in (("b",), ("insert",), ("delete",), ("ctrl+down",), ("c",), ("enter",)):
            await pilot.press(*keys)
            await pilot.pause(0.2)
            if dialog_of(app, MessageBox):
                assert "Fix the YAML" in dialog_of(app, MessageBox)._text
                await pilot.press("enter")
                await pilot.pause(0.1)
        assert ed.text == broken  # never rewritten
        await pilot.press("ctrl+t")  # to the code, at the problem
        await wait(pilot, lambda: app.active_window() is window.source, "not in the code")
        ed.undo()
        await wait(pilot, lambda: not window.read_only, "not editable again")


async def test_views_switch_and_ctrl_t_remembers_the_board(project):
    from divide.app import Divide
    from divide.ui.flowboard import FlowDesignWindow
    from divide.ui.flowmodel import FlowWindow

    flow = project / "flows/fulfil.yml"
    app = Divide(project, [flow], palette="phosphor-amber")
    async with app.run_test(size=(80, 24)) as pilot:
        window = await open_designer(app, pilot)
        await wait(pilot, lambda: window.has_class("narrow"), "not narrow")  # the inspector under the board
        window.select(("step", "stock", "short"))
        await pilot.press("ctrl+d")
        await wait(pilot, lambda: isinstance(app.active_window(), FlowWindow), "no Flow window")
        tree = app.active_window()
        await wait(pilot, lambda: getattr(tree.selected(), "name", "") == "stock.short", "the tree is not at stock.short")
        await pilot.press("ctrl+d")
        await wait(pilot, lambda: app.active_window() is window, "not back to the board")
        await pilot.press("ctrl+t")
        await wait(pilot, lambda: app.active_window() is window.source, "not the code")
        assert window.source.editor.selected_text == "short"
        await pilot.press("ctrl+t")  # the last view: the board
        await wait(pilot, lambda: isinstance(app.active_window(), FlowDesignWindow), "Ctrl+T did not reopen the board")
        styles = window.board.paint(window.key)
        box = window.board.boxes[window.key]
        assert styles[box.y][box.x][1].startswith("sel:")


# ------------------------------------------------------------------ found in review
def test_more_arrows_than_rows_make_the_card_taller_never_share_a_row():
    text = ("blocks:\n  main:\n    steps:\n      a:\n        activity: x\n"
            + "".join(f"      s{n}:\n        jump: .a\n" for n in range(5)))
    b = board(text)
    a = b.boxes[("step", "main", "a")]
    assert a.h >= 6  # five arrows, each on its own row
    heads = [c.cells[-1] for c in b.connections]
    assert len(set(heads)) == 5
    cells: dict = {}
    for conn in b.connections:
        for cell in conn.cells:
            cells.setdefault(cell, []).append(conn)
    assert all(b.chars[y][x] in CROSSINGS for (x, y), cs in cells.items() if len(cs) > 1)


def test_a_missing_target_is_a_question_mark_at_its_port_alone():
    text = FLOW + "      far:\n        jump: main.total\n"
    b = board(text)
    lost = next(c for c in b.connections if c.target is None)
    assert len(lost.cells) == 1 and b.chars[lost.cells[0][1]][lost.cells[0][0]] == "?"
    assert not any(lost.cells[0] in c.cells for c in b.connections if c is not lost)


def test_duplicate_ids_are_not_drawn_and_navigation_reaches_every_card():
    text = "blocks:\n  main:\n    steps:\n      a:\n        activity: x\n      a:\n        activity: y\n      b:\n        activity: z\n  main:\n    steps:\n      c:\n        pause: true\n"
    b = board(text)
    assert b.lanes == [[("block", "main"), ("step", "main", "a"), ("step", "main", "b")]]
    assert b.duplicates == ["main", "main.a"]


async def test_renaming_a_step_that_jumps_to_itself_keeps_the_jump_on_it(project):
    from divide.app import Divide
    from divide.ui.flowmodel import StepDialog

    flow = project / "flows/loop.yml"
    flow.write_text("blocks:\n  main:\n    steps:\n      retry:\n        activity: greet\n        jump: .retry\n")
    app = Divide(project, [flow])
    async with app.run_test(size=(120, 34)) as pilot:
        window = await open_designer(app, pilot)
        window.select(("step", "main", "retry"))
        await pilot.press("enter")
        await wait(pilot, lambda: dialog_of(app, StepDialog), "no Step dialog")
        dialog_of(app, StepDialog).id_input.data = "again"
        await pilot.press("alt+k")
        await wait(pilot, lambda: "again:" in window.source.editor.text, "not renamed")
        assert window.source.editor.text == "blocks:\n  main:\n    steps:\n      again:\n        activity: greet\n        jump: .again\n"
        await pilot.press("ctrl+z")  # the rename alone, in one undo
        await wait(pilot, lambda: window.source.editor.text == flow.read_text(), "one undo did not undo it")


async def test_removing_a_steps_only_connection_is_refused_everywhere(project):
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox
    from divide.ui.flowmodel import StepDialog

    flow = project / "flows/fulfil.yml"
    before = flow.read_text()
    app = Divide(project, [flow])
    async with app.run_test(size=(160, 44)) as pilot:
        window = await open_designer(app, pilot)
        code = window.source

        async def refused():
            await wait(pilot, lambda: dialog_of(app, MessageBox) and "something to do" in dialog_of(app, MessageBox)._text,
                       "not refused")
            await pilot.press("enter")
            await pilot.pause(0.2)
            assert code.editor.text == before

        window.select(("step", "main", "stock"))  # only: call stock.reserve
        await pilot.press("tab", "delete")  # the chosen connection
        await wait(pilot, lambda: dialog_of(app, MessageBox), "removing was not asked")
        await pilot.press("y")
        await refused()
        window.select(("step", "main", "stock"))
        await pilot.press("c", "delete")  # Del while choosing the target
        await refused()
        window.select(("step", "main", "stock"))
        await pilot.press("enter")  # the Step dialog with its call emptied
        await wait(pilot, lambda: dialog_of(app, StepDialog), "no Step dialog")
        dialog_of(app, StepDialog).inputs["call"].data = ""
        await pilot.press("alt+k")
        await refused()


async def test_a_click_on_a_pinned_lane_title_after_scrolling_selects_its_block(project):
    from divide.app import Divide

    flow = project / "flows/fulfil.yml"
    app = Divide(project, [flow])
    async with app.run_test(size=(80, 30)) as pilot:
        window = await open_designer(app, pilot)
        view = window.board_view
        window.select(("step", "main", "receipt"))  # the last card: the board scrolls down
        await wait(pilot, lambda: view.scroll_offset.y > 0, "the board did not scroll")
        title = window.board.boxes[("block", "main")]
        await pilot.click(view, offset=(title.x - view.scroll_offset.x + 2, title.y))
        await wait(pilot, lambda: window.key == ("block", "main"), f"the click selected {window.key}")
        window.select(("step", "main", "receipt"))  # scrolled down again: a card is still found where it is drawn
        await wait(pilot, lambda: view.scroll_offset.y > 0, "the board did not scroll")
        await pilot.pause(0.2)
        visible = [key for key in window.board.lanes[0][1:] if key != window.key
                   and window.board.header_height <= window.board.boxes[key].y + 1 - view.scroll_offset.y < view.size.height]
        assert visible, "no other card shows below the titles"
        card = window.board.boxes[visible[-1]]
        await pilot.click(view, offset=(card.x - view.scroll_offset.x + 2, card.y + 1 - view.scroll_offset.y))
        await wait(pilot, lambda: window.key == visible[-1], f"the click selected {window.key}")


def test_each_block_is_a_column_of_alternating_colour_holding_its_cards():
    """No frames, no rules: each Block a column of its own surface, from its left edge to the next
    one's and down to the end, neighbours alternating; its title on it; each card a surface above it."""
    b = board()
    for i, lane in enumerate(b.lanes):
        title = b.boxes[lane[0]]
        colour = "lane" if i % 2 == 0 else "lane.alt"
        assert all(b.fill[y][title.x] == colour for y in range(b.height))  # the whole height
        assert b.fill[title.y][title.x + 2] == colour  # the title has no surface of its own
        for key in lane[1:]:
            box = b.boxes[key]
            assert all(b.fill[y][x] == "card" for y in range(box.y, box.y + box.h) for x in range(box.x, box.x + box.w))
    first, second = b.boxes[b.lanes[0][0]], b.boxes[b.lanes[1][0]]
    assert {b.fill[3][x] for x in range(first.x, second.x - 1)} <= {"lane", "card"}  # its gutter is its own
    assert b.fill[3][second.x - 1] == "lane.alt"
    assert not any(ch in "┌┐└┘" for ch in b.text().split("\n")[0])  # no frame
    assert b.filler() == b.fill[-1]
    review = b.boxes[("step", "main", "review")]
    assert b.styles[review.y + 1][review.x + 2] == "kw.condition" and b.styles[review.y + 2][review.x + 2] == "kw.call"


async def test_the_board_draws_its_surfaces_from_the_theme(project):
    from divide.app import Divide

    for palette in ("free-pascal", "phosphor-green", "phosphor-amber-black"):  # a black window too
        app = Divide(project, [project / "flows/fulfil.yml"], palette=palette)
        async with app.run_test(size=(120, 34)) as pilot:
            window = await open_designer(app, pilot)
            surfaces = window.board_view.surfaces()
            colours = [surfaces[k].bgcolor for k in ("lane", "lane.alt", "card")]
            assert all(colours) and len(set(colours)) == 3, (palette, colours)
            window_bg = window.board_view.styles.background.rich_color
            assert window_bg not in colours  # neither column is the window's own



# ------------------------------------------------------------------ the panel and the context
async def test_the_panel_holds_the_summary_and_says_when_a_target_is_chosen(project):
    from divide.app import Divide

    app = Divide(project, [project / "flows/fulfil.yml"])
    async with app.run_test(size=(120, 34)) as pilot:
        window = await open_designer(app, pilot)
        summary = str(window.summary.render())
        assert "4 Block(s), 13 Step(s)" in summary and "starts at main" in summary and "CALL returns" in summary
        assert not window.bar.display  # nothing going on: no message
        window.select(("step", "stock", "short"))
        await pilot.press("j")
        await wait(pilot, lambda: window.bar.display, "no message while choosing a target")
        said = str(window.bar.render())
        assert "JUMP from stock.short" in said and "Esc cancels" in said
        assert window.bar.region.x > window.board_view.region.x + window.board_view.region.width - 1  # in the panel
        await pilot.press("escape")
        await wait(pilot, lambda: not window.bar.display, "the message stayed")


def test_a_context_as_data_and_back():
    for text in ("{approved: true, by: ana, n: 3, x: 1.5, s: \"a b\", l: [1, two], m: {k: null}}",
                 "  a: yes\n  b:\n    c: 2\n  d:\n    - x\n    - y", "{}", ""):
        data = fm.context_data(text)
        assert fm.context_data(fm.render_context(data)) == data
    assert fm.context_data("{a: yes, b: '1', c: ~, d: 017}") == {"a": True, "b": "1", "c": None, "d": 17}
    assert fm.render_context({"k": "a: b", "t": "true", "n": None, "l": []}) == '{k: "a: b", t: "true", n: null, l: []}'
    with pytest.raises(fm.EditError):
        fm.context_data("[1, 2]")


async def test_x_edits_a_steps_context_as_a_tree_or_json_in_one_undo(project):
    from divide.app import Divide
    from divide.ui.flowcontext import ContextDialog
    from divide.ui.jsontree import EditItemDialog

    flow = project / "flows/fulfil.yml"
    before = flow.read_text()
    app = Divide(project, [flow])
    async with app.run_test(size=(120, 34)) as pilot:
        window = await open_designer(app, pilot)
        code = window.source
        window.select(("step", "stock", "short"))
        await pilot.press("x")
        await wait(pilot, lambda: dialog_of(app, ContextDialog), "no context dialog")
        dialog = dialog_of(app, ContextDialog)
        assert dialog.value == {"retried": True} and dialog.mode == "tree"
        await pilot.press("insert")  # a new key, with the JSON editor's item dialog
        await wait(pilot, lambda: dialog_of(app, EditItemDialog), "no item dialog")
        item = dialog_of(app, EditItemDialog)
        item.key_input.data, item.value_input.data = "by", "ana maria"
        await pilot.press("enter")
        await wait(pilot, lambda: dialog_of(app, ContextDialog) and "by" in dialog_of(app, ContextDialog).value, "not added")
        await pilot.press("alt+j")  # the same value as JSON text
        await wait(pilot, lambda: dialog.mode == "text", "not the JSON view")
        assert '"by": "ana maria"' in dialog.json_text.text
        dialog.json_text.load_text('{"retried": true, "by": "ana maria", "tries": [1, 2]}')
        await pilot.press("alt+k")
        await wait(pilot, lambda: 'context: {retried: true, by: "ana maria", tries: [1, 2]}' in code.editor.text, "not written")
        await pilot.press("ctrl+z")
        await wait(pilot, lambda: code.editor.text == before, "one undo did not undo it")
        window.select(("step", "stock", "short"))
        await pilot.press("x")  # invalid JSON keeps the text, Cancel changes nothing
        await wait(pilot, lambda: dialog_of(app, ContextDialog), "no context dialog")
        dialog = dialog_of(app, ContextDialog)
        await pilot.press("alt+j")
        await wait(pilot, lambda: dialog.mode == "text", "not the JSON view")
        dialog.json_text.load_text("{not json")
        await pilot.press("alt+r")
        await pilot.pause(0.2)
        assert dialog.mode == "text"
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert code.editor.text == before


async def test_the_step_dialog_edits_its_context_with_the_same_dialog(project):
    from divide.app import Divide
    from divide.ui.flowcontext import ContextDialog
    from divide.ui.flowmodel import StepDialog

    app = Divide(project, [project / "flows/fulfil.yml"])
    async with app.run_test(size=(120, 34)) as pilot:
        window = await open_designer(app, pilot)
        window.select(("step", "review", "approve"))
        await pilot.press("enter")
        await wait(pilot, lambda: dialog_of(app, StepDialog), "no Step dialog")
        step_dialog = dialog_of(app, StepDialog)
        await pilot.press("alt+e")
        await wait(pilot, lambda: dialog_of(app, ContextDialog), "no context dialog")
        context = dialog_of(app, ContextDialog)
        assert context.value == {"approved": True}
        context.value["by"] = "ana"
        await pilot.press("alt+k")
        await wait(pilot, lambda: dialog_of(app, StepDialog), "not back in the Step dialog")
        assert step_dialog.inputs["context"].data == "{approved: true, by: ana}"
