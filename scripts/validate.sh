CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
source "$CURRENT_DIR/common.sh"

make_devenv
source "$DEVENV_DIR/bin/activate"

header "Validating code formatting"
isort --check-only ados/ server.py
ISORT_RET=$?
black --check ados/ server.py
BLACK_RET=$?

header "Validating type hints with mypy"
mypy ados/ server.py
MYPY_RET=$?

header "Validating linting with pylint"
pylint ados/ server.py
PYLINT_RET=$?

if [[ $ISORT_RET -ne 0 || $BLACK_RET -ne 0 || $MYPY_RET -ne 0 || $PYLINT_RET -ne 0 ]]; then
    printf "\n\e[1;31mValidation failed!\e[0m\n\n"
    exit 1
else
    printf "\n\e[1;32mAll validations passed!\e[0m\n\n"
    exit 0
fi
