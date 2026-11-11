#!/bin/sh
# Prepare the image build: install the build tools and get the sources.
# The Dockerfile runs both commands in its build stage. "sources" can
# also run on the host before "docker build"; the build then uses the
# files in sources/ instead of downloading them again.
#
# Usage:
#   prepare.sh tools          install compiler, perl, upx, zlib (Alpine)
#   prepare.sh sources DIR    download Python, OpenSSL and SQLite into DIR
#                             and check them against versions.env
set -eu

HERE=$(dirname "$0")

usage() {
    sed -n '7,10s/^# \{0,1\}//p' "$0" >&2
    exit 2
}

tools() {
    if ! command -v apk > /dev/null 2>&1; then
        echo "tools: needs Alpine Linux (apk), it runs in the build stage" >&2
        exit 1
    fi
    apk add --no-cache build-base linux-headers perl upx zlib-dev zlib-static
}

# download URL FILE
download() {
    if command -v wget > /dev/null 2>&1; then
        wget -q -O "$2" "$1"
    elif command -v curl > /dev/null 2>&1; then
        curl -fsSL -o "$2" "$1"
    else
        echo "sources: needs wget or curl" >&2
        exit 1
    fi
}

# digest ALGORITHM FILE: print the checksum of FILE.
digest() {
    case $1 in
        sha256)
            sha256sum "$2" | cut -d ' ' -f 1
            ;;
        sha3-256)
            if command -v sha3sum > /dev/null 2>&1; then
                sha3sum -a 256 "$2" | cut -d ' ' -f 1
            else
                openssl dgst -sha3-256 -r "$2" | cut -d ' ' -f 1
            fi
            ;;
    esac
}

# fetch DIR FILE URL ALGORITHM CHECKSUM: keep DIR/FILE if its checksum
# is right, otherwise download it and check it.
fetch() {
    if [ -f "$1/$2" ] && [ "$(digest "$4" "$1/$2")" = "$5" ]; then
        echo "$2: present, $4 OK"
        return
    fi
    echo "$2: downloading $3"
    download "$3" "$1/$2.part"
    sum=$(digest "$4" "$1/$2.part")
    if [ "$sum" != "$5" ]; then
        rm -f "$1/$2.part"
        echo "$2: wrong $4 checksum $sum" >&2
        exit 1
    fi
    mv "$1/$2.part" "$1/$2"
    echo "$2: $4 OK"
}

sources() {
    dir=$1
    # shellcheck source=versions.env
    . "$HERE/versions.env"
    mkdir -p "$dir"
    fetch "$dir" "Python-$PYTHON_VERSION.tar.xz" \
        "https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tar.xz" \
        sha256 "$PYTHON_SHA256"
    fetch "$dir" "openssl-$OPENSSL_VERSION.tar.gz" \
        "https://github.com/openssl/openssl/releases/download/openssl-$OPENSSL_VERSION/openssl-$OPENSSL_VERSION.tar.gz" \
        sha256 "$OPENSSL_SHA256"
    fetch "$dir" "sqlite-amalgamation-$SQLITE_VERSION.zip" \
        "https://www.sqlite.org/$SQLITE_YEAR/sqlite-amalgamation-$SQLITE_VERSION.zip" \
        sha3-256 "$SQLITE_SHA3_256"
}

case ${1:-} in
    tools)
        [ $# -eq 1 ] || usage
        tools
        ;;
    sources)
        [ $# -eq 2 ] || usage
        sources "$2"
        ;;
    *)
        usage
        ;;
esac
