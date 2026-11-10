#!/usr/bin/env python3
"""Store geolocation data of the current public IP address in SQLite.

Every minute the script finds the public IP address of this machine,
asks the ip-api.com JSON API about it and saves all returned fields,
together with a UTC timestamp, into a SQLite database. It runs until
it is stopped with Ctrl+C or SIGTERM.

With --ips or --ips-file it looks up the given addresses instead,
100 per request through the ip-api.com batch endpoint. All lookups of
a run are done first, then the results are saved in one transaction.
"""

import argparse
import functools
import ipaddress
import json
import logging
import re
import signal
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone

import requests

# Free replacement for geoplugin.net, which became a paid-only API.
# The free ip-api.com endpoints are HTTP only and allow 45 single or
# 15 batch requests per minute.
GEOIP_URL = "http://ip-api.com/json/{ip}"
BATCH_URL = "http://ip-api.com/batch"
BATCH_SIZE = 100
# Field mask that asks ip-api.com for every available field.
GEOIP_FIELDS = "66846719"
IP_LOOKUP_URLS = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
)
REQUEST_TIMEOUT = 10
DEFAULT_DB_PATH = "geoip.db"
DEFAULT_INTERVAL = 60

# Columns every record has. Each API field gets an extra column.
BASE_COLUMNS = ("id", "fetched_at", "ip", "raw_json")
COLUMN_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

LOGGER = logging.getLogger("geoip_loop")


class FetchError(Exception):
    """Raised when the geolocation data cannot be fetched."""


def utc_now():
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_public_ip(session):
    """Return the public IP address of this machine."""
    for url in IP_LOOKUP_URLS:
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return str(ipaddress.ip_address(response.text.strip()))
        except (requests.RequestException, ValueError) as error:
            LOGGER.warning("IP lookup via %s failed: %s", url, error)
    raise FetchError("could not find the public IP address")


def wait_for_rate_limit(response):
    """Sleep until the ip-api.com rate limit resets if it is used up."""
    # X-Rl: requests left in this window, X-Ttl: seconds until reset.
    if response.headers.get("X-Rl") == "0":
        delay = int(response.headers.get("X-Ttl", "60"))
        LOGGER.info("ip-api.com rate limit reached, waiting %d s", delay)
        time.sleep(delay)


def get_geoip(session, ip_address):
    """Return (fetched_at, data) from ip-api.com for one address."""
    response = session.get(
        GEOIP_URL.format(ip=ip_address),
        params={"fields": GEOIP_FIELDS},
        timeout=REQUEST_TIMEOUT,
    )
    fetched_at = utc_now()
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise FetchError("unexpected response from ip-api.com")
    wait_for_rate_limit(response)
    return fetched_at, data


def get_geoip_batch(session, ip_addresses):
    """Return (fetched_at, data list) for up to BATCH_SIZE addresses."""
    response = session.post(
        BATCH_URL,
        params={"fields": GEOIP_FIELDS},
        json=ip_addresses,
        timeout=REQUEST_TIMEOUT,
    )
    fetched_at = utc_now()
    response.raise_for_status()
    data = response.json()
    if (
        not isinstance(data, list)
        or len(data) != len(ip_addresses)
        or not all(isinstance(item, dict) for item in data)
    ):
        raise FetchError("unexpected batch response from ip-api.com")
    wait_for_rate_limit(response)
    return fetched_at, data


def lookup_current_ip(session):
    """Yield (fetched_at, ip, data) for the public IP of this machine."""
    ip_address = get_public_ip(session)
    fetched_at, data = get_geoip(session, ip_address)
    yield fetched_at, ip_address, data


def lookup_ip_list(session, ip_addresses):
    """Yield (fetched_at, ip, data) for every address, in batches."""
    for start in range(0, len(ip_addresses), BATCH_SIZE):
        chunk = ip_addresses[start:start + BATCH_SIZE]
        fetched_at, data_list = get_geoip_batch(session, chunk)
        for ip_address, data in zip(chunk, data_list):
            yield fetched_at, ip_address, data


def fetch_all(session, ip_list):
    """Do every lookup of one run, return (results, all_ok).

    results holds (fetched_at, ip, data) for each address ip-api.com
    could locate. A failed request stops the run; the results fetched
    before it are still returned.
    """
    if ip_list:
        lookups = lookup_ip_list(session, ip_list)
    else:
        lookups = lookup_current_ip(session)
    results = []
    all_ok = True
    try:
        for fetched_at, ip_address, data in lookups:
            if data.get("status") == "success":
                results.append((fetched_at, ip_address, data))
                continue
            # e.g. "reserved range" for private addresses
            LOGGER.warning(
                "Lookup of %s failed: %s",
                ip_address,
                data.get("message", "unknown error"),
            )
            all_ok = False
    except (requests.RequestException, ValueError, FetchError) as error:
        LOGGER.error("Fetching geolocation data failed: %s", error)
        all_ok = False
    return results, all_ok


def init_db(conn):
    """Create the geoip table if it does not exist yet."""
    with conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS geoip ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "fetched_at TEXT NOT NULL, "
            "ip TEXT NOT NULL, "
            "raw_json TEXT NOT NULL)"
        )


def add_missing_columns(conn, names):
    """Add a column for every API field that does not have one yet."""
    rows = conn.execute("PRAGMA table_info(geoip)").fetchall()
    existing = {row[1].lower() for row in rows}
    for name in names:
        if name.lower() not in existing:
            # Safe to quote: names are checked against COLUMN_NAME.
            conn.execute(f'ALTER TABLE geoip ADD COLUMN "{name}"')
            existing.add(name.lower())


def to_db_value(value):
    """Convert a JSON value to a type SQLite can store."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def insert_record(conn, fetched_at, ip_address, data):
    """Insert one API response, return the row id.

    The caller is responsible for the transaction.
    """
    fields = {
        key: to_db_value(value)
        for key, value in data.items()
        if COLUMN_NAME.fullmatch(key) and key.lower() not in BASE_COLUMNS
    }
    record = {
        "fetched_at": fetched_at,
        "ip": ip_address,
        "raw_json": json.dumps(data, ensure_ascii=False),
        **fields,
    }
    add_missing_columns(conn, fields)
    columns = ", ".join(f'"{name}"' for name in record)
    placeholders = ", ".join("?" * len(record))
    cursor = conn.execute(
        f"INSERT INTO geoip ({columns}) VALUES ({placeholders})",
        list(record.values()),
    )
    return cursor.lastrowid


def save_records(conn, results):
    """Save all results in one transaction, return the new row ids."""
    with conn:
        return [
            insert_record(conn, fetched_at, ip_address, data)
            for fetched_at, ip_address, data in results
        ]


def fetch_and_store(session, conn, ip_list=None):
    """Look up all addresses first, then save them in one transaction.

    Without ip_list the public IP address of this machine is looked up,
    otherwise every address in ip_list. Returns True if every lookup
    succeeded and was saved.
    """
    results, all_ok = fetch_all(session, ip_list)
    if not results:
        return all_ok
    try:
        row_ids = save_records(conn, results)
    except sqlite3.Error as error:
        LOGGER.error("Saving to the database failed, nothing saved: %s", error)
        return False
    for row_id, (_, ip_address, data) in zip(row_ids, results):
        LOGGER.info(
            "Saved record %d: %s, %s, %s",
            row_id,
            ip_address,
            data.get("city") or "-",
            data.get("country") or "-",
        )
    if ip_list:
        LOGGER.info("Saved %d of %d addresses", len(row_ids), len(ip_list))
    return all_ok


def run_forever(job, interval):
    """Call job every interval seconds until interrupted."""
    next_run = time.monotonic()
    while True:
        job()
        # Fixed schedule; skip missed runs (e.g. after a suspend).
        next_run = max(next_run + interval, time.monotonic())
        time.sleep(max(0.0, next_run - time.monotonic()))


def positive_int(text):
    """Argparse type for a whole number greater than zero."""
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return value


def ip_arg(text):
    """Argparse type for an IPv4 or IPv6 address."""
    try:
        return str(ipaddress.ip_address(text.strip()))
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def ip_file_arg(path):
    """Argparse type that reads IP addresses from a file, one per line."""
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    addresses = []
    for number, line in enumerate(lines, start=1):
        text = line.split("#", 1)[0].strip()
        if not text:
            continue
        try:
            addresses.append(ip_arg(text))
        except argparse.ArgumentTypeError as error:
            raise argparse.ArgumentTypeError(
                f"{path}, line {number}: {error}"
            ) from error
    if not addresses:
        raise argparse.ArgumentTypeError(f"{path}: no IP addresses found")
    return addresses


def parse_args(argv=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help="SQLite database file (default: %(default)s)",
    )
    parser.add_argument(
        "--interval",
        type=positive_int,
        default=DEFAULT_INTERVAL,
        help="seconds between fetches (default: %(default)s)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="fetch once and exit",
    )
    parser.add_argument(
        "--ips",
        nargs="+",
        type=ip_arg,
        default=[],
        metavar="IP",
        help="look up these addresses instead of the current IP",
    )
    parser.add_argument(
        "--ips-file",
        type=ip_file_arg,
        metavar="FILE",
        help="look up the addresses in FILE (one per line, # comments)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    """Run the fetch loop, return the exit code."""
    args = parse_args(argv)
    # Keep the order, drop duplicates.
    ip_list = list(dict.fromkeys(args.ips + (args.ips_file or [])))
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    # Stop on SIGTERM the same way as on Ctrl+C.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    if ip_list:
        target = f"{len(ip_list)} listed IP address(es)"
    else:
        target = "the current IP address"
    try:
        with closing(sqlite3.connect(args.db)) as conn:
            init_db(conn)
            with requests.Session() as session:
                job = functools.partial(
                    fetch_and_store, session, conn, ip_list
                )
                if args.once:
                    return 0 if job() else 1
                LOGGER.info(
                    "Looking up %s every %d s, saving to %s, Ctrl+C to stop",
                    target,
                    args.interval,
                    args.db,
                )
                run_forever(job, args.interval)
    except KeyboardInterrupt:
        LOGGER.info("Stopped")
    except sqlite3.Error as error:
        LOGGER.error("Cannot use database %s: %s", args.db, error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
