# Installation

## What you need

| | Needed for |
|---|---|
| **PHP 8** (the `php` command) | rendering, and checking includes |
| **Div** (`divengine/div`) | rendering, and checking includes |
| **Xdebug** (optional) | the PHP [[debugger\|Debugging PHP]] |
| **Python 3.11+** | only to install divide from its source code |

Editing, highlighting, completion and most checks work without PHP. Everything that needs to know what Div would do (rendering, resolving `{% includes %}`) asks the real engine, so it needs PHP and Div.

## Install divide

Every [release](https://github.com/divengine/divide/releases/latest) carries divide ready to run, with Python inside: nothing else to install. Pick the way that suits your system.

### macOS and Linux: Homebrew

```bash
brew install divengine/tap/divide
```

`brew upgrade divide` updates it.

### Windows: Scoop

```powershell
scoop install https://github.com/divengine/divide/releases/latest/download/divide.json
```

`scoop update divide` updates it. Or download `divide-<version>-windows-x86_64.msi` from the release: the installer puts divide in Program Files and on the PATH (open a new terminal afterwards). The `.zip` holds `divide.exe` alone, to put wherever you like.

### Linux packages

From the release, for your architecture (`amd64`/`x86_64` or `arm64`/`aarch64`):

| System | Package | Install |
|---|---|---|
| Debian, Ubuntu | `divide_<version>_amd64.deb` | `sudo apt install ./divide_<version>_amd64.deb` |
| Fedora, RHEL, openSUSE | `divide-<version>-1.x86_64.rpm` | `sudo dnf install ./divide-<version>-1.x86_64.rpm` |
| Alpine | `divide_<version>_x86_64.apk` | `sudo apk add --allow-untrusted divide_<version>_x86_64.apk` |
| Arch | `divide-<version>-1-x86_64.pkg.tar.zst` | `sudo pacman -U divide-<version>-1-x86_64.pkg.tar.zst` |

The packages put `divide` in `/usr/bin` and recommend `php-cli`.

### Linux: AppImage or the binary alone

```bash
chmod +x divide-<version>-linux-x86_64.AppImage
./divide-<version>-linux-x86_64.AppImage
```

Or the standalone binary, in a folder on your PATH:

```bash
curl -fLo ~/.local/bin/divide https://github.com/divengine/divide/releases/download/v<version>/divide-<version>-linux-x86_64
chmod +x ~/.local/bin/divide
```

### macOS: the archive

`divide-<version>-macos-arm64.tar.gz` (Apple silicon) or `-macos-x86_64.tar.gz` (Intel) holds the binary. It is not signed, so macOS stops it the first time; allow it with:

```bash
xattr -d com.apple.quarantine divide
```

(Homebrew does not need this.) On Windows, SmartScreen asks the same before the first run of the `.exe` or the `.msi`: **More info > Run anyway**.

Each release has a `SHA256SUMS` file to check what you downloaded.

### From the source code

With Python 3.11 or newer, as a command for your user:

```bash
git clone https://github.com/divengine/divide.git
cd divide
tools/install.sh
```

`tools/install.sh` creates the checkout's `.venv` if needed, installs divide there (editable) and links the `divide` command in `~/.local/bin` (or the folder you give it: `tools/install.sh /usr/local/bin`). `git pull` in the checkout updates the command. To remove it, delete the link.

Or as an isolated command with [pipx](https://pipx.pypa.io/):

```bash
pipx install git+https://github.com/divengine/divide.git
```

### Check it

```bash
divide --version
cd ~/sites/my-project
divide .            # this folder is the project
divide page.tpl     # a file on its own, no folder
```

## Install Div for your project

The usual way is Composer, in the project that holds your templates:

```bash
composer require divengine/div
```

divide finds the engine by itself, in this order:

1. the `DIVIDE_DIV_PHP` environment variable: a `vendor/autoload.php`, or a Div checkout's `src/div.php` (with its `vendor/` installed);
2. the `engine` of the project's [[Div setup|Div Setup]] (`.div/setup.json`), then of yours (`~/.div/setup.json`);
3. the path set in **Options > Div engine…** (saved in `~/.config/divide/config.json`);
4. a `vendor/autoload.php` with `vendor/divengine/div`, looking upwards from the template and from the project folder.

If none is found, **Ctrl+F9** on a template explains what to do, and include checks are simply skipped.

## Start it

```bash
divide                    # nothing opened: the Welcome window (recent folders and files)
divide .                  # the current folder as the project, project window open
divide ~/sites/shop       # another folder as the project
divide index.tpl card.tpl # files on their own, with no folder
divide ~/sites/shop index.tpl
divide --palette turbo-c  # start with a colour theme: turbo-pascal, turbo-c, free-pascal, modern-dark, phosphor-white, phosphor-green, phosphor-green-black, phosphor-amber, phosphor-amber-black
divide --colors truecolor # colour depth when the terminal says less than it can: auto, truecolor, 256, 16
divide --language es      # the interface in Spanish for this run: en, es
```

The first two are also in **Options > Colors**, which remembers them (see [[The Desktop#colours]]); the language is in **Options > Language** (see [[The Desktop#language]]).

A folder is opened only when you give it, as in VS Code; **File > Open folder** opens one later (see [[The Desktop#a-folder-a-file-or-nothing]]).

Use a terminal at least 80×25; 120 columns or more is comfortable for working side by side with the output.

Next: [[Getting Started]].
