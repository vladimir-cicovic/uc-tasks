#!/usr/bin/env python3
"""Lab service: tries to keep FD_HOG_FILES files open.

With a low LimitNOFILE it fails with EMFILE and logs the error
every FD_HOG_INTERVAL seconds.
"""
import os
import sys
import time

WANT = int(os.environ.get("FD_HOG_FILES", "100"))
INTERVAL = float(os.environ.get("FD_HOG_INTERVAL", "2"))


def main():
    handles = []
    while True:
        while len(handles) < WANT:
            try:
                handles.append(open("/dev/null", "rb"))
            except OSError as err:
                print(f"fd-hog: cannot open more files: {err}", file=sys.stderr, flush=True)
                break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
