import json

import pytest

from divide.ui import progress


@pytest.fixture(autouse=True)
def quick_progress(monkeypatch):
    """A successful job's progress box closes at once (the user would see it for a moment)."""
    monkeypatch.setattr(progress, "AUTO_CLOSE", 0.01)


@pytest.fixture(autouse=True)
def own_config(tmp_path_factory, monkeypatch):
    """Never the user's settings (a language server they installed would join in);
    tests that need settings point XDG_CONFIG_HOME elsewhere themselves."""
    home = tmp_path_factory.mktemp("config")
    (home / "divide").mkdir()
    (home / "divide" / "config.json").write_text(json.dumps({"lsp": {"php": "off"}}))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
