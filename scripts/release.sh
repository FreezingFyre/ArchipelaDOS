CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
source "$CURRENT_DIR/common.sh"

if [[ -z "$1" ]]; then
    echo "Usage: $0 <version>"
    exit 1
fi

VERSION="$1"
PACKAGE_DIR="output/ArchipelaDOS-v$VERSION"

rm -rf $PACKAGE_DIR* || true
mkdir -p "$PACKAGE_DIR"
git clean -fxd ados

cp server.py "$PACKAGE_DIR"
cp config.yaml "$PACKAGE_DIR"
cp requirements.txt "$PACKAGE_DIR"
cp ArchipelaDOS.yaml "$PACKAGE_DIR"
cp -r ados "$PACKAGE_DIR/ados"

cd output
tar -czf "ArchipelaDOS-v$VERSION.tar.gz" "ArchipelaDOS-v$VERSION"
zip -r "ArchipelaDOS-v$VERSION.zip" "ArchipelaDOS-v$VERSION"
