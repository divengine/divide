"""The Homebrew formula and the Scoop manifest of a release, from its SHA256SUMS.

    python packaging/manifests.py 0.1.0 assets/SHA256SUMS assets/

writes ``divide.rb`` (Homebrew, macOS and Linux) and ``divide.json`` (Scoop, Windows) in the folder given.
Both download the standalone binaries the release publishes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = "divengine/divide"
HOMEPAGE = f"https://github.com/{REPO}"
DESCRIPTION = "Terminal IDE for the Divengine projects, starting with the Div template language"


def archive(version: str, target: str) -> str:
    """The archive name of a target (linux-x86_64, windows-x86_64...)."""
    suffix = "zip" if target.startswith("windows") else "tar.gz"
    return f"divide-{version}-{target}.{suffix}"


def download(version: str, name: str) -> str:
    return f"{HOMEPAGE}/releases/download/v{version}/{name}"


def read_sums(text: str) -> dict[str, str]:
    """``sha256sum`` lines: hash, then the file name (``*`` before it in binary mode)."""
    sums = {}
    for line in text.splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            sums[name.lstrip("*")] = digest
    return sums


def homebrew(version: str, sums: dict[str, str]) -> str:
    def block(target: str, indent: str) -> str:
        name = archive(version, target)
        return f'{indent}url "{download(version, name)}"\n{indent}sha256 "{sums[name]}"\n'

    return (
        "class Divide < Formula\n"
        f'  desc "{DESCRIPTION}"\n'
        f'  homepage "{HOMEPAGE}"\n'
        f'  version "{version}"\n'
        "\n"
        "  on_macos do\n"
        "    on_arm do\n" + block("macos-arm64", "      ") + "    end\n"
        "    on_intel do\n" + block("macos-x86_64", "      ") + "    end\n"
        "  end\n"
        "\n"
        "  on_linux do\n"
        "    on_arm do\n" + block("linux-arm64", "      ") + "    end\n"
        "    on_intel do\n" + block("linux-x86_64", "      ") + "    end\n"
        "  end\n"
        "\n"
        "  def install\n"
        '    bin.install "divide"\n'
        "  end\n"
        "\n"
        "  test do\n"
        '    assert_match version.to_s, shell_output("#{bin}/divide --version")\n'
        "  end\n"
        "end\n"
    )


def scoop(version: str, sums: dict[str, str]) -> str:
    name = archive(version, "windows-x86_64")
    manifest = {
        "version": version,
        "description": DESCRIPTION,
        "homepage": HOMEPAGE,
        "architecture": {"64bit": {"url": download(version, name), "hash": sums[name],
                                   "extract_dir": name.removesuffix(".zip")}},
        "bin": "divide.exe",
        "checkver": "github",
        "autoupdate": {
            "architecture": {"64bit": {"url": download("$version", archive("$version", "windows-x86_64")),
                                       "extract_dir": "divide-$version-windows-x86_64"}},
            "hash": {"url": "$baseurl/SHA256SUMS"},
        },
    }
    return json.dumps(manifest, indent=4) + "\n"


def main(argv: list[str]) -> None:
    version, sums_file, out = argv
    sums = read_sums(Path(sums_file).read_text(encoding="utf-8"))
    Path(out, "divide.rb").write_text(homebrew(version, sums), encoding="utf-8")
    Path(out, "divide.json").write_text(scoop(version, sums), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
