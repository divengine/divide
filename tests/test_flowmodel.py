"""The Flow window: a Runner Flow's structure read from its YAML, edits that change only what they must,
Runner's own compiler as the validator, and the window driven with the keyboard.

The edits are checked on the text itself: everything outside the edited span stays byte for
byte. The checks and the runs use the real Runner installed by Composer in examples/runner
(``composer install --working-dir examples/runner``); without php or that installation those
tests skip.
"""

import asyncio
import difflib
import shutil
from pathlib import Path

import pytest

from divide.run import flowmodel as fm
from divide.run.flow import find_runner

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "runner"
BOOTSTRAP = EXAMPLE / "vendor" / "divengine" / "runner" / "bin" / "run.php"
needs_runner = pytest.mark.skipif(not (shutil.which("php") and BOOTSTRAP.is_file()),
                                  reason="needs php and composer install --working-dir examples/runner")

COMMENTED = """\
# An order, with comments everywhere
id: order   # the Flow's id
description: "An order: reviewed, then approved"

blocks:
    # the entry Block
    main:
        description: first
        steps:
            total:
                activity: compute_total   # sums the items
            review:   # goes to review
                call: 'review.check'

            receipt:
                activity: format_receipt
    review:
        steps:
            check:
                activity: mark_reviewed
                context:
                    reviewed: true    # set after the activity
                    by: "ana"
            after: {jump: main.receipt}
            anchored: &a
                activity: x
extra: kept as it is
"""


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "runner"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("*.context.json", ".div"))
    return root


def changed_lines(before: str, after: str) -> list[str]:
    return [line for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
            if line[:1] in "+-" and not line.startswith(("+++", "---"))]


def edited(text: str, block: str, step: str, values: dict) -> str:
    doc = fm.parse(text)
    change = fm.edit_step(doc, doc.step(block, step), values)
    assert change is not None
    after = fm.apply(text, change)
    assert fm.verify(doc, after, block, step, values) is None
    return after


# ------------------------------------------------------------------ reading
def test_the_structure_and_where_it_is_written():
    doc = fm.parse(COMMENTED)
    assert doc.id == "order" and doc.description == "An order: reviewed, then approved" and not doc.problems
    assert [b.id for b in doc.blocks] == ["main", "review"]
    assert [s.id for s in doc.block("main").steps] == ["total", "review", "receipt"]
    review = doc.step("main", "review")
    assert review.get("call") == "review.check" and COMMENTED[review.key_start:review.key_end] == "review"
    assert doc.step("review", "check").get("context") == "{reviewed: true, by: \"ana\"}"
    assert doc.step("review", "after").style == "flow" and doc.step("review", "after").why
    assert doc.step("review", "anchored").why  # an anchor: read-only
    at = COMMENTED.index("compute_total")
    assert doc.at(at) is doc.step("main", "total")


def test_offsets_are_characters_not_bytes():
    text = "description: ñandú — ✓\nblocks:\n  main:\n    steps:\n      a:\n        activity: x\n"
    doc = fm.parse(text)
    attr = doc.step("main", "a").attrs["activity"]
    assert text[attr.value_start:attr.value_end] == "x"
    assert edited(text, "main", "a", {"activity": "y"}) == text.replace("activity: x", "activity: y")


def test_invalid_yaml_is_reported_and_never_edited():
    text = "blocks:\n  main:\n    steps:\n      a:\n        activity: [x\n"
    doc = fm.parse(text)
    assert doc.problems and not doc.editable
    with pytest.raises(fm.EditError):
        fm.edit_step(doc, doc.step("main", "a") or fm.Step("main", "a", 0, 0, 0, 0), {"activity": "y"})


# ------------------------------------------------------------------ editing in place
def test_changing_a_value_keeps_everything_else_byte_for_byte():
    after = edited(COMMENTED, "main", "total", {"activity": "compute_sum"})
    assert changed_lines(COMMENTED, after) == ["-                activity: compute_total   # sums the items",
                                               "+                activity: compute_sum   # sums the items"]
    quoted = edited(COMMENTED, "main", "review", {"call": "review.after"})
    assert changed_lines(COMMENTED, quoted) == ["-                call: 'review.check'", "+                call: review.after"]


def test_values_that_would_read_back_differently_are_quoted():
    for value, written in (("true", '"true"'), ("a: b", '"a: b"'), ("x #y", '"x #y"'), ("12", '"12"'),
                           ("billing/total", "billing/total"), ("Class::run", '"Class::run"')):
        after = edited(COMMENTED, "main", "total", {"activity": value})
        assert f"activity: {written}   # sums the items" in after
        assert fm.parse(after).step("main", "total").get("activity") == value


def test_adding_an_attribute_is_one_line_with_the_siblings_indentation():
    after = edited(COMMENTED, "main", "total", {"condition": "is_big", "pause": True})
    assert changed_lines(COMMENTED, after) == ["+                condition: is_big", "+                pause: true"]


def test_removing_an_attribute_removes_only_its_lines():
    after = edited(COMMENTED, "main", "review", {"call": "", "pause": True})  # never left empty: Runner refuses it
    assert changed_lines(COMMENTED, after) == ["-                call: 'review.check'", "+                pause: true"]
    assert "            review:   # goes to review\n" in after  # the Step's own comment stays


def refused(text: str, block: str, step: str, values: dict) -> str:
    """The edit is refused with a message: nothing is planned, so nothing changes."""
    doc = fm.parse(text)
    with pytest.raises(fm.EditError) as raised:
        fm.edit_step(doc, doc.step(block, step), values)
    return str(raised.value)


def test_removing_what_carries_a_comment_is_refused():
    for block, step, values in (("main", "total", {"activity": ""}),  # activity: compute_total   # sums the items
                                ("review", "check", {"context": ""}),  # its keys have comments
                                ("review", "check", {"context": '{by: "ana"}'})):  # reviewed's line has one
        message = refused(COMMENTED, block, step, values)
        assert "comment" in message and "Ctrl+T" in message


# ------------------------------------------------------------------ a block-style context, key by key
def test_a_changed_context_value_keeps_its_comment():
    after = edited(COMMENTED, "review", "check", {"context": '{reviewed: false, by: "ana"}'})
    assert changed_lines(COMMENTED, after) == ["-                    reviewed: true    # set after the activity",
                                               "+                    reviewed: false    # set after the activity"]


def test_a_new_context_key_is_one_line_and_the_order_stays():
    after = edited(COMMENTED, "review", "check", {"context": '{at: today, by: "bob", reviewed: true}'})
    assert changed_lines(COMMENTED, after) == ['-                    by: "ana"', '+                    by: "bob"',
                                               "+                    at: today"]


def test_a_context_key_without_a_comment_can_go_and_own_line_comments_stay():
    text = COMMENTED.replace('                    by: "ana"\n', '                    # who reviewed it\n                    by: "ana"\n')
    after = edited(text, "review", "check", {"context": "{reviewed: true}"})
    assert changed_lines(text, after) == ['-                    by: "ana"']
    assert "                    # who reviewed it\n" in after


def test_what_the_context_edit_cannot_do_in_place_is_refused():
    nested = COMMENTED.replace('                    by: "ana"\n', '                    by:\n                        name: ana\n')
    assert "Ctrl+T" in refused(nested, "review", "check", {"context": "{reviewed: true, by: bob}"})
    assert refused(COMMENTED, "review", "check", {"context": "{}"})  # empty: remove the attribute instead
    assert refused(COMMENTED, "review", "check", {"context": "[1, 2]"})


def test_unrelated_yaml_stays_byte_for_byte():
    values = {"context": '{reviewed: false, by: "ana", at: today}', "activity": "mark_checked"}
    after = edited(COMMENTED, "review", "check", values)
    step = fm.parse(COMMENTED).step("review", "check")
    assert after[:step.key_start] == COMMENTED[:step.key_start]  # everything before the Step
    assert after.endswith(COMMENTED[step.end:])  # everything after it
    assert fm.parse(after).comments.__len__() == len(fm.parse(COMMENTED).comments)
    assert changed_lines(COMMENTED, after) == [
        "-                activity: mark_reviewed", "+                activity: mark_checked",
        "-                    reviewed: true    # set after the activity", "+                    reviewed: false    # set after the activity",
        "+                    at: today"]


def test_verify_catches_a_lost_comment():
    doc = fm.parse(COMMENTED)
    lost = COMMENTED.replace("   # sums the items", "")
    assert fm.verify(doc, lost, "main", "total", {"activity": "compute_total"}) == "a comment would be lost"


def test_deleting_a_step_counts_the_comments_that_go_with_it():
    doc = fm.parse(COMMENTED)
    assert fm.comments_in(doc, *fm.step_lines(doc, doc.step("review", "check"))) == 1
    assert fm.comments_in(doc, *fm.step_lines(doc, doc.step("main", "receipt"))) == 0
    after = fm.apply(COMMENTED, fm.delete_step(doc, doc.step("main", "review")))
    assert fm.verify(doc, after, "main", "review", None) is None  # its own comment goes, as the dialog says


def test_one_dialog_is_one_replacement():
    doc = fm.parse(COMMENTED)
    change = fm.edit_step(doc, doc.step("main", "total"), {"activity": "a", "condition": "c", "jump": "review.check"})
    assert isinstance(change, fm.Change)
    assert fm.edit_step(doc, doc.step("main", "total"), {"activity": "compute_total"}) is None  # nothing changes


def test_what_cannot_be_edited_in_place_is_refused():
    doc = fm.parse(COMMENTED)
    for step in ("after", "anchored"):
        with pytest.raises(fm.EditError):
            fm.edit_step(doc, doc.step("review", step), {"activity": "y"})
    with pytest.raises(fm.EditError):
        fm.edit_step(doc, doc.step("review", "check"), {"context": "[1, 2]"})


def test_adding_and_deleting_steps():
    doc = fm.parse(COMMENTED)
    change = fm.add_step(doc, doc.block("main"), doc.step("main", "total"), "log", {"activity": "write_log", "module": "audit"})
    after = fm.apply(COMMENTED, change)
    assert changed_lines(COMMENTED, after) == ["+            log:", "+                module: audit", "+                activity: write_log"]
    assert [s.id for s in fm.parse(after).block("main").steps] == ["total", "log", "review", "receipt"]
    again = fm.parse(after)
    assert fm.apply(after, fm.delete_step(again, again.step("main", "log"))) == COMMENTED
    with pytest.raises(fm.EditError):
        fm.add_step(doc, doc.block("main"), None, "total", {"activity": "x"})  # already there
    with pytest.raises(fm.EditError):
        fm.add_step(doc, doc.block("main"), None, "_hidden", {"activity": "x"})


def test_verify_catches_an_edit_that_reads_back_wrong():
    doc = fm.parse(COMMENTED)
    wrong = COMMENTED.replace("activity: compute_total", "activity: other")
    assert fm.verify(doc, wrong, "main", "total", {"activity": "compute_sum"}) is not None
    assert fm.verify(doc, COMMENTED.replace("call: 'review.check'", "call: x.y"), "main", "total", {"activity": "compute_total"}) is None


# ------------------------------------------------------------------ targets and functions
def test_targets_are_looked_up_in_the_file():
    doc = fm.parse(COMMENTED)
    assert fm.resolve_target(doc, "main", "review.check")[1] is doc.step("review", "check")
    assert fm.resolve_target(doc, "main", ".receipt")[1] is doc.step("main", "receipt")  # its own Block
    assert fm.resolve_target(doc, "main", "review.")[1] is doc.step("review", "check")  # the first Step
    assert fm.resolve_target(doc, "main", "nope.x")[2] and fm.resolve_target(doc, "main", "review.nope")[2]
    assert fm.resolve_target(doc, "main", "nodot")[2]


def test_function_files_where_runner_looks(tmp_path):
    (tmp_path / "fn" / "billing").mkdir(parents=True)
    (tmp_path / "fn" / "greet.php").write_text("<?php return fn (array &$context) => 1;")
    (tmp_path / "fn" / "billing" / "total.php").write_text("<?php return fn (array &$context) => 1;")
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "tax.php").write_text("<?php return fn (array &$context) => 1;")
    functions = fm.functions_for(tmp_path, "fn", {"_modules": {"taxes": "elsewhere"}})
    assert functions.find("greet", None, tmp_path) == tmp_path / "fn" / "greet.php"
    assert functions.find("total", "billing", tmp_path) == tmp_path / "fn" / "billing" / "total.php"
    assert functions.find("tax", "taxes", tmp_path) == tmp_path / "elsewhere" / "tax.php"
    assert functions.find("total", None, tmp_path) is None and functions.find("greet", "billing", tmp_path) is None
    assert functions.names(None) == ["greet"] and functions.names("billing") == ["total"]
    assert functions.module_names() == ["billing", "taxes"]
    assert fm.functions_for(tmp_path, "", {"_root_folder": "fn"}).root == tmp_path / "fn"


# ------------------------------------------------------------------ Runner's verdict
def check(project: Path, text: str, root: str = "functions"):
    runner = find_runner(project)
    doc = fm.parse(text)
    result = asyncio.run(fm.check(runner.bootstrap, text, "order.yml", fm.function_names(doc)))
    return result, fm.diagnose(doc, fm.functions_for(project, root), project, result)


def lines_of(text: str, diagnostics) -> list[tuple[int, str, str]]:
    return [(text.count("\n", 0, d.start) + 1, d.severity, d.message) for d in diagnostics]


@needs_runner
def test_runner_compiles_a_good_flow(project):
    text = (project / "flows/order.yml").read_text()
    result, found = check(project, text)
    assert result.ok is True and found == []


@needs_runner
def test_runner_and_the_lookups_say_what_is_wrong_and_where(project):
    text = (project / "flows/order.yml").read_text()
    bad = (text.replace("call: review.check", "call: review.nope")
               .replace("activity: compute_total", "activity: compute_totl\n        actvity: x")
               .replace("activity: mark_reviewed", "activity: strlen"))
    result, found = check(project, bad)
    assert result.ok is False and "unknown key 'actvity' in step 'main.total'" in result.error
    shown = lines_of(bad, found)
    assert (8, "error", "Runner: unknown key 'actvity' in step 'main.total'") in shown  # at the key Runner names
    assert any(line == 10 and "Step 'nope' is not in Block 'review'" in m for line, _s, m in shown)
    assert any(line == 7 and "no file functions/compute_totl.php" in m for line, _s, m in shown)
    assert not any("strlen" in m for _l, _s, m in shown)  # a PHP function: Runner calls it


@needs_runner
def test_a_missing_module_function_is_an_error(project):
    text = (project / "flows/invoice.yml").read_text().replace("module: shipping", "module: shiping")
    _result, found = check(project, text)
    assert any(d.severity == "error" and "shiping:total: no file functions/shiping/total.php" in d.message for d in found)


@needs_runner
def test_runner_reports_a_missing_target_itself(project):
    text = (project / "flows/hello.yml").read_text().replace("      done:\n", "      done:\n        jump: gone.x\n")
    result, found = check(project, text)
    assert result.ok is False and "target block 'gone' not found" in result.error
    assert [m for _l, _s, m in lines_of(text, found)] == ["jump gone.x: Block 'gone' is not in this Flow"]  # said once


@needs_runner
def test_checking_runs_no_activity(project):
    marker = project / "ran.txt"
    (project / "functions" / "greet.php").write_text(
        f"<?php\nfile_put_contents({str(marker)!r}, 'ran');\nreturn fn (array &$context): string => 'hi';\n")
    result, found = check(project, (project / "flows/hello.yml").read_text())
    assert result.ok is True and found == [] and not marker.exists()


# ------------------------------------------------------------------ the window
async def wait(pilot, condition, what: str, tries: int = 200) -> None:
    for _ in range(tries):
        await pilot.pause(0.05)
        if condition():
            return
    pytest.fail(what)


def dialog_of(app, kind):
    return getattr(app.screen, "dialog", None) if isinstance(getattr(app.screen, "dialog", None), kind) else None


def set_root(flow: Path, root: str = "functions", context: str = "") -> None:
    from divide.ui.flow import save_flow_settings
    save_flow_settings(flow.resolve(), {"context": context, "root": root, "save": ""})


@needs_runner
async def test_edit_a_step_with_the_keyboard_and_save(project):
    from divide.app import Divide
    from divide.ui.flowmodel import FlowWindow, StepDialog

    flow = project / "flows/order.yml"
    original = flow.read_text()
    flow.write_text("# kept\n" + original.replace("activity: compute_total", "activity: compute_total  # sums"))
    before = flow.read_text()
    set_root(flow)
    app = Divide(project, [flow])
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("ctrl+t")  # the Flow window, in the code's place
        await wait(pilot, lambda: isinstance(app.active_window(), FlowWindow), "no Flow window")
        window = app.active_window()
        await wait(pilot, lambda: "compiles" in str(window.verdict.render()), "Runner gave no verdict")
        assert [n.data for n in window.flow_tree.root.children] == [("block", "main"), ("block", "review"), ("block", "approval")]
        await pilot.press("down", "down")  # main, then its first Step
        await wait(pilot, lambda: window.selected() is not None and getattr(window.selected(), "id", "") == "total", "not on main.total")
        await pilot.press("left")  # up to its Block
        await wait(pilot, lambda: getattr(window.selected(), "id", "") == "main" and not hasattr(window.selected(), "block"), "left did not go up")
        await pilot.press("right")  # into its first Step
        await wait(pilot, lambda: getattr(window.selected(), "id", "") == "total", "right did not go in")
        assert "compute_total" in str(window.inspector.render()) and "functions/compute_total.php" in str(window.inspector.render())
        await pilot.press("enter")
        await wait(pilot, lambda: dialog_of(app, StepDialog), "no Step dialog")
        dialog = dialog_of(app, StepDialog)
        assert dialog.inputs["activity"].data == "compute_total"
        dialog.inputs["activity"].data = "format_receipt"
        dialog.inputs["condition"].data = "needs_approval"
        await pilot.press("alt+k")  # OK
        code = app.window_for(flow)
        await wait(pilot, lambda: "activity: format_receipt  # sums" in code.editor.text, "the edit was not written")
        assert code.dirty
        assert changed_lines(before, code.editor.text) == [
            "-        activity: compute_total  # sums", "+        activity: format_receipt  # sums", "+        condition: needs_approval"]
        await pilot.press("f2")  # saved from the Flow window
        await wait(pilot, lambda: not code.dirty, "not saved")
        assert flow.read_text() == code.editor.text and flow.read_text().startswith("# kept\n")
        await pilot.press("ctrl+z")  # the code's undo
        await wait(pilot, lambda: "activity: compute_total  # sums" in code.editor.text, "undo did not undo the edit")
        await pilot.press("ctrl+t")  # back to the code, at the Step
        await wait(pilot, lambda: app.active_window() is code, "not back to the code")
        assert code.editor.selected_text == "total"


@needs_runner
async def test_targets_problems_and_messages(project):
    from divide.app import Divide
    from divide.ui.flowmodel import FlowWindow

    flow = project / "flows/order.yml"
    flow.write_text(flow.read_text().replace("call: approval.ask", "call: approval.nope").replace("activity: mark_reviewed", "activity: mark_reviewd"))
    set_root(flow)
    app = Divide(project, [flow])
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("ctrl+t")
        await wait(pilot, lambda: isinstance(app.active_window(), FlowWindow), "no Flow window")
        window = app.active_window()
        await wait(pilot, lambda: "error(s)" in str(window.verdict.render()), "no verdict")
        review = window.flow_tree.root.children[1]
        assert str(review.label).startswith("! review")
        labels = [str(n.label) for n in review.children]
        assert labels[0].startswith("! check") and labels[1].startswith("! approve")
        await pilot.press("alt+f9")  # Check: the problems in Messages
        await wait(pilot, lambda: app.messages_window() is not None
                   and any("Step 'nope' is not in Block 'approval'" in i.text for i in app.messages_window().items), "nothing in Messages")
        items = app.messages_window().items
        await pilot.press("escape")  # the Check box, which stays on errors
        await pilot.pause(0.2)
        assert any("mark_reviewd: no file functions/mark_reviewd.php" in i.text for i in items)

        app.raise_window(window)
        window.select(("step", "main", "review"))
        await wait(pilot, lambda: getattr(window.selected(), "name", "") == "main.review", "not on main.review")
        await pilot.press("ctrl+j")  # Ctrl+Enter (a terminal sends Ctrl+J): its call: review.check
        await wait(pilot, lambda: getattr(window.selected(), "name", "") == "review.check", "Ctrl+Enter did not go to the call's target")
        await pilot.press("ctrl+j")  # no call or jump: the activity's file (missing: said)
        await pilot.pause(0.3)
        assert isinstance(app.active_window(), FlowWindow)


@needs_runner
async def test_add_delete_and_run_the_edited_flow(project):
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox
    from divide.ui.flow import FlowDialog
    from divide.ui.flowmodel import FlowWindow, StepDialog

    flow = project / "flows/hello.yml"
    set_root(flow, "functions", '{"name": "Ana"}')
    app = Divide(project, [flow])
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("ctrl+t")
        await wait(pilot, lambda: isinstance(app.active_window(), FlowWindow), "no Flow window")
        window = app.active_window()
        window.select(("step", "main", "greet"))
        await wait(pilot, lambda: getattr(window.selected(), "name", "") == "main.greet", "not on main.greet")
        await pilot.press("insert")  # a new Step after greet
        await wait(pilot, lambda: dialog_of(app, StepDialog), "no new Step dialog")
        dialog = dialog_of(app, StepDialog)
        dialog.id_input.data = "mark"
        dialog.inputs["context"].data = "{modeled: ok}"
        await pilot.press("alt+k")
        code = app.window_for(flow)
        await wait(pilot, lambda: "      mark:\n        context: {modeled: ok}\n" in code.editor.text, "the Step was not added")
        assert getattr(window.selected(), "name", "") == "main.mark"
        await pilot.press("f2")
        await wait(pilot, lambda: not code.dirty, "not saved")

        await pilot.press("ctrl+f9")  # issue #1's Run Flow, from the Flow window
        await wait(pilot, lambda: dialog_of(app, FlowDialog), "no Run Flow dialog")
        await pilot.press("enter")
        await wait(pilot, lambda: app.output_window() is not None and "State: done" in app.output_window().view.text, "the Flow did not run")
        report = app.output_window().view.text
        assert '"modeled": "ok"' in report and '"greet": "Hello Ana"' in report

        app.raise_window(window)
        window.select(("step", "main", "mark"))
        await wait(pilot, lambda: getattr(window.selected(), "name", "") == "main.mark", "not on main.mark")
        await pilot.press("delete")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "deleting was not asked")
        await pilot.press("y")
        await wait(pilot, lambda: "mark:" not in code.editor.text, "the Step was not deleted")
        assert code.editor.text == flow.read_text().replace("      mark:\n        context: {modeled: ok}\n", "")


async def test_invalid_yaml_and_read_only_steps_are_never_rewritten(tmp_path):
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox
    from divide.ui.flowmodel import FlowWindow

    broken = tmp_path / "broken.yml"
    text = "blocks:\n  main:\n    steps:\n      b:\n        activity: [y\n"
    broken.write_text(text)
    flowing = tmp_path / "flowing.yml"
    styled = "blocks:\n  main:\n    steps:\n      a: {activity: x}  # flow style\n"
    flowing.write_text(styled)
    app = Divide(tmp_path, [flowing, broken])
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause(0.3)
        app.raise_window(app.window_for(broken))
        await pilot.press("ctrl+t")
        await wait(pilot, lambda: isinstance(app.active_window(), FlowWindow), "no Flow window")
        window = app.active_window()
        await pilot.pause(0.3)
        assert "[YAML errors]" in str(window.flow_tree.root.label)
        await pilot.press("insert")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "the YAML error was not said")
        await pilot.press("enter")
        await pilot.pause(0.2)

        app.raise_window(app.window_for(flowing))
        await pilot.press("ctrl+t")
        await wait(pilot, lambda: isinstance(app.active_window(), FlowWindow) and app.active_window().source.path == flowing, "no Flow window")
        window = app.active_window()
        window.select(("step", "main", "a"))
        await wait(pilot, lambda: getattr(window.selected(), "id", "") == "a", "not on a")
        assert "(read-only)" in str(window.flow_tree.cursor_node.label)
        await pilot.press("enter")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "read-only was not said")
        assert "flow style" in dialog_of(app, MessageBox)._text
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert app.window_for(broken).editor.text == text and app.window_for(flowing).editor.text == styled
    assert broken.read_text() == text and flowing.read_text() == styled


async def test_plain_yaml_keeps_ctrl_t_for_nothing_and_php_is_untouched(tmp_path):
    from divide.app import Divide
    from divide.ui.flowmodel import FlowWindow

    (tmp_path / "config.yml").write_text("name: x\nitems:\n  - a\n")
    app = Divide(tmp_path, [tmp_path / "config.yml"])
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("ctrl+t")
        await pilot.pause(0.3)
        assert not isinstance(app.active_window(), FlowWindow)
        assert not app.window_for(tmp_path / "config.yml").editor.checked


async def test_the_step_dialog_keeps_comments_or_says_why_not(tmp_path):
    from divide.app import Divide
    from divide.ui.dialogs import MessageBox
    from divide.ui.flowmodel import FlowWindow, StepDialog

    flow = tmp_path / "order.yml"
    flow.write_text(COMMENTED)
    app = Divide(tmp_path, [flow])
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("ctrl+t")
        await wait(pilot, lambda: isinstance(app.active_window(), FlowWindow), "no Flow window")
        window = app.active_window()
        code = app.window_for(flow)
        window.select(("step", "review", "check"))
        await wait(pilot, lambda: getattr(window.selected(), "name", "") == "review.check", "not on review.check")
        await pilot.press("enter")
        await wait(pilot, lambda: dialog_of(app, StepDialog), "no Step dialog")
        dialog = dialog_of(app, StepDialog)
        assert dialog.inputs["context"].data == '{reviewed: true, by: "ana"}'
        dialog.inputs["context"].data = '{reviewed: false, by: "ana"}'
        await pilot.press("alt+k")
        await wait(pilot, lambda: "reviewed: false    # set after the activity" in code.editor.text, "the comment was not kept")
        assert changed_lines(COMMENTED, code.editor.text) == ["-                    reviewed: true    # set after the activity",
                                                              "+                    reviewed: false    # set after the activity"]
        kept = code.editor.text

        await pilot.press("enter")  # now drop reviewed, whose line has a comment: refused, said
        await wait(pilot, lambda: dialog_of(app, StepDialog), "no Step dialog")
        dialog_of(app, StepDialog).inputs["context"].data = '{by: "ana"}'
        await pilot.press("alt+k")
        await wait(pilot, lambda: dialog_of(app, MessageBox), "the refusal was not said")
        assert "comment" in dialog_of(app, MessageBox)._text and "Ctrl+T" in dialog_of(app, MessageBox)._text
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert code.editor.text == kept
    assert flow.read_text() == COMMENTED  # never saved: the file is as it was
