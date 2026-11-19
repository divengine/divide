"""The Homebrew formula, the Scoop manifest and the winget manifests of a release, from its SHA256SUMS.

    python packaging/manifests.py 0.1.0 assets/SHA256SUMS assets/ [--winget DIR]

writes ``divide.rb`` (Homebrew, macOS and Linux) and ``divide.json`` (Scoop, Windows) in the folder given;
with ``--winget``, the three manifests winget-pkgs takes (version, installer, locale) in
``DIR/manifests/d/Divengine/Divide/<version>/``, the place they have in that repository.
All of them download the standalone binaries the release publishes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = "divengine/divide"
HOMEPAGE = f"https://github.com/{REPO}"
LICENSE = "GPL-3.0-or-later"
DESCRIPTION = "Terminal IDE for the Divengine projects, starting with the Div template language"
WINGET_ID = "Divengine.Divide"
WINGET_SCHEMA = "1.12.0"


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
        f'  license "{LICENSE}"\n'
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
        "license": LICENSE,
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


def winget(version: str, sums: dict[str, str]) -> dict[str, str]:
    """winget-pkgs' three manifests, by file name: a portable divide.exe inside the Windows zip."""
    name = archive(version, "windows-x86_64")

    def manifest(kind: str, body: str) -> str:
        schema = f"winget-manifest.{kind}.{WINGET_SCHEMA}" if kind else f"winget-manifest.version.{WINGET_SCHEMA}"
        return (f"# yaml-language-server: $schema=https://aka.ms/{schema}.schema.json\n\n"
                f"PackageIdentifier: {WINGET_ID}\nPackageVersion: {version}\n{body}"
                f"ManifestType: {kind or 'version'}\nManifestVersion: {WINGET_SCHEMA}\n")

    folder = name.removesuffix(".zip")
    return {
        f"{WINGET_ID}.yaml": manifest("", "DefaultLocale: en-US\n"),
        f"{WINGET_ID}.installer.yaml": manifest("installer", (
            "InstallerType: zip\n"
            "NestedInstallerType: portable\n"
            "NestedInstallerFiles:\n"
            f"- RelativeFilePath: {folder}\\divide.exe\n"
            "  PortableCommandAlias: divide\n"
            "Commands:\n- divide\n"
            "Installers:\n"
            "- Architecture: x64\n"
            f"  InstallerUrl: {download(version, name)}\n"
            f"  InstallerSha256: {sums[name].upper()}\n")),
        f"{WINGET_ID}.locale.en-US.yaml": manifest("defaultLocale", (
            "PackageLocale: en-US\n"
            "Publisher: Divengine\n"
            "PublisherUrl: https://github.com/divengine\n"
            f"PublisherSupportUrl: {HOMEPAGE}/issues\n"
            "PackageName: divide\n"
            f"PackageUrl: {HOMEPAGE}\n"
            f"License: {LICENSE}\n"
            f"LicenseUrl: {HOMEPAGE}/blob/main/LICENSE\n"
            f"ShortDescription: {DESCRIPTION}\n"
            "Moniker: divide\n"
            "Tags:\n- div\n- ide\n- php\n- template-engine\n- terminal\n- tui\n"
            f"ReleaseNotesUrl: {HOMEPAGE}/releases/tag/v{version}\n"
            "Documentations:\n"
            "- DocumentLabel: Wiki\n"
            f"  DocumentUrl: {HOMEPAGE}/wiki\n")),
    }


def winget_folder(version: str) -> Path:
    """Where winget-pkgs keeps a version's manifests."""
    publisher, package = WINGET_ID.split(".", 1)
    return Path("manifests", publisher[0].lower(), publisher, package, version)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version")
    parser.add_argument("sums", type=Path, help="the release's SHA256SUMS")
    parser.add_argument("out", type=Path, help="folder for divide.rb and divide.json")
    parser.add_argument("--winget", type=Path, help="also the winget manifests, under this folder")
    args = parser.parse_args(argv)
    sums = read_sums(args.sums.read_text(encoding="utf-8"))
    Path(args.out, "divide.rb").write_text(homebrew(args.version, sums), encoding="utf-8")
    Path(args.out, "divide.json").write_text(scoop(args.version, sums), encoding="utf-8")
    if args.winget:
        folder = args.winget / winget_folder(args.version)
        folder.mkdir(parents=True, exist_ok=True)
        for name, text in winget(args.version, sums).items():
            (folder / name).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
