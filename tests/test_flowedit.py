"""The Flow Designer's structural edits: Blocks and Steps added, renamed, moved and deleted in the
YAML text, each one replacement verified by reading it back.

Everything outside what an operation must change stays byte for byte: the tests compare the
lines that change, and the rest of the text.
"""

import difflib
import shutil
from pathlib import Path

import pytest

from divide.run import flowedit as fe
from divide.run import flowmodel as fm

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "runner"
BOOTSTRAP = EXAMPLE / "vendor" / "divengine" / "runner" / "bin" / "run.php"
needs_runner = pytest.mark.skipif(not (shutil.which("php") and BOOTSTRAP.is_file()),
                                  reason="needs php and composer install --working-dir examples/runner")

FLOW = """\
# Orders: reviewed, then approved
id: order
blocks:
  # where the Flow starts
  main:
    description: "first: the total"
    steps:
      total:
        activity: compute_total   # sums the items
      review:   # into review and back
        call: 'review.check'
      receipt:
        activity: format_receipt
        jump: .total   # again

  review:
    steps:
      check:
        activity: mark_reviewed
        # set once reviewed
        context:
          reviewed: true    # by the activity
      approve:
        jump: "approval."
  approval:
    steps:
      ask:
        condition: needs_approval
        pause: true
      record:
        activity: record_approval
        call: review.approve
extra: kept as it is
"""


def changed(before: str, after: str) -> list[str]:
    return [line for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
            if line[:1] in "+-" and not line.startswith(("+++", "---"))]


def done(text: str, plan: fe.Plan) -> str:
    after = fm.apply(text, plan.change)
    assert plan.check(after) is None, plan.check(after)
    return after


def order(text: str) -> list[tuple[str, list[str]]]:
    return [(b.id, [s.id for s in b.steps]) for b in fm.parse(text).blocks]


# ------------------------------------------------------------------ references
def test_references_and_what_they_lead_to():
    doc = fm.parse(FLOW)
    refs = {(r.step.name, r.key): (r.block.id if r.block else None, r.target.id if r.target else None) for r in fe.references(doc)}
    assert refs == {("main.review", "call"): ("review", "check"), ("main.receipt", "jump"): ("main", "total"),
                    ("review.approve", "jump"): ("approval", "ask"), ("approval.record", "call"): ("review", "approve")}
    assert [r.step.name for r in fe.incoming(doc, doc.block("review"))] == ["main.review", "approval.record"]
    assert [r.step.name for r in fe.incoming(doc, doc.step("approval", "ask"))] == ["review.approve"]
    assert [r.step.name for r in fe.first_step_refs(doc, doc.block("approval"))] == ["review.approve"]


# ------------------------------------------------------------------ moving
def test_moving_a_step_swaps_two_units_text_for_text():
    doc = fm.parse(FLOW)
    after = done(FLOW, fe.move_step(doc, doc.step("main", "review"), -1))
    assert order(after)[0] == ("main", ["review", "total", "receipt"])
    # the same lines, the comments with their Step, nothing rewritten
    assert sorted(after.splitlines()) == sorted(FLOW.splitlines())
    assert "      review:   # into review and back\n        call: 'review.check'\n      total:\n        activity: compute_total   # sums the items\n" in after
    back = fm.parse(after)
    assert done(after, fe.move_step(back, back.step("main", "review"), 1)) == FLOW


def test_a_steps_comments_go_with_it():
    doc = fm.parse(FLOW)
    after = done(FLOW, fe.move_step(doc, doc.step("review", "check"), 1))
    assert "      approve:\n        jump: \"approval.\"\n      check:\n        activity: mark_reviewed\n        # set once reviewed\n" in after


def test_moving_blocks_keeps_the_lines_between_them():
    doc = fm.parse(FLOW)
    after = done(FLOW, fe.move_block(doc, doc.block("review"), -1))
    assert [b for b, _s in order(after)] == ["review", "main", "approval"]
    assert sorted(after.splitlines()) == sorted(FLOW.splitlines())
    assert after.endswith("extra: kept as it is\n")
    # the leading comment belongs to main and goes with it; the blank line stays where it was
    assert after.index("  # where the Flow starts\n  main:") > after.index("  review:")
    doc = fm.parse(after)
    assert done(after, fe.move_block(doc, doc.block("review"), 1)) == FLOW


def test_the_last_block_without_a_final_newline():
    text = "blocks:\n  a:\n    steps:\n      x:\n        activity: f\n  b:\n    steps:\n      y:\n        activity: g"
    doc = fm.parse(text)
    after = done(text, fe.move_block(doc, doc.block("b"), -1))
    assert after == "blocks:\n  b:\n    steps:\n      y:\n        activity: g\n  a:\n    steps:\n      x:\n        activity: f"


def test_what_cannot_move():
    doc = fm.parse(FLOW)
    with pytest.raises(fm.EditError, match="already the first"):
        fe.move_step(doc, doc.step("main", "total"), -1)
    with pytest.raises(fm.EditError, match="already the last"):
        fe.move_block(doc, doc.block("approval"), 1)
    crooked = "blocks:\n  a:\n    steps:\n      x:\n        activity: f\n      y: {activity: g}  \n      z: 1\n"
    doc = fm.parse(crooked)
    after = done(crooked, fe.move_step(doc, doc.step("a", "y"), -1))  # a flow-style Step moves as it is
    assert after.splitlines()[3] == "      y: {activity: g}  "
    broken = fm.parse(FLOW + "  bad: [\n")
    with pytest.raises(fm.EditError, match="YAML has errors"):
        fe.move_step(broken, broken.step("main", "review"), -1)


# ------------------------------------------------------------------ renaming
def test_renaming_a_step_rewrites_what_leads_to_it_in_its_quoting():
    doc = fm.parse(FLOW)
    plan = fe.rename_step(doc, doc.step("review", "check"), "inspect")
    after = done(FLOW, plan)
    assert changed(FLOW, after) == ["-      check:", "-        call: 'review.check'", "+        call: 'review.inspect'",
                                    "+      inspect:"] or sorted(changed(FLOW, after)) == sorted([
        "-        call: 'review.check'", "+        call: 'review.inspect'", "-      check:", "+      inspect:"])
    assert plan.notes == ["main.review call review.inspect"]


def test_renaming_a_step_follows_relative_targets_only_in_its_block():
    doc = fm.parse(FLOW)
    after = done(FLOW, fe.rename_step(doc, doc.step("main", "total"), "sum"))
    assert "        jump: .sum   # again\n" in after and "      sum:\n        activity: compute_total   # sums the items\n" in after


def test_renaming_a_block_rewrites_explicit_targets():
    doc = fm.parse(FLOW)
    plan = fe.rename_block(doc, doc.block("approval"), "sign_off")
    after = done(FLOW, plan)
    assert sorted(changed(FLOW, after)) == sorted(['-  approval:', '+  sign_off:', '-        jump: "approval."', '+        jump: "sign_off."'])
    doc = fm.parse(after)
    after2 = done(after, fe.rename_block(doc, doc.block("main"), "start"))
    assert changed(after, after2) == ["-  main:", "+  start:"]  # .total is relative: it stays


def test_renaming_refuses_clashes_and_bad_ids():
    doc = fm.parse(FLOW)
    with pytest.raises(fm.EditError, match="already has a Step 'review'"):
        fe.rename_step(doc, doc.step("main", "total"), "review")
    with pytest.raises(fm.EditError, match="already has a Block 'review'"):
        fe.rename_block(doc, doc.block("main"), "review")
    for bad in ("_x", "a.b", "", "a b"):
        with pytest.raises(fm.EditError, match="letters, digits"):
            fe.rename_step(doc, doc.step("main", "total"), bad)
    assert fe.rename_step(doc, doc.step("main", "total"), "total") is None


def test_renaming_with_unicode_keeps_offsets():
    text = "# déjà vu: ñandú\nblocks:\n  main:\n    steps:\n      uno:   # el primero, ñ\n        activity: f\n      dos:\n        jump: main.uno\n"
    doc = fm.parse(text)
    after = done(text, fe.rename_step(doc, doc.step("main", "uno"), "first"))
    assert after == text.replace("uno:   #", "first:   #").replace("main.uno", "main.first")


# ------------------------------------------------------------------ a Block's description
def test_a_blocks_description_set_added_and_removed():
    doc = fm.parse(FLOW)
    after = done(FLOW, fe.edit_block(doc, doc.block("main"), "first: sums"))
    assert changed(FLOW, after) == ['-    description: "first: the total"', '+    description: "first: sums"']
    doc = fm.parse(FLOW)
    after = done(FLOW, fe.edit_block(doc, doc.block("review"), "Reviews it"))
    assert changed(FLOW, after) == ['+    description: "Reviews it"']
    assert "  review:\n    description: \"Reviews it\"\n    steps:\n" in after
    doc = fm.parse(FLOW)
    after = done(FLOW, fe.edit_block(doc, doc.block("main"), ""))
    assert changed(FLOW, after) == ['-    description: "first: the total"']
    assert fe.edit_block(doc, doc.block("review"), None) is None


# ------------------------------------------------------------------ deleting
def test_deleting_a_step_that_others_lead_to_is_refused_unless_unlinked():
    doc = fm.parse(FLOW)
    with pytest.raises(fm.EditError, match=r"approval.record \(call review.approve\) lead\(s\) to review.approve"):
        fe.delete_step(doc, doc.step("review", "approve"))
    plan = fe.delete_step(doc, doc.step("review", "approve"), unlink=True)
    after = done(FLOW, plan)
    assert changed(FLOW, after) == ['-      approve:', '-        jump: "approval."', '-        call: review.approve']
    assert plan.notes == ["approval.record: call review.approve"]


def test_deleting_counts_the_comments_that_go():
    doc = fm.parse(FLOW)
    with pytest.raises(fm.EditError, match=r"main.review \(call review.check\) lead\(s\) to review.check"):
        fe.delete_step(doc, doc.step("review", "check"))
    with pytest.raises(fm.EditError, match="comment on its line"):
        fe.delete_step(doc, doc.step("main", "total"), unlink=True)  # receipt's jump .total has one
    text = FLOW.replace("jump: .total   # again", "jump: .total")
    doc = fm.parse(text)
    plan = fe.delete_step(doc, doc.step("main", "total"), unlink=True)  # it goes too
    assert plan.lost_comments == 1 and plan.notes == ["main.receipt: jump .total"]
    assert changed(text, done(text, plan)) == ["-      total:", "-        activity: compute_total   # sums the items",
                                               "-        jump: .total"]
    doc = fm.parse(FLOW.replace("      review:   # into review and back\n        call: 'review.check'\n", ""))
    plan = fe.delete_step(doc, doc.step("review", "check"))
    assert plan.lost_comments == 2
    after = done(doc.text, plan)
    assert "check:" not in after and "# by the activity" not in after and "    steps:\n      approve:" in after


def test_unlinking_never_removes_a_comment_or_empties_a_step():
    doc = fm.parse(FLOW)
    with pytest.raises(fm.EditError, match="nothing left to do"):
        fe.delete_step(doc, doc.step("review", "check"), unlink=True)  # main.review has only its call
    text = FLOW.replace("        call: review.approve", "        call: review.approve  # back")
    doc = fm.parse(text)
    with pytest.raises(fm.EditError, match="comment on its line"):
        fe.delete_step(doc, doc.step("review", "approve"), unlink=True)


def test_deleting_the_first_step_says_where_block_dot_now_leads():
    doc = fm.parse(FLOW)
    plan = fe.delete_step(doc, doc.step("approval", "ask"), unlink=True)
    assert plan.notes == ['review.approve (jump approval.) now leads to approval.record']


def test_deleting_blocks():
    doc = fm.parse(FLOW)
    with pytest.raises(fm.EditError, match="lead\\(s\\) into approval"):
        fe.delete_block(doc, doc.block("approval"))
    with pytest.raises(fm.EditError, match="review.approve would have nothing left to do"):
        fe.delete_block(doc, doc.block("approval"), unlink=True)
    text = FLOW.replace('        jump: "approval."\n', '        jump: "approval."\n        activity: approve\n')
    doc = fm.parse(text)
    plan = fe.delete_block(doc, doc.block("approval"), unlink=True)
    after = done(text, plan)
    assert [b for b, _s in order(after)] == ["main", "review"]
    assert '        jump: "approval."' not in after and after.endswith("        activity: approve\nextra: kept as it is\n")
    only = "blocks:\n  main:\n    steps:\n      a:\n        activity: f\n"
    doc = fm.parse(only)
    with pytest.raises(fm.EditError, match="needs a Block"):
        fe.delete_block(doc, doc.block("main"))
    doc = fm.parse(FLOW)
    plan = fe.delete_block(doc, doc.block("main"))  # nothing outside leads into main
    assert plan.lost_comments == 4
    assert order(done(FLOW, plan))[0][0] == "review"


# ------------------------------------------------------------------ adding
def test_adding_a_block_indented_as_its_siblings():
    doc = fm.parse(FLOW)
    plan = fe.add_block(doc, doc.block("main"), "ship", "send", {"activity": "send_parcel", "jump": "main.receipt"},
                        description="Ships it")
    after = done(FLOW, plan)
    assert [b for b, _s in order(after)] == ["main", "ship", "review", "approval"]
    assert changed(FLOW, after) == ["+  ship:", '+    description: "Ships it"', "+    steps:", "+      send:",
                                    "+        activity: send_parcel", "+        jump: main.receipt"]


def test_adding_blocks_from_scratch_with_four_spaces():
    text = "id: new\nblocks:   # none yet\n"
    doc = fm.parse(text)
    after = done(text, fe.add_block(doc, None, "main", "start", {"activity": "begin"}))
    assert after == "id: new\nblocks:   # none yet\n  main:\n    steps:\n      start:\n        activity: begin\n"
    four = "blocks:\n    a:\n        steps:\n            x:\n                activity: f\n"
    doc = fm.parse(four)
    after = done(four, fe.add_block(doc, None, "b", "y", {"pause": True}))
    assert after.endswith("    b:\n        steps:\n            y:\n                pause: true\n")
    with pytest.raises(fm.EditError, match="already has a Block"):
        fe.add_block(fm.parse(four), None, "a", "y", {"pause": True})
    with pytest.raises(fm.EditError, match="something to do"):
        fe.add_block(fm.parse(four), None, "c", "y", {})
    with pytest.raises(fm.EditError, match="no blocks"):
        fe.add_block(fm.parse("id: x\n"), None, "c", "y", {"pause": True})


# ------------------------------------------------------------------ chained, verified
def test_a_rename_and_an_edit_are_one_replacement():
    doc = fm.parse(FLOW)
    step = doc.step("review", "check")
    plan = fe.chain(doc, lambda d: fe.rename_step(d, d.step("review", "check"), "inspect"),
                    lambda d: fe.edit_step(d, d.step("review", "inspect"), {"activity": "inspect_order"}))
    after = done(FLOW, plan)
    assert sorted(changed(FLOW, after)) == sorted([
        "-        call: 'review.check'", "+        call: 'review.inspect'", "-      check:", "+      inspect:",
        "-        activity: mark_reviewed", "+        activity: inspect_order"])
    assert step.id == "check"  # the document planned on is never changed


def test_a_plan_that_reads_back_wrong_is_caught():
    doc = fm.parse(FLOW)
    plan = fe.move_step(doc, doc.step("main", "review"), -1)
    assert plan.check(FLOW) is not None  # the text as it was is not the move
    assert plan.check(FLOW.replace("# sums the items", "")) == "a comment would be lost"


def test_set_target_writes_the_explicit_form():
    doc = fm.parse(FLOW)
    after = done(FLOW, fe.set_target(doc, doc.step("main", "total"), "jump", "approval.record"))
    assert changed(FLOW, after) == ["+        jump: approval.record"]
    doc = fm.parse(after)
    again = done(after, fe.set_target(doc, doc.step("main", "total"), "jump", None))
    assert again == FLOW


@needs_runner
def test_every_operation_leaves_a_flow_runner_compiles(tmp_path):
    import asyncio
    from divide.run.flow import find_runner

    runner = find_runner(EXAMPLE)
    doc = fm.parse(FLOW)
    text = FLOW.replace("extra: kept as it is\n", "")
    steps = [
        lambda d: fe.move_block(d, d.block("review"), -1),
        lambda d: fe.rename_step(d, d.step("review", "approve"), "approve_it"),
        lambda d: fe.rename_block(d, d.block("approval"), "sign"),
        lambda d: fe.add_block(d, d.block("sign"), "ship", "send", {"activity": "send", "jump": "main."}),
        lambda d: fe.move_step(d, d.step("main", "receipt"), -1),
        lambda d: fe.delete_step(d, d.step("review", "approve_it"), unlink=True),
    ]
    for make in steps:
        doc = fm.parse(text)
        text = done(text, make(doc))
        result = asyncio.run(fm.check(runner.bootstrap, text, "f.yml", []))
        assert result.ok is True, (result.error, text)
