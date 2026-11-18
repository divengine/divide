"""The version manifest and the Homebrew and Scoop manifests a release publishes."""

import importlib.util
import json
from pathlib import Path

import divide
from divide.app import main

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("manifests", ROOT / "packaging" / "manifests.py")
manifests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifests)

TARGETS = ["linux-x86_64", "linux-arm64", "macos-arm64", "macos-x86_64", "windows-x86_64"]


def sums(version: str) -> dict[str, str]:
    return {manifests.archive(version, t): f"{i:064x}" for i, t in enumerate(TARGETS, 1)}


def test_the_version_is_the_one_in_the_manifest(capsys):
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert divide.__version__ == version
    try:
        main(["--version"])
    except SystemExit:
        pass
    assert capsys.readouterr().out.strip() == f"divide {version}"


def test_sha256sum_lines_are_read_in_text_and_binary_mode():
    text = f"{'a' * 64}  divide-1.0.0-linux-x86_64.tar.gz\n{'b' * 64} *divide-1.0.0-windows-x86_64.zip\n\n"
    assert manifests.read_sums(text) == {"divide-1.0.0-linux-x86_64.tar.gz": "a" * 64,
                                         "divide-1.0.0-windows-x86_64.zip": "b" * 64}


def test_the_formula_downloads_each_platform_with_its_checksum():
    formula = manifests.homebrew("1.2.3", sums("1.2.3"))
    assert 'version "1.2.3"' in formula
    for i, target in enumerate(TARGETS[:4], 1):
        url = f"https://github.com/divengine/divide/releases/download/v1.2.3/divide-1.2.3-{target}.tar.gz"
        assert f'url "{url}"\n      sha256 "{i:064x}"' in formula
    mac = formula.index("on_macos")
    linux = formula.index("on_linux")
    assert mac < formula.index("macos-arm64") < formula.index("macos-x86_64") < linux
    assert linux < formula.index("linux-arm64") < formula.index("linux-x86_64")
    assert 'bin.install "divide"' in formula


def test_the_scoop_manifest_points_at_the_windows_zip_and_updates_itself():
    manifest = json.loads(manifests.scoop("1.2.3", sums("1.2.3")))
    assert manifest["version"] == "1.2.3"
    app = manifest["architecture"]["64bit"]
    assert app == {"url": "https://github.com/divengine/divide/releases/download/v1.2.3/divide-1.2.3-windows-x86_64.zip",
                   "hash": f"{5:064x}", "extract_dir": "divide-1.2.3-windows-x86_64"}
    assert manifest["bin"] == "divide.exe"
    auto = manifest["autoupdate"]["architecture"]["64bit"]
    assert auto["url"].endswith("/v$version/divide-$version-windows-x86_64.zip")


def test_main_writes_both(tmp_path):
    lines = "".join(f"{digest}  {name}\n" for name, digest in sums("0.9.0").items())
    (tmp_path / "SHA256SUMS").write_text(lines, encoding="utf-8")
    manifests.main(["0.9.0", str(tmp_path / "SHA256SUMS"), str(tmp_path)])
    assert "divide-0.9.0-macos-arm64.tar.gz" in (tmp_path / "divide.rb").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "divide.json").read_text(encoding="utf-8"))["version"] == "0.9.0"
