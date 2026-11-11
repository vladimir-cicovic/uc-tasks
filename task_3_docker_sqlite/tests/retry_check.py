"""Check that the script retries a request whose connection was closed.

A local server answers the first request on every connection and then
closes the connection without answering the next one. That is what
ip-api.com does when its idle timeout hits just as the next request
arrives ("RemoteDisconnected"). A plain requests session must fail on
it, the session of geoip_loop.py must not.

Usage (from tests/test-image.sh):
    docker run --rm -v "$PWD/tests/retry_check.py:/t.py:ro" \
        --entrypoint python3 geoip-loop /t.py /app/geoip_loop.py
"""

import importlib.util
import socket
import sys
import threading

import requests

RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 2\r\n"
    b"\r\n"
    b"ok"
)
METHODS = ("GET", "GET", "POST", "GET")


def load_script(path):
    """Import geoip_loop.py from path."""
    spec = importlib.util.spec_from_file_location("geoip_loop", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_request(conn):
    """Read one HTTP request, return False if the client closed."""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            return False
        data += chunk
    head, _, body = data.partition(b"\r\n\r\n")
    length = 0
    for line in head.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1])
    while len(body) < length:
        body += conn.recv(4096)
    return True


def serve(listener):
    """Answer one request per connection, drop the second one."""
    while True:
        conn, _ = listener.accept()
        with conn:
            if read_request(conn):
                conn.sendall(RESPONSE)
            read_request(conn)


def answered(name, session, url):
    """Send METHODS to url, return how many got an answer."""
    count = 0
    for method in METHODS:
        try:
            response = session.request(method, url, json=[], timeout=5)
            count += response.text == "ok"
        except requests.RequestException as error:
            print(f"        {name}: {method} failed: {error}")
    print(f"{name}: {count} of {len(METHODS)} requests answered")
    return count


def main():
    """Run the check, return the exit code."""
    path = sys.argv[1] if len(sys.argv) > 1 else "/app/geoip_loop.py"
    script = load_script(path)
    listener = socket.create_server(("127.0.0.1", 0))
    threading.Thread(target=serve, args=(listener,), daemon=True).start()
    url = f"http://127.0.0.1:{listener.getsockname()[1]}/json/192.0.2.1"
    with requests.Session() as plain:
        before = answered("plain requests session", plain, url)
    with script.make_session() as session:
        after = answered("geoip_loop session", session, url)
    if before < len(METHODS) and after == len(METHODS):
        print("ok      dropped connections are retried")
        return 0
    print("FAILED  dropped connections are not retried")
    return 1


if __name__ == "__main__":
    sys.exit(main())
