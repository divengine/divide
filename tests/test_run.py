"""Running PHP scripts and debugging them with Xdebug.

The debugger tests need Xdebug: loaded by php.ini, or DIVIDE_XDEBUG naming an
``xdebug.so`` (it loads with ``-d zend_extension=``). Skipped otherwise.
"""

import asyncio
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from divide.app import Divide
from divide.run import dbgp
from divide.run.script import php_messages, run_script, split_args
from divide.ui.progress import ProgressScreen
from divide.ui.runner import CallStackWindow, WatchesWindow
from divide.ui.windows import MessagesWindow

PHP = shutil.which("php")
needs_php = pytest.mark.skipif(PHP is None, reason="php not in PATH")
XDEBUG = os.environ.get("DIVIDE_XDEBUG")


def _xdebug_loaded() -> bool:
    if PHP is None:
        return False
    if XDEBUG and Path(XDEBUG).is_file():
        return True
    return "xdebug" in subprocess.run([PHP, "-m"], capture_output=True, text=True).stdout.lower().split()


needs_xdebug = pytest.mark.skipif(not _xdebug_loaded(), reason="needs Xdebug (php.ini or DIVIDE_XDEBUG=path/xdebug.so)")

SCRIPT = """<?php
function total(array $xs): int {
    $sum = 0;
    foreach ($xs as $x) {
        $sum += $x;
    }
    return $sum;
}
$items = [1, 2, 3];
echo "args: " . implode(",", array_slice($argv, 1)) . "\\n";
$t = total($items);
echo "total $t\\n";
"""


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    settings = {"lsp": {"php": "off"}}
    if XDEBUG:
        settings["xdebug"] = XDEBUG
    (home / "divide").mkdir(parents=True)
    (home / "divide" / "config.json").write_text(json.dumps(settings))


async def settle(pilot, n=6):
    for _ in range(n):
        await pilot.pause()


async def until(pilot, pred, tries=200):
    for _ in range(tries):
        if pred():
            return True
        await pilot.pause(0.05)
    return False


def test_php_errors_become_messages():
    stderr = (
        "Warning: Undefined variable $nope in /p/a.php on line 3\n"
        "PHP Deprecated:  old in /p/b.php on line 7\n"
        "Fatal error: Uncaught RuntimeException: boom in /p/a.php:5\n"
        "Stack trace:\n#0 /p/a.php(6): f()\n#1 {main}\n  thrown in /p/a.php on line 5\n"
        "a line of the script's own\n"
    )
    found = php_messages(stderr)
    assert [(m.level, m.text, str(m.file), m.line) for m in found] == [
        ("warning", "Warning: Undefined variable $nope", "/p/a.php", 3),
        ("warning", "Deprecated: old", "/p/b.php", 7),
        ("error", "Fatal error: Uncaught RuntimeException: boom", "/p/a.php", 5),
    ]
    assert split_args('one "two words" three') == ["one", "two words", "three"]
    assert split_args('broken "quote') == ["broken", '"quote']


def test_dbgp_packets_and_values():
    buffer = bytearray(b"5\0<a/>x\0" + b"3\0<b")
    assert dbgp.packets(buffer) == [b"<a/>x"[:5]] and buffer == bytearray(b"3\0<b")
    xml = (
        '<response xmlns="urn:debugger_protocol_v1"><property name="$items" type="array" numchildren="2">'
        '<property name="0" type="int"><![CDATA[1]]></property>'
        '<property name="name" type="string" encoding="base64"><![CDATA[SXQncw==]]></property></property>'
        '<property name="$shop" type="object" classname="Shop"/><property name="$x" type="uninitialized"/></response>'
    )
    props = ET.fromstring(xml).findall("d:property", dbgp.NS)
    values = [dbgp.variable(p) for p in props]
    assert values[0].lines() == ["$items = array(2)", "  0 = 1", "  name = 'It\\'s'"]
    assert [v.value for v in values[1:]] == ["Shop", "(not set)"]
    assert dbgp.uri_path("file:///a%20b/c.php") == Path("/a b/c.php") and dbgp.uri_path("dbgp://1") is None


@needs_php
async def test_run_script_and_stop(tmp_path):
    script = tmp_path / "a.php"
    script.write_text(SCRIPT)
    result = await run_script(script, ["x", "y z"])
    assert result.output == "args: x,y z\ntotal 6\n" and result.exit_code == 0 and not result.failed
    slow = tmp_path / "slow.php"
    slow.write_text("<?php echo 'go'; flush(); sleep(30);")
    task = asyncio.ensure_future(run_script(slow))
    await asyncio.sleep(0.5)
    task.cancel()
    result = await task
    assert result.stopped and result.output == "go"


@needs_php
async def test_ctrl_f9_runs_the_script(tmp_path):
    script = tmp_path / "a.php"
    script.write_text(SCRIPT)
    app = Divide(tmp_path, [script])
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        await pilot.press("ctrl+f9")
        assert await until(pilot, lambda: app.output_window() is not None and "total 6" in app.output_window().view.text)
        out = app.output_window()
        assert out.title == "Output: a.php" and "exit code 0" in out.summary
        assert await until(pilot, lambda: not isinstance(app.screen, ProgressScreen))  # success: it closes itself

        # an error: the box waits, PHP's messages jump to their line
        win = app.window_for(script.resolve())
        app.raise_window(win)
        win.editor.move_cursor((11, 0))
        win.editor.insert("echo $nope;\nthrow new Exception('boom');\n")
        await pilot.press("ctrl+f9")
        assert await until(pilot, lambda: isinstance(app.screen, ProgressScreen) and not app.screen.dialog.running)
        dialog = app.screen.dialog
        assert dialog.verdict == "Errors: press any key" and dialog.rows["Exit code"] == "255"
        assert script.read_text().count("boom") == 1  # saved before running
        await pilot.press("enter")
        await settle(pilot)
        messages = app.messages_window()
        assert isinstance(messages, MessagesWindow)
        texts = [i.text for i in messages.items]
        assert "a.php(12): Warning: Undefined variable $nope" in texts
        assert "a.php(13): Fatal error: Uncaught Exception: boom" in texts
        index = texts.index("a.php(13): Fatal error: Uncaught Exception: boom")
        messages.activate(index)
        await settle(pilot)
        assert win.editor.selected_text == "throw new Exception('boom');"


@needs_php
async def test_esc_stops_and_parameters(tmp_path):
    script = tmp_path / "slow.php"
    script.write_text("<?php echo implode('+', array_slice($argv, 1)); flush(); sleep(30);")
    app = Divide(tmp_path, [script])
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        await pilot.press("alt+r", "p")  # Run > Parameters
        await settle(pilot)
        dialog = app.screen.dialog
        dialog.input.data = 'one "two three"'
        await pilot.press("enter")
        await settle(pilot)
        assert app.run_arguments(script.resolve()) == 'one "two three"'
        await pilot.press("ctrl+f9")
        assert await until(pilot, lambda: isinstance(app.screen, ProgressScreen))
        box = app.screen.dialog
        assert box.rows["Script"] == "slow.php" and box.rows["Parameters"] == 'one "two three"'
        await pilot.pause(0.5)
        await pilot.press("escape")
        assert await until(pilot, lambda: not box.running)
        assert box.verdict == "Stopped: press any key"
        await pilot.press("space")
        assert await until(pilot, lambda: app.output_window() is not None and app.output_window().view.text == "one+two three")


@needs_xdebug
async def test_debugger(tmp_path):
    script = tmp_path / "a.php"
    script.write_text(SCRIPT)
    app = Divide(tmp_path, [script])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        ed = app.active_editor().editor
        # a breakpoint on "$sum += $x;"
        ed.move_cursor((4, 0))
        await pilot.press("ctrl+f8")
        assert app.breakpoints == {script.resolve(): {5}} and ed.breakpoint_rows == {4}

        # F8: the debugger starts and stops on the first line that runs
        await pilot.press("f8")
        assert await until(pilot, lambda: app.paused, tries=300)
        assert ed.execution_row == 8 and app.status_line._hint_text.startswith("Paused at a.php:9")

        # Ctrl+F9: on to the breakpoint, inside total()
        await pilot.press("ctrl+f9")
        assert await until(pilot, lambda: app.paused and ed.execution_row == 4)
        assert await until(pilot, lambda: app.output_window() is not None and app.output_window().view.text == "args: \n")

        # Watches (with the frame's variables) and the call stack
        app.watches.append("$sum + 100")
        app.show_watches()
        app.show_call_stack()
        await app.refresh_debug_windows()
        await settle(pilot)
        watches, stack = app.watches_window(), app.stack_window()
        assert isinstance(watches, WatchesWindow) and isinstance(stack, CallStackWindow)
        assert watches.lines[0] == "$sum + 100 = 100"
        assert "$sum = 0" in watches.lines and "$x = 1" in watches.lines
        assert [line[2:].split()[0] for line in stack.lines] == ["total", "{main}"]

        # a frame further up: its variables
        await app.select_frame(1)
        await settle(pilot)
        assert "$items = array(3)" in watches.lines and stack.lines[1].startswith("►")

        # Ctrl+F4: evaluate where it stopped
        app.debug_frame = 0
        await pilot.press("ctrl+f4")
        await settle(pilot)
        app.screen.dialog.input.data = "$sum + $x * 10"
        await pilot.press("enter")
        assert await until(pilot, lambda: hasattr(app.screen, "dialog") and getattr(app.screen.dialog, "_text", "").startswith("$sum"))
        assert app.screen.dialog._text == "$sum + $x * 10 = 10"
        await pilot.press("enter")
        await settle(pilot)

        # remove the breakpoint, step out, run to the end
        app.raise_window(app.window_for(script.resolve()))
        ed.move_cursor((4, 0))
        await pilot.press("ctrl+f8")
        assert app.breakpoints == {}
        await pilot.press("shift+f8")
        assert await until(pilot, lambda: app.paused and ed.execution_row == 11)  # the line after the call
        await pilot.press("ctrl+f9")
        assert await until(pilot, lambda: app.session is None)
        assert ed.execution_row is None
        assert app.output_window().view.text == "args: \ntotal 6\n" and "exit code 0" in app.output_window().summary

        # F4 runs to the cursor; Ctrl+F2 ends it
        app.raise_window(app.window_for(script.resolve()))  # the Output window came on top
        await settle(pilot)
        ed.move_cursor((11, 0))
        await pilot.press("f4")
        assert await until(pilot, lambda: app.paused and ed.execution_row == 11)
        await pilot.press("ctrl+f2")
        assert await until(pilot, lambda: app.session is None)
        assert "program reset" in app.output_window().summary


async def test_debug_keys_belong_to_php(tmp_path):
    page = tmp_path / "a.tpl"
    page.write_text("hello\nworld\n")
    app = Divide(tmp_path, [page])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        await pilot.press("f7")  # in a template F7 still selects all
        await settle(pilot)
        assert app.active_editor().editor.selected_text == "hello\nworld\n"
        assert app.session is None


@needs_xdebug
async def test_ctrl_f9_stops_at_breakpoints_and_watches_keys(tmp_path):
    script = tmp_path / "a.php"
    script.write_text(SCRIPT)
    app = Divide(tmp_path, [script])
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot)
        ed = app.active_editor().editor
        ed.move_cursor((10, 0))
        await pilot.press("ctrl+f8", "ctrl+f9")
        assert await until(pilot, lambda: app.paused and ed.execution_row == 10, tries=300)
        app.show_watches()
        await settle(pilot)
        watches = app.watches_window()
        watches.list.focus()
        await pilot.press("insert")
        await settle(pilot)
        app.screen.dialog.input.data = "$items[1]"
        await pilot.press("enter")
        assert await until(pilot, lambda: watches.lines[0] == "$items[1] = 2")
        watches.list.focus()
        watches.list.focus_item(0)
        await pilot.press("delete")
        assert await until(pilot, lambda: app.watches == [] and watches.lines[0] == "── local variables ──")
        await pilot.press("ctrl+f2")
        assert await until(pilot, lambda: app.session is None)
