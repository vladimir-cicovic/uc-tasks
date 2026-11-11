#!/bin/sh
# Collect the static Python, its standard library and the dependencies
# into one directory, which becomes the whole root filesystem of the
# final (FROM scratch) image. Runs in the build stage, see Dockerfile.
#
# Usage: rootfs.sh TARGET_DIR DEPS_DIR
set -eu

ROOT=${1:?usage: rootfs.sh TARGET_DIR DEPS_DIR}
DEPS=${2:?usage: rootfs.sh TARGET_DIR DEPS_DIR}
VER=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
BIN=/usr/local/bin/python$VER
LIB=/usr/local/lib/python$VER
SITE=$ROOT$LIB/site-packages

# The image has no shared libraries, so the binary must not need any,
# and it must contain the C modules the script uses.
if ldd "$BIN" > /dev/null 2>&1; then
    echo "$BIN is not a static binary" >&2
    exit 1
fi
python3 -c 'import _hashlib, _socket, _sqlite3, _ssl, unicodedata, zlib'

mkdir -p "$ROOT/usr/local/bin"
cp "$BIN" "$ROOT/usr/local/bin/"
ln -s "python$VER" "$ROOT/usr/local/bin/python3"
# lib-dynload is a landmark Python looks for at startup.
mkdir -p "$ROOT$LIB/lib-dynload"
cp "$LIB/LICENSE.txt" "$ROOT$LIB/"

# Standard library as bytecode (no sources, no docstrings) in one zip
# file, which is on the default sys.path. Packages the script never
# uses, or that need C modules which are not built, are skipped.
python3 - "$LIB" "$ROOT/usr/local/lib/python$(echo "$VER" | tr -d .).zip" <<'EOF'
import os
import sys
import zipfile

lib, target = sys.argv[1:]
skip = {
    "__phello__", "_pyrepl", "ctypes", "curses", "ensurepip", "idlelib",
    "pydoc_data", "test", "tkinter", "turtle.py", "turtledemo",
    "unittest", "venv", "xml", "xmlrpc",
}


def keep(path):
    return os.path.basename(path) not in skip


with zipfile.PyZipFile(target, "w", zipfile.ZIP_DEFLATED, optimize=2) as zf:
    zf.writepy(lib, filterfunc=keep)
    for name in sorted(os.listdir(lib)):
        path = os.path.join(lib, name)
        if keep(path) and os.path.isfile(os.path.join(path, "__init__.py")):
            zf.writepy(path, filterfunc=keep)
EOF

# Dependencies from requirements.txt, also as bytecode only. A static
# Python cannot load C extensions: compiled speedups that have a pure
# Python twin (charset_normalizer) are removed, any other one is an
# error.
mkdir -p "$SITE"
cp -R "$DEPS/." "$SITE/"
rm -rf "${SITE:?}/bin"
find "$SITE" -name '*.so' | while read -r so; do
    name=${so##*/}
    if [ -f "${so%/*}/${name%%.*}.py" ]; then
        rm "$so"
    else
        echo "C extension without a pure Python version: $so" >&2
        exit 1
    fi
done
# -s and -p: record /usr/local/... in the bytecode, not the build path.
python3 -m compileall -q -b -o 2 -s "$ROOT" -p / "$SITE"
find "$SITE" -name '*.py' -delete
find "$SITE" -name __pycache__ -type d -prune -exec rm -rf {} +

# Mount point for the database, writable by the default user.
mkdir -p "$ROOT/data"
chown 65532:65532 "$ROOT/data"
