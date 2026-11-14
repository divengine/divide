# Installation

## What you need

| | Needed for |
|---|---|
| **Python 3.11+** | divide itself |
| **PHP 8** (the `php` command) | rendering, and checking includes |
| **Div** (`divengine/div`) | rendering, and checking includes |
| **Xdebug** (optional) | the PHP [[debugger|Debugging PHP]] |

Editing, highlighting, completion and most checks work with Python alone. Everything that needs to know what Div would do (rendering, resolving `{% includes %}`) asks the real engine, so it needs PHP and Div.

## Install divide

From the repository, as a command for your user:

```bash
git clone https://github.com/divengine/divide.git
cd divide
tools/install.sh
```

`tools/install.sh` creates the checkout's `.venv` if needed, installs divide there (editable) and links the `divide` command in `~/.local/bin` (or the folder you give it: `tools/install.sh /usr/local/bin`). Then, in any folder:

```bash
cd ~/sites/my-project
divide              # the folder is the project
divide page.tpl     # a file: its folder is the project
```

`git pull` in the checkout updates the command. To remove it, delete the link.

Or as an isolated command with [pipx](https://pipx.pypa.io/):

```bash
pipx install git+https://github.com/divengine/divide.git
divide --help
```

## Install Div for your project

The usual way is Composer, in the project that holds your templates:

```bash
composer require divengine/div
```

divide finds the engine by itself, in this order:

1. the `DIVIDE_DIV_PHP` environment variable: a `vendor/autoload.php`, or a Div checkout's `src/div.php` (with its `vendor/` installed);
2. the path set in **Options > Div engine…** (saved in `~/.config/divide/config.json`);
3. a `vendor/autoload.php` with `vendor/divengine/div`, looking upwards from the template and from the project folder.

If none is found, **Ctrl+F9** on a template explains what to do, and include checks are simply skipped.

## Start it

```bash
divide                    # the current folder as the project, project window open
divide ~/sites/shop       # another folder as the project
divide index.tpl card.tpl # open files (their folder becomes the project)
divide ~/sites/shop index.tpl
divide --palette turbo-c  # Turbo C colours instead of Turbo Pascal's
```

Use a terminal at least 80×25; 120 columns or more is comfortable for working side by side with the output.

Next: [[Getting Started]].
