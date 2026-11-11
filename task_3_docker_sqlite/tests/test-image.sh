#!/bin/sh
# Test the geoip-loop image on this host: options, hardened run,
# database on the host, TLS, retry of dropped connections, restart
# policy and stop. Needs Docker, sqlite3 and network access; takes
# about a minute.
#
# Usage: sh tests/test-image.sh [IMAGE]    (default: geoip-loop:latest)
set -u

IMAGE=${1:-geoip-loop:latest}
TESTS=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
NAME=geoip-loop-test
ME="$(id -u):$(id -g)"
FAILED=0

cleanup() {
    docker rm -f "$NAME" > /dev/null 2>&1
    rm -rf "$WORK"
}
trap cleanup EXIT

# check DESCRIPTION COMMAND [ARG...]: run COMMAND, print ok or FAILED
# and, on failure, its output.
check() {
    description=$1
    shift
    if "$@" > "$WORK/out" 2>&1; then
        echo "ok      $description"
    else
        echo "FAILED  $description"
        sed 's/^/        /' "$WORK/out"
        FAILED=$((FAILED + 1))
    fi
}

run() {
    docker run --rm --user "$ME" -v "$WORK/data:/data" "$IMAGE" "$@"
}

help_works() {
    docker run --rm "$IMAGE" --help | grep -q '^usage: geoip_loop.py'
}

once_hardened() {
    docker run --rm --user "$ME" -v "$WORK/data:/data" --read-only \
        --cap-drop ALL --security-opt no-new-privileges "$IMAGE" --once
}

db_on_host() {
    [ "$(stat -c %u "$WORK/data/geoip.db")" = "$(id -u)" ] \
        && [ "$(sqlite3 "$WORK/data/geoip.db" 'SELECT count(*) FROM geoip;')" = 1 ]
}

ips_file() {
    printf '8.8.8.8\n# comment\n1.1.1.1\n' > "$WORK/data/ips.txt"
    out=$(run --once --ips-file ips.txt 2>&1)
    echo "$out"
    echo "$out" | grep -q 'Saved 2 of 2 addresses'
}

anonymous_volume() {
    docker run --rm "$IMAGE" --once
}

tls() {
    docker run --rm -v "$TESTS/tls_check.py:/t.py:ro" \
        --entrypoint python3 "$IMAGE" /t.py
}

retry() {
    docker run --rm -v "$TESTS/retry_check.py:/t.py:ro" \
        --entrypoint python3 "$IMAGE" /t.py /app/geoip_loop.py
}

# wait_for TEXT: wait up to 30 s for TEXT in the container log.
wait_for() {
    for _ in $(seq 30); do
        docker logs "$NAME" 2>&1 | grep -q "$1" && return 0
        sleep 1
    done
    return 1
}

loop_and_restart() {
    docker run -d --name "$NAME" --restart unless-stopped --user "$ME" \
        -v "$WORK/data:/data" "$IMAGE" --interval 5 > /dev/null \
        && wait_for 'Saved record 4' \
        && wait_for 'Saved record 5' \
        && kill -9 "$(docker inspect -f '{{.State.Pid}}' "$NAME")" \
        && sleep 3 \
        && [ "$(docker inspect -f '{{.State.Running}} {{.RestartCount}}' "$NAME")" = "true 1" ]
}

stop_cleanly() {
    docker stop "$NAME" > /dev/null \
        && [ "$(docker inspect -f '{{.State.ExitCode}}' "$NAME")" = 0 ] \
        && docker logs "$NAME" 2>&1 | tail -1 | grep -q 'INFO Stopped'
}

missing_dir() {
    out=$(docker run --rm --user "$ME" -v "$WORK/missing:/data" "$IMAGE" --once 2>&1)
    status=$?
    echo "$out"
    [ "$status" = 1 ] && echo "$out" | grep -q 'unable to open database file'
}

echo "Testing $IMAGE"
mkdir "$WORK/data"
check "--help shows the options" help_works
check "--once with --read-only --cap-drop ALL" once_hardened
check "database on the host, owned by $(id -un)" db_on_host
check "--ips-file with a comment line" ips_file
check "without -v (anonymous volume, user 65532)" anonymous_volume
check "TLS verified, bad certificates rejected" tls
check "dropped connections are retried" retry
check "loop, restart after kill -9" loop_and_restart
check "docker stop: exit 0, logs Stopped" stop_cleanly
check "missing host directory: clear error, exit 1" missing_dir

if [ "$FAILED" -eq 0 ]; then
    echo "All tests passed"
else
    echo "$FAILED test(s) failed"
    exit 1
fi
