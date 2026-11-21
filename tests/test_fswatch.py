"""Changes made outside divide, through the system's own notifications (watchdog): the watcher itself,
then the project window that follows them.

The watcher tests use the real native observer of the platform they run on (inotify, FSEvents,
ReadDirectoryChangesW): nothing is polled, and nothing is faked except where a refusal is needed.
"""

import asyncio
import os
import shutil
import threading
import time
from pathlib import Path

import pytest

from divide.run.fswatch import Batch, FolderWatcher

WAIT = 5.0  # seconds a notification may take on a loaded CI machine


class Collector:
    def __init__(self) -> None:
        self.batches: list[Batch] = []
        self.errors: list[tuple[Path, str]] = []
        self.lock = threading.Lock()

    def change(self, batch: Batch) -> None:
        with self.lock:
            self.batches.append(batch)

    def error(self, folder: Path, why: str) -> None:
        self.errors.append((folder, why))

    def folders(self) -> set[Path]:
        with self.lock:
            return set().union(*(b.folders for b in self.batches)) if self.batches else set()

    def wait_for(self, condition, timeout: float = WAIT) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if condition():
                return True
            time.sleep(0.02)
        return condition()


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "p"
    for folder in ("a", "b", "a/deep"):
        (root / folder).mkdir(parents=True)
    (root / "a" / "x.txt").write_text("x")
    return root.resolve()


@pytest.fixture
def watching():
    made = []

    def make(folders, **kwargs):
        seen = Collector()
        watcher = FolderWatcher(seen.change, seen.error, **kwargs)
        watcher.set_folders(folders)
        made.append(watcher)
        time.sleep(0.15)  # the native watch is in place (FSEvents takes a moment)
        return watcher, seen

    yield make
    for watcher in made:
        watcher.stop()


def test_created_deleted_and_renamed_entries_affect_their_folder(tree, watching):
    watcher, seen = watching([tree, tree / "a"])
    (tree / "new.txt").write_text("n")
    assert seen.wait_for(lambda: tree in seen.folders())
    seen.batches.clear()
    (tree / "a" / "x.txt").rename(tree / "a" / "y.txt")
    assert seen.wait_for(lambda: tree / "a" in seen.folders())
    seen.batches.clear()
    (tree / "new.txt").unlink()
    assert seen.wait_for(lambda: tree in seen.folders())


def test_a_move_affects_both_folders(tree, watching):
    watcher, seen = watching([tree / "a", tree / "b"])
    os.replace(tree / "a" / "x.txt", tree / "b" / "x.txt")
    assert seen.wait_for(lambda: {tree / "a", tree / "b"} <= seen.folders())


def test_folders_are_watched_alone_not_recursively(tree, watching):
    watcher, seen = watching([tree])
    (tree / "a" / "deep" / "inside.txt").write_text("i")  # two levels down: not watched
    (tree / "a" / "z.txt").write_text("z")  # one level down: a's own entry, not the root's
    time.sleep(1.0)
    assert seen.batches == []
    (tree / "c").mkdir()
    assert seen.wait_for(lambda: seen.folders() == {tree})


def test_contents_changing_is_not_a_change_of_the_folder(tree, watching):
    watcher, seen = watching([tree / "a"])
    with open(tree / "a" / "x.txt", "a") as f:
        f.write("more")
    time.sleep(1.0)
    assert seen.batches == []


def test_a_burst_is_one_batch_without_repeats(tree, watching):
    watcher, seen = watching([tree / "a"], delay=0.3)
    for i in range(300):
        (tree / "a" / f"f{i}.txt").write_text("")
    assert seen.wait_for(lambda: seen.batches)
    time.sleep(0.6)
    assert 1 <= len(seen.batches) <= 3 and all(b.folders == frozenset({tree / "a"}) for b in seen.batches)
    assert watcher.events >= 300


def test_a_storm_over_many_folders_is_bounded(tree, watching):
    folders = []
    for i in range(12):
        (tree / f"d{i}").mkdir()
        folders.append(tree / f"d{i}")
    watcher, seen = watching(folders, max_pending=4)
    for folder in folders:
        (folder / "f").write_text("")
    assert seen.wait_for(lambda: any(b.everything for b in seen.batches))
    batch = next(b for b in seen.batches if b.everything)
    assert batch.folders == frozenset(folders)  # everything watched: no more than that


def test_the_watched_set_follows_and_old_batches_go_stale(tree, watching):
    watcher, seen = watching([tree, tree / "a"])
    (tree / "a" / "n.txt").write_text("")
    assert seen.wait_for(lambda: seen.batches)
    old = seen.batches[-1]
    assert watcher.is_current(old)
    watcher.set_folders([tree])
    assert watcher.folders == {tree} and not watcher.is_current(old)
    seen.batches.clear()
    (tree / "a" / "m.txt").write_text("")
    time.sleep(1.0)
    assert seen.batches == []


def test_a_watched_folder_deleted(tree, watching):
    watcher, seen = watching([tree, tree / "a"])
    shutil.rmtree(tree / "a")
    assert seen.wait_for(lambda: tree in seen.folders())
    watcher.set_folders([tree])  # the tree drops it
    assert watcher.folders == {tree}


def test_refusals_are_said_once_and_the_rest_is_watched(tree, watching):
    class Refusing:
        daemon = True

        def start(self): pass

        def schedule(self, handler, path, recursive=False):
            if path.endswith("b"):
                raise OSError(28, "inotify watch limit reached")
            return object()

        def unschedule(self, watch): pass

        def unschedule_all(self): pass

        def stop(self): pass

        def join(self, timeout=None): pass

    watcher, seen = watching([tree / "a", tree / "b"], observer_factory=Refusing)
    assert watcher.folders == {tree / "a"} and [f for f, _ in seen.errors] == [tree / "b"]
    watcher.set_folders([tree / "a", tree / "b"])  # not tried again, not said again
    assert len(seen.errors) == 1


def test_more_folders_than_the_limit(tree, watching):
    watcher, seen = watching([tree, tree / "a", tree / "b"], max_watched=2)
    assert watcher.folders == {tree, tree / "a"} and seen.errors[0][0] == tree / "b"


def observer_threads() -> list:
    from watchdog.utils import BaseThread
    return [t for t in threading.enumerate() if isinstance(t, BaseThread) and t.is_alive()]


def test_stop_ends_everything(tree):
    seen = Collector()
    watcher = FolderWatcher(seen.change, seen.error, delay=0.5)
    watcher.set_folders([tree, tree / "a", tree / "b"])
    time.sleep(0.15)
    assert observer_threads()
    (tree / "late.txt").write_text("")  # a batch waits...
    time.sleep(0.1)
    watcher.stop()  # ...and is forgotten
    time.sleep(0.8)
    assert seen.batches == [] and watcher.folders == set()
    assert observer_threads() == []
    watcher.set_folders([tree])  # a stopped watcher stays stopped
    assert watcher.folders == set()


# ------------------------------------------------------------------ the project window
async def until(pilot, condition, what: str, tries: int = 250) -> None:
    for _ in range(tries):
        await pilot.pause(0.02)
        if condition():
            return
    pytest.fail(what)


def names(node) -> list[str]:
    return sorted(c.data.path.name for c in node.children if c.data is not None)


async def project(pilot, app):
    await until(pilot, lambda: app.project_window() is not None and app.project_window().project_tree.watcher is not None,
                "no project window watching")
    tree = app.project_window().project_tree
    await until(pilot, lambda: tree.root.children, "the project did not load")
    return tree


async def opened(pilot, tree, folder: Path):
    node = tree._node_for(folder)
    node.expand()
    await until(pilot, lambda: tree._node_for(folder) is not None and tree._node_for(folder).data.loaded
                and folder in tree.watcher.folders, f"{folder.name} did not open")
    return tree._node_for(folder)


async def test_outside_changes_appear_and_moves_show_on_both_sides(tree):
    from divide.app import Divide

    app = Divide(tree, [])
    async with app.run_test(size=(100, 30)) as pilot:
        t = await project(pilot, app)
        assert t.watcher.folders == {tree}
        await opened(pilot, t, tree / "a")
        await opened(pilot, t, tree / "b")
        (tree / "made.txt").write_text("")
        (tree / "newdir").mkdir()
        await until(pilot, lambda: {"made.txt", "newdir"} <= set(names(t.root)), "creations not shown")
        os.replace(tree / "a" / "x.txt", tree / "b" / "x.txt")
        await until(pilot, lambda: "x.txt" not in names(t._node_for(tree / "a")) and "x.txt" in names(t._node_for(tree / "b")),
                    "the move was not shown on both sides")
        (tree / "made.txt").rename(tree / "renamed.txt")
        await until(pilot, lambda: "renamed.txt" in names(t.root) and "made.txt" not in names(t.root), "the rename was not shown")
        shutil.rmtree(tree / "newdir")
        await until(pilot, lambda: "newdir" not in names(t.root), "the deletion was not shown")


async def test_the_tree_keeps_its_place(tree):
    from divide.app import Divide

    for i in range(40):
        (tree / f"file{i:02}.txt").write_text("")
    app = Divide(tree, [])
    async with app.run_test(size=(100, 20)) as pilot:
        t = await project(pilot, app)
        await opened(pilot, t, tree / "a")
        target = t._node_for(tree / "file30.txt")
        t.move_cursor(target)
        await pilot.pause(0.2)
        y, line = t.scroll_offset.y, t.cursor_line
        assert y > 0
        (tree / "file99.txt").write_text("")  # below: nothing should move
        await until(pilot, lambda: "file99.txt" in names(t.root), "the new file was not shown")
        await pilot.pause(0.2)
        assert t.selected_path == tree / "file30.txt" and t.cursor_line == line and t.scroll_offset.y == y
        assert t._node_for(tree / "a").is_expanded  # what was open stays open


async def test_watches_follow_folding_and_closed_folders_load_fresh(tree):
    from divide.app import Divide

    app = Divide(tree, [])
    async with app.run_test(size=(100, 30)) as pilot:
        t = await project(pilot, app)
        a = await opened(pilot, t, tree / "a")
        a.collapse()
        await until(pilot, lambda: t.watcher.folders == {tree}, "the closed folder is still watched")
        (tree / "a" / "while-closed.txt").write_text("")
        await pilot.pause(0.6)
        await opened(pilot, t, tree / "a")
        await until(pilot, lambda: "while-closed.txt" in names(t._node_for(tree / "a")), "not read again when it opened")


async def test_a_deleted_open_folder_and_the_buffers_are_left_alone(tree):
    from divide.app import Divide

    app = Divide(tree, [])
    async with app.run_test(size=(100, 30)) as pilot:
        t = await project(pilot, app)
        app.open_file(tree / "a" / "x.txt")
        await until(pilot, lambda: app.window_for(tree / "a" / "x.txt") is not None, "the file did not open")
        await opened(pilot, t, tree / "a")
        await opened(pilot, t, tree / "a" / "deep")
        editor = app.window_for(tree / "a" / "x.txt").editor
        editor.insert("unsaved ")
        (tree / "a" / "x.txt").write_text("changed outside")
        shutil.rmtree(tree / "a" / "deep")
        await until(pilot, lambda: "deep" not in names(t._node_for(tree / "a")), "the deleted folder is still shown")
        await until(pilot, lambda: tree / "a" / "deep" not in t.watcher.folders, "the deleted folder is still watched")
        assert editor.text == "unsaved x"  # the buffer is never reloaded from the disk


async def test_switching_and_closing_projects_stop_the_watcher(tree, tmp_path):
    from divide.app import Divide

    other = tmp_path / "other"
    (other / "q").mkdir(parents=True)
    app = Divide(tree, [])
    async with app.run_test(size=(100, 30)) as pilot:
        t = await project(pilot, app)
        first = t.watcher
        stale = Batch(first.generation, frozenset({tree}))
        await app.open_folder(other)
        await until(pilot, lambda: first.stopped, "the old project's watcher was not stopped")
        t2 = await project(pilot, app)
        assert t2.watcher.folders == {other.resolve()}
        t._apply_changes(stale)  # a batch of the old project arriving late: nothing happens
        (other / "seen.txt").write_text("")
        await until(pilot, lambda: "seen.txt" in names(t2.root), "the new project is not watched")
        await app.close_folder()
        await until(pilot, lambda: t2.watcher is None, "closing the folder did not stop the watcher")
    await asyncio.sleep(0.3)
    from watchdog.utils import BaseThread
    assert [t for t in threading.enumerate() if isinstance(t, BaseThread)] == []  # no observer left


async def test_ctrl_r_still_refreshes_without_the_watcher(tree, monkeypatch):
    from divide.app import Divide

    monkeypatch.setenv("DIVIDE_NO_WATCH", "1")
    app = Divide(tree, [])
    async with app.run_test(size=(100, 30)) as pilot:
        await until(pilot, lambda: app.project_window() is not None, "no project window")
        t = app.project_window().project_tree
        await until(pilot, lambda: t.root.children, "the project did not load")
        assert t.watcher is None
        (tree / "manual.txt").write_text("")
        await pilot.pause(0.6)
        assert "manual.txt" not in names(t.root)
        t.focus()
        await pilot.press("ctrl+r")
        await until(pilot, lambda: "manual.txt" in names(t.root), "Ctrl+R did not refresh")


async def test_a_filter_survives_outside_changes(tree):
    from divide.app import Divide

    app = Divide(tree, [])
    async with app.run_test(size=(100, 30)) as pilot:
        t = await project(pilot, app)
        t.focus()
        await pilot.press(*"txt")
        await until(pilot, lambda: t.filter_text == "txt", "no filter")
        (tree / "other.txt").write_text("")
        await until(pilot, lambda: "other.txt" in names(t.root), "not shown under the filter")
        assert t.filter_text == "txt"
