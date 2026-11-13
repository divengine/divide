#!/usr/bin/env sh
# Install divide as a command for your user, from this checkout.
#
#     tools/install.sh            # links ~/.local/bin/divide
#     tools/install.sh /usr/local/bin
#
# divide is installed in editable mode in the checkout's .venv (created if
# missing) and the command is a link to it: `divide` works in any folder and
# always runs the code of this checkout (git pull is the update).
# To remove it: delete the link.
set -eu

here=$(cd "$(dirname "$0")/.." && pwd)
bin_dir=${1:-"$HOME/.local/bin"}
python=${PYTHON:-python3}

if [ ! -x "$here/.venv/bin/python" ]; then
    echo "creating $here/.venv"
    "$python" -m venv "$here/.venv"
fi
"$here/.venv/bin/python" -m pip install --quiet --editable "$here"

mkdir -p "$bin_dir"
target="$bin_dir/divide"
if [ -e "$target" ] && [ ! -L "$target" ]; then
    echo "$target exists and is not a link: left as it is" >&2
    exit 1
fi
ln -sfn "$here/.venv/bin/divide" "$target"
echo "divide -> $target"

case ":$PATH:" in
    *":$bin_dir:"*) ;;
    *) echo "note: $bin_dir is not in your PATH; add it to use 'divide' everywhere" ;;
esac
