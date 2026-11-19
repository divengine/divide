"""The folders and files opened lately, newest first, in the user's settings (``recent``).

Only real paths are kept; one that no longer exists is left out when the list is read.
"""

from __future__ import annotations

from pathlib import Path

from divide import config

LIMIT = 12
KINDS = ("folders", "files")


def _stored() -> dict[str, list[str]]:
    data = config.load().get("recent")
    if not isinstance(data, dict):
        return {kind: [] for kind in KINDS}
    return {kind: [p for p in data.get(kind, []) if isinstance(p, str)] for kind in KINDS}


def entries(kind: str) -> list[Path]:
    """The ``kind`` ("folders" or "files") still on disk, newest first."""
    test = Path.is_dir if kind == "folders" else Path.is_file
    return [Path(p) for p in _stored()[kind] if test(Path(p))]


def add(kind: str, path: Path) -> None:
    """``path`` first in its list (and only once)."""
    stored = _stored()
    text = str(path.expanduser().resolve())
    stored[kind] = [text, *(p for p in stored[kind] if p != text)][:LIMIT]
    config.set_value("recent", stored)


def forget(kind: str, path: Path) -> None:
    stored = _stored()
    text = str(path)
    stored[kind] = [p for p in stored[kind] if p != text]
    config.set_value("recent", stored)
