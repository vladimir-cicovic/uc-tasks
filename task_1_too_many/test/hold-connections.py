#!/usr/bin/env python3
"""Open many TCP connections to a server and keep them open for a while.

Usage: python3 hold-connections.py HOST [--port 80] [--count 200] [--seconds 10]
"""
import argparse
import socket
import time


def main():
    parser = argparse.ArgumentParser(description="Hold many TCP connections open.")
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seconds", type=float, default=10)
    args = parser.parse_args()

    conns = []
    for _ in range(args.count):
        try:
            conns.append(socket.create_connection((args.host, args.port), timeout=3))
        except OSError as err:
            print(f"connection {len(conns) + 1} failed: {err}")
            break

    print(f"holding {len(conns)} connections for {args.seconds:g} s")
    time.sleep(args.seconds)
    for c in conns:
        c.close()
    print("closed")


if __name__ == "__main__":
    main()
