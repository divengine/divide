#!/usr/bin/env python3
"""Measure the project window's watching of outside changes (divide.run.fswatch): idle CPU and memory,
threads and watches, change-to-visible latency, and a burst. Real measurements of this machine, printed
as JSON; nothing is estimated.

    .venv/bin/python tools/bench_watch.py [--files 50000] [--open 30] [--idle 10]

A project of ``--files`` files in nested folders is made in a temporary folder; ``--open`` folders are
opened in the project window (the watched ones); then:
- idle: process CPU seconds and RSS over ``--idle`` seconds with nothing changing, with and without the
  watcher (DIVIDE_NO_WATCH);
- latency: a file created in a watched folder, until its row is in the tree (20 times);
- burst: 2000 files created over 10 open folders at once: batches, folders read again, time until all
  are shown, CPU seconds spent.
"""

import argparse
import asyncio
import json
import os
import resource
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def make_project(root: Path, files: int) -> list[Path]:
    folders = []
    per = 100
    for i in range(max(1, files // per)):
        folder = root / f"pkg{i // 50:03}" / f"mod{i:04}"
        folder.mkdir(parents=True, exist_ok=True)
        folders.append(folder)
        for j in range(per):
            (folder / f"f{j:03}.txt").write_bytes(b"")
    return folders


def rss_mb() -> float:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 if sys.platform != "darwin" else 1024 * 1024)


def inotify_fds() -> int | None:
    if not os.path.isdir("/proc/self/fd"):
        return None
    count = 0
    for f in os.listdir("/proc/self/fd"):
        try:
            count += "inotify" in os.readlink(f"/proc/self/fd/{f}")
        except OSError:
            pass
    return count


async def run(args, watch: bool) -> dict:
    os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
    if watch:
        os.environ.pop("DIVIDE_NO_WATCH", None)
    else:
        os.environ["DIVIDE_NO_WATCH"] = "1"
    from divide.app import Divide

    work = Path(tempfile.mkdtemp(prefix="divide-bench-"))
    root = work / "project"
    folders = make_project(root, args.files)
    app = Divide(root, [])
    out: dict = {"watch": watch}
    async with app.run_test(size=(120, 40)) as pilot:
        for _ in range(500):
            await pilot.pause(0.02)
            if app.project_window() is not None and app.project_window().project_tree.root.children:
                break
        tree = app.project_window().project_tree
        reloads = [0]
        original = tree.reload_node

        def counting(node):
            reloads[0] += 1
            return original(node)

        tree.reload_node = counting
        opened = []
        for folder in folders[: args.open]:
            for part in [folder.parent, folder]:
                node = tree._node_for(part)
                if node is not None and not node.is_expanded:
                    node.expand()
                    for _ in range(200):
                        await pilot.pause(0.01)
                        n = tree._node_for(part)
                        if n is not None and n.data.loaded:
                            break
            opened.append(folder)
        await pilot.pause(1.0)
        out["watched_folders"] = len(tree.watcher.folders) if tree.watcher else 0
        out["threads"] = threading.active_count()
        out["inotify_fds"] = inotify_fds()
        out["rss_mb"] = round(rss_mb(), 1)
        cpu0, t0 = time.process_time(), time.monotonic()
        await asyncio.sleep(args.idle)
        out["idle_cpu_s"] = round(time.process_time() - cpu0, 3)
        out["idle_s"] = round(time.monotonic() - t0, 1)
        out["idle_cpu_percent"] = round(100 * out["idle_cpu_s"] / out["idle_s"], 2)
        if not watch:
            return out
        target = opened[0]
        latencies = []
        for i in range(20):
            name = f"latency{i}.txt"
            start = time.monotonic()
            (target / name).write_bytes(b"")
            while True:
                await asyncio.sleep(0.005)
                node = tree._node_for(target)
                if node is not None and any(c.data.path.name == name for c in node.children):
                    break
                if time.monotonic() - start > 10:
                    break
            latencies.append(time.monotonic() - start)
            await asyncio.sleep(0.4)
        out["latency_ms"] = {"min": round(min(latencies) * 1000), "median": round(statistics.median(latencies) * 1000),
                             "max": round(max(latencies) * 1000)}
        burst_folders = opened[:10]
        batches0, events0, reloads0 = tree.watcher.batches, tree.watcher.events, reloads[0]
        cpu0, start = time.process_time(), time.monotonic()
        for k in range(2000):
            (burst_folders[k % len(burst_folders)] / f"burst{k:04}.txt").write_bytes(b"")
        written = time.monotonic() - start
        each = 2000 // len(burst_folders)
        while True:
            await asyncio.sleep(0.01)
            done = all(sum(1 for c in tree._node_for(f).children if c.data.path.name.startswith("burst")) == each
                       for f in burst_folders)
            if done or time.monotonic() - start > 30:
                break
        out["burst"] = {"files": 2000, "folders": len(burst_folders), "write_s": round(written, 3),
                        "all_shown_s": round(time.monotonic() - start, 3), "events": tree.watcher.events - events0,
                        "batches": tree.watcher.batches - batches0, "folder_reloads": reloads[0] - reloads0,
                        "cpu_s": round(time.process_time() - cpu0, 3)}
    import shutil
    shutil.rmtree(work, ignore_errors=True)
    from watchdog.utils import BaseThread
    out["observer_threads_after_exit"] = sum(isinstance(t, BaseThread) and t.is_alive() for t in threading.enumerate())
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", type=int, default=50000)
    parser.add_argument("--open", type=int, default=30)
    parser.add_argument("--idle", type=float, default=10)
    parser.add_argument("--no-watch", action="store_true", help="only the run without the watcher")
    args = parser.parse_args()
    result = asyncio.run(run(args, watch=not args.no_watch))
    result.update(files=args.files, open=args.open, platform=sys.platform, python=sys.version.split()[0])
    print(json.dumps(result))


if __name__ == "__main__":
    main()
