# Releases

One note per version: `releases/<version>.md` (for example `releases/0.2.0.md`), in Markdown. It is the text of
that version's release on GitHub.

To release a version:

1. Raise the number in `VERSION` (the root of the repository) and write `releases/<version>.md`, in the same
   change. A pull request that changes `VERSION` without its note fails its checks.
2. Merge it into `main`. When the tests pass on `main`, the Release workflow sees a version that has no tag yet
   and its note, builds divide for every platform, tags the commit `v<version>` and publishes the release with
   the note and the files below. A version with a letter in it (`0.2.0rc1`) is published as a pre-release.

A version already tagged is not released again; a new version without its note is not released (the workflow
says so in its summary).

## What a release publishes

| File | For |
|---|---|
| `divide-<version>-linux-x86_64.tar.gz`, `-linux-arm64.tar.gz` | Linux: the standalone binary, no Python needed |
| `divide-<version>-linux-x86_64`, `-linux-arm64` | the same binary, alone, for `curl` |
| `divide-<version>-linux-x86_64.AppImage`, `-linux-arm64.AppImage` | Linux, as an AppImage |
| `divide_<version>_amd64.deb`, `_arm64.deb` | Debian, Ubuntu (`sudo apt install ./divide_*.deb`) |
| `divide-<version>-1.x86_64.rpm`, `.aarch64.rpm` | Fedora, RHEL, openSUSE (`sudo dnf install ./divide-*.rpm`) |
| `divide_<version>_x86_64.apk`, `_aarch64.apk` | Alpine (`apk add --allow-untrusted divide_*.apk`) |
| `divide-<version>-1-x86_64.pkg.tar.zst`, `-aarch64.pkg.tar.zst` | Arch Linux (`sudo pacman -U divide-*.pkg.tar.zst`) |
| `divide-<version>-macos-arm64.tar.gz`, `-macos-x86_64.tar.gz` | macOS: the standalone binary |
| `divide-<version>-windows-x86_64.zip` | Windows: `divide.exe` |
| `divide-<version>-windows-x86_64.msi` | Windows installer: Program Files, on the PATH |
| `divide.rb` | the Homebrew formula (`brew install divengine/tap/divide`) |
| `divide.json` | the Scoop manifest (`scoop install https://github.com/divengine/divide/releases/latest/download/divide.json`) |
| `SHA256SUMS` | the checksums of all of them |

The binaries are not signed: macOS asks to allow divide the first time it runs from a downloaded archive
(Homebrew does not), and Windows SmartScreen asks before the first run of the `.exe` or the `.msi`.

The Homebrew formula also goes to the tap, [divengine/homebrew-tap](https://github.com/divengine/homebrew-tap),
when the repository has the `HOMEBREW_TAP_DEPLOY_KEY` secret: the private half of an SSH key that the tap
has as a deploy key with write access.
