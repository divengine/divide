"""Folders watched for changes made outside divide, through the system's own notifications (UI-independent).

``watchdog``'s native observer (inotify on Linux, FSEvents on macOS,
ReadDirectoryChangesW on Windows) watches a set of folders, each one alone
(not recursively): the project window gives the folders it shows open. No
folder is ever listed on a timer: nothing happens until the system says
something changed.

An entry created, deleted, renamed or moved in a watched folder makes that
folder *affected*; a move affects both folders, the one it left and the one
it went to. Events are coalesced: the first starts a short wait (``delay``),
those that arrive meanwhile join it, and then the affected folders are
handed over once, without repeats, with the generation they belong to (a
later :meth:`set_folders` or :meth:`stop` makes earlier ones stale). A storm
(a checkout, ``composer install``) is bounded: past ``max_pending`` folders
the batch says *everything watched* instead of growing.

``on_change`` and ``on_error`` run on watchdog's or the timer's threads:
the caller moves them to its own thread (Textual: ``call_from_thread``) and
never touches widgets from them. A folder the system refuses to watch (a
limit, permissions, a network filesystem) is reported once through
``on_error`` and left out; nothing polls instead.
"""

from __future__ import annotations

from divide.i18n import _

import os
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

DELAY = 0.3  # seconds a burst is gathered for
MAX_WATCHED = 64  # folders watched at most (watchdog runs a thread per watch)
MAX_PENDING = 128  # affected folders kept before a batch becomes "everything"


@dataclass(frozen=True)
class Batch:
    """Folders whose entries changed, for one generation of the watched set."""

    generation: int
    folders: frozenset[Path]
    everything: bool = False  # too many: refresh every watched folder


class FolderWatcher:
    """Watches folders one by one (not recursively) and reports which changed, coalesced."""

    def __init__(self, on_change: Callable[[Batch], None], on_error: Callable[[Path, str], None] | None = None, *,
                 delay: float = DELAY, max_watched: int = MAX_WATCHED, max_pending: int = MAX_PENDING,
                 observer_factory: Callable[[], object] | None = None) -> None:
        self.on_change = on_change
        self.on_error = on_error
        self.delay = delay
        self.max_watched = max_watched
        self.max_pending = max_pending
        self._factory = observer_factory
        self._observer = None
        self._watches: dict[Path, object] = {}
        self._real: dict[str, Path] = {}  # the folder as the system names it (macOS: /private/var...) -> as given
        self._refused: set[Path] = set()  # said once, not tried again until the set changes
        self._lock = threading.Lock()
        self._pending: set[Path] = set()
        self._everything = False
        self._timer: threading.Timer | None = None
        self.generation = 0
        self.stopped = False
        self.events = 0  # events heard (for measurements and tests)
        self.batches = 0

    # ------------------------------------------------------------- the watched set
    @property
    def folders(self) -> set[Path]:
        return set(self._watches)

    def set_folders(self, folders: Iterable[Path]) -> None:
        """Watch exactly these folders (the first ``max_watched``): new ones are added, gone ones dropped."""
        if self.stopped:
            return
        wanted: list[Path] = []
        for folder in folders:
            folder = Path(folder)
            if folder not in wanted:
                wanted.append(folder)
        over = wanted[self.max_watched:]
        wanted = wanted[:self.max_watched]
        with self._lock:
            self.generation += 1
            self._pending &= set(wanted)
        for folder in list(self._watches):
            if folder not in wanted:
                self._unschedule(folder)
        self._refused &= set(wanted)
        for folder in wanted:
            if folder not in self._watches and folder not in self._refused:
                self._schedule(folder)
        if over and self.on_error is not None and over[0] not in self._refused:
            self._refused.add(over[0])
            self.on_error(over[0], _("more than {n} folders open").format(n=self.max_watched))

    def _ensure_observer(self):
        if self._observer is None:
            if self._factory is not None:
                self._observer = self._factory()
            else:
                from watchdog.observers import Observer
                self._observer = Observer()
            self._observer.daemon = True
            self._observer.start()
        return self._observer

    def _schedule(self, folder: Path) -> None:
        try:
            if not folder.is_dir():
                return
            observer = self._ensure_observer()
            self._watches[folder] = observer.schedule(_Handler(self), str(folder), recursive=False)
            self._real[os.path.normcase(os.path.realpath(folder))] = folder
        except Exception as exc:  # a limit (inotify), permissions, a filesystem that cannot be watched
            self._refused.add(folder)
            if self.on_error is not None:
                self.on_error(folder, str(exc) or type(exc).__name__)

    def _unschedule(self, folder: Path) -> None:
        watch = self._watches.pop(folder, None)
        self._real = {k: v for k, v in self._real.items() if v != folder}
        if watch is None or self._observer is None:
            return
        try:
            self._observer.unschedule(watch)
        except Exception:  # already gone (the folder was deleted)
            pass

    # ------------------------------------------------------------- events
    def _event(self, kind: str, src: str, dest: str | None, is_dir: bool) -> None:
        if self.stopped or kind not in ("created", "deleted", "moved"):
            return  # contents changing (modified), opened, closed: nothing the tree shows
        touched = {os.path.dirname(src)} | ({os.path.dirname(dest)} if dest else set())
        with self._lock:
            self.events += 1
            watched = {self._folder_of(t) for t in touched} & set(self._watches)
            if not watched:
                return
            if len(self._pending) + len(watched) > self.max_pending:
                self._everything = True
            else:
                self._pending |= watched
            if self._timer is None:
                self._timer = threading.Timer(self.delay, self._flush, args=(self.generation,))
                self._timer.daemon = True
                self._timer.start()

    def _folder_of(self, name: str) -> Path:
        path = Path(name)
        if path in self._watches:
            return path
        return self._real.get(os.path.normcase(os.path.realpath(name)), path)

    def _flush(self, generation: int) -> None:
        with self._lock:
            self._timer = None
            folders, everything = frozenset(self._pending), self._everything
            self._pending, self._everything = set(), False
            if self.stopped or (not folders and not everything):
                return
            batch = Batch(self.generation, frozenset(self._watches) if everything else folders, everything)
            self.batches += 1
        self.on_change(batch)

    def is_current(self, batch: Batch) -> bool:
        """``batch`` belongs to the folders watched now (not to a set changed or stopped since)."""
        return not self.stopped and batch.generation == self.generation

    # ------------------------------------------------------------- the end
    def stop(self) -> None:
        """Every watch dropped, the pending batch forgotten, watchdog's threads ended."""
        with self._lock:
            self.stopped = True
            self.generation += 1
            timer, self._timer = self._timer, None
            self._pending.clear()
        if timer is not None:
            timer.cancel()
        observer, self._observer = self._observer, None
        self._watches.clear()
        self._real.clear()
        if observer is not None:
            try:
                observer.unschedule_all()
                observer.stop()
                observer.join(timeout=2)
            except Exception:
                pass


class _Handler:
    """watchdog's handler interface, without importing watchdog until a folder is watched."""

    def __init__(self, watcher: FolderWatcher) -> None:
        self.watcher = watcher

    def dispatch(self, event) -> None:
        dest = getattr(event, "dest_path", "") or None
        src = event.src_path.decode() if isinstance(event.src_path, bytes) else event.src_path
        if isinstance(dest, bytes):
            dest = dest.decode()
        self.watcher._event(event.event_type, src, dest, bool(event.is_directory))
