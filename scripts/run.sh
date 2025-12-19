if [[ ! -z "$1" ]]; then
    CONFIG_PATH="$( realpath "$1" )"
fi

CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
source "$CURRENT_DIR/common.sh"

make_devenv
source "$DEVENV_DIR/bin/activate"

if [[ -z "$CONFIG_PATH" ]]; then
    python server.py
else
    python server.py "$CONFIG_PATH"
fi
