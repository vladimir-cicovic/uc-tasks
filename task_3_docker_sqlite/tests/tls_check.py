"""Check TLS inside the image.

The HTTPS services the script uses must connect with a verified
certificate, and bad certificates must be rejected. badssl.com resets
connections now and then, so each bad certificate URL is tried up to
five times until its TLS error shows up.

Usage (from tests/test-image.sh):
    docker run --rm -v "$PWD/tests/tls_check.py:/t.py:ro" \
        --entrypoint python3 geoip-loop /t.py
"""

import socket
import ssl
import sys
import time

import certifi
import requests

GOOD_HOSTS = ("api.ipify.org", "ifconfig.me", "icanhazip.com")
BAD_URLS = (
    "https://expired.badssl.com/",
    "https://wrong.host.badssl.com/",
    "https://self-signed.badssl.com/",
    "https://untrusted-root.badssl.com/",
)
ATTEMPTS = 5


def check_good(context, host):
    """Connect to host with TLS, return True if it worked."""
    try:
        with socket.create_connection((host, 443), timeout=10) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                print(f"ok      {host}: {tls.version()} {tls.cipher()[0]}")
                return True
    except OSError as error:
        print(f"FAILED  {host}: {error}")
        return False


def check_bad(url):
    """Request url, return True if its certificate is rejected."""
    for _ in range(ATTEMPTS):
        try:
            requests.get(url, timeout=10)
        except requests.exceptions.SSLError:
            print(f"ok      {url}: rejected")
            return True
        except requests.exceptions.ConnectionError:
            time.sleep(3)
            continue
        print(f"FAILED  {url}: accepted")
        return False
    print(f"FAILED  {url}: no answer in {ATTEMPTS} attempts")
    return False


def main():
    """Run all checks, return the exit code."""
    context = ssl.create_default_context(cafile=certifi.where())
    results = [check_good(context, host) for host in GOOD_HOSTS]
    results += [check_bad(url) for url in BAD_URLS]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
