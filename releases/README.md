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

## winget

Each release also becomes a pull request to [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs)
with its three manifests (`Divengine.Divide`: the Windows zip, installed as the portable command `divide`), when
the repository has the `WINGET_TOKEN` secret: a classic GitHub token with the `public_repo` scope. The pull
request comes from that token's user's fork of winget-pkgs (made the first time). Once winget's maintainers
merge it, `winget install Divengine.Divide` installs that version.

`packaging/manifests.py <version> SHA256SUMS <dir> --winget <dir>` writes the manifests and
`packaging/winget_submit.py <version> <dir>` sends them, with GitHub's API: winget-pkgs is not cloned (`--dry-run` only says what it would send).

## Microsoft Store (MSIX)

**Off for now**: the MSIX is built only when the repository has the variable `MSSTORE_IDENTITY_NAME`, and sent
only when it has `MSSTORE_PRODUCT_ID`; without them a release does not try either.

When on, the Windows build also makes `divide-<version>-windows-x86_64.msix` (`packaging/msix/`): unsigned, because the
Store signs it, so it is not a file of the release but of the run's artifacts (`msix`). Before keeping it, the
build signs a copy with a certificate made for the occasion, installs it and runs `divide --version` through
its alias. Pre-releases have no MSIX: the Store takes numeric versions only.

The package's identity comes from Partner Center (the product's *Product identity*), in the repository's
variables `MSSTORE_IDENTITY_NAME`, `MSSTORE_PUBLISHER` (`CN=...`) and `MSSTORE_PUBLISHER_NAME`. The first
submission is made by hand in Partner Center with that MSIX. Then each release sends its MSIX to a new
submission when the repository has the secrets `MSSTORE_TENANT_ID`, `MSSTORE_CLIENT_ID`,
`MSSTORE_CLIENT_SECRET`, `MSSTORE_SELLER_ID` (a Microsoft Entra application added to Partner Center as
Manager) and the variable `MSSTORE_PRODUCT_ID`. Without them, the release does everything else.
