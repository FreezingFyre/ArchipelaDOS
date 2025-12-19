CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
source "$CURRENT_DIR/common.sh"

make_devenv
source "$DEVENV_DIR/bin/activate"

header "Sorting imports with isort"
isort ados/ server.py

header "Performing code formatting with black"
black ados/ server.py
