CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

export ROOT_DIR="$( realpath "$CURRENT_DIR/../" )"
export DEVENV_DIR="$ROOT_DIR/devenv"

make_devenv() {
    if [[ -d "$DEVENV_DIR" ]]; then
        diff "$ROOT_DIR/requirements.txt" "$DEVENV_DIR/requirements.txt" > /dev/null 2>&1
        local DIFF_REQS=$?
        diff "$ROOT_DIR/requirements_dev.txt" "$DEVENV_DIR/requirements_dev.txt" > /dev/null 2>&1
        local DIFF_DEV_REQS=$?
        if [[ $DIFF_REQS -eq 0 ]] && [[ $DIFF_DEV_REQS -eq 0 ]]; then
            echo "Development environment is up to date"
            return
        fi
    fi

    echo "Setting up development environment..."
    rm -rf "$DEVENV_DIR" || true
    python3 -m venv "$DEVENV_DIR"
    source "$DEVENV_DIR/bin/activate"
    pip install -r "$ROOT_DIR/requirements.txt" -r "$ROOT_DIR/requirements_dev.txt"
    cp "$ROOT_DIR/requirements.txt" "$DEVENV_DIR/requirements.txt"
    cp "$ROOT_DIR/requirements_dev.txt" "$DEVENV_DIR/requirements_dev.txt"

    echo "Development environment setup complete"
}

header() {
    local TEXT="$1"
    printf "\n\e[0;36m"
    for i in $(seq 1 ${#TEXT}); do printf "="; done
    printf "\n%s\n" "$TEXT"
    for i in $(seq 1 ${#TEXT}); do printf "="; done
    printf "\e[0m\n"
}

cd "$ROOT_DIR"
