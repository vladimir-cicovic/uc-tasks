# geoip_loop

Every minute `geoip_loop.py` looks up the public IP address of the machine
(api.ipify.org, with ifconfig.me and icanhazip.com as fallbacks), fetches
its geolocation data from `http://ip-api.com/json/<ip>` and stores it in a
SQLite database. It can also look up a list of addresses instead (see
"IP lists" below).

## Why ip-api.com and not geoplugin.net

The task asks for `http://www.geoplugin.net/json.gp?ip=<current_ip>`, but
geoPlugin is no longer free. As of November 2026 it answers every request
with HTTP 403:

    {"geoplugin_status": 403, "geoplugin_message": "geoPlugin API is no
    longer available for free use. To continue access, please upgrade to a
    paid plan"}

ip-api.com is used instead: free, no API key, 45 requests per minute, and
it returns the same kind of data (continent, country, region, city,
coordinates, time zone, currency) plus ISP, AS and proxy/hosting flags.
The free endpoint is HTTP only and for non-commercial use.

## Database

Table `geoip`, one row per fetch:

- `id`, `fetched_at` (UTC, ISO 8601), `ip`
- one column per field returned by the API (`country`, `regionName`,
  `city`, `lat`, `lon`, `timezone`, `currency`, `isp`, ...). If the API
  starts returning a new field, a column for it is added automatically.
- `raw_json`: the complete API response

## Setup

Ubuntu 22.04 with its Python 3.10. `requests` goes into a virtual
environment, not into the global Python. Ubuntu needs the venv module
first:

    sudo apt install python3-venv
    python3 -m venv .venv
    source .venv/bin/activate
    .venv/bin/pip install -r requirements.txt

## Usage

    .venv/bin/python geoip_loop.py                # one record every minute
    .venv/bin/python geoip_loop.py --once         # one record, then exit
    .venv/bin/python geoip_loop.py --db /tmp/geoip.db --interval 60

Stop the loop with Ctrl+C or SIGTERM. The database file defaults to
`geoip.db` in the current directory. See "Database commands" below for
reading and cleaning it.

Instead of the full `.venv/bin/...` paths you can activate the
environment for the current shell:

    source .venv/bin/activate
    python geoip_loop.py --once       # python, pip, pylint now come from .venv
    deactivate                        # back to the system Python

Ubuntu 22.04 also ships a system `requests` (python3-requests 2.25.1), so
`python3 geoip_loop.py` without `.venv` would quietly use that one.

## IP lists

The script has two modes. The batch endpoint is used only with a list:

| Started with | Looked up every run | Endpoint |
|---|---|---|
| no list | 1 address: the current public IP of the machine | `GET http://ip-api.com/json/<ip>` |
| `--ips` or `--ips-file` | every address in the list | `POST http://ip-api.com/batch`, 100 addresses per request |

    .venv/bin/python geoip_loop.py --ips 8.8.8.8 1.1.1.1 2606:4700:4700::1111
    .venv/bin/python geoip_loop.py --ips-file ips.example.txt --once

`--ips-file` takes one address per line; empty lines and everything after
`#` are ignored. Both options can be combined, duplicates are looked up
once. With a list the current IP of the machine is not looked up; add it
to the list if it should be stored too. The file is read once at start,
so restart the loop after changing it. A list with a single address also
goes through the batch endpoint.

Lists go to `http://ip-api.com/batch`, 100 addresses per request: a list
of 250 addresses means 3 requests (100 + 100 + 50) and one write of 250
records in every run. The free plan allows 15 batch requests per minute
(1,500 addresses). When the limit is used up (`X-Rl: 0`), the script waits
`X-Ttl` seconds before the next request. Addresses ip-api.com cannot
locate (for example private ranges) are logged as warnings and not
stored; with `--once` the exit code is then 1.

Each run does all lookups first and only then writes the results to
SQLite, in one transaction. The write is all or nothing: on a database
error no record of that run is saved. If a request fails half way, the
addresses fetched before it are still saved and the whole list is tried
again in the next run. `fetched_at` is the time of the API response, not
of the write.

## Database commands

These need the sqlite3 command line tool (`sudo apt install sqlite3`).
Run them in the directory that holds `geoip.db`.

Describe the table:

    sqlite3 geoip.db ".schema geoip"
    sqlite3 -header -column geoip.db "PRAGMA table_info(geoip);"

Only `id`, `fetched_at`, `ip` and `raw_json` exist from the start. The
columns for the API fields are added with the first stored record.

Select:

    # last 20 records
    sqlite3 -header -column geoip.db "SELECT id, fetched_at, ip, city, country, isp FROM geoip ORDER BY id DESC LIMIT 20;"

    # number of records
    sqlite3 geoip.db "SELECT COUNT(*) FROM geoip;"

    # all records for one address
    sqlite3 -header -column geoip.db "SELECT * FROM geoip WHERE ip = '8.8.8.8';"

    # records from one day (fetched_at is UTC, ISO 8601)
    sqlite3 -header -column geoip.db "SELECT id, fetched_at, ip, city FROM geoip WHERE fetched_at LIKE '2026-11-10%';"

    # how often each address was looked up
    sqlite3 -header -column geoip.db "SELECT ip, COUNT(*) AS records, MIN(fetched_at) AS first, MAX(fetched_at) AS last FROM geoip GROUP BY ip;"

    # export everything to CSV
    sqlite3 -header -csv geoip.db "SELECT * FROM geoip;" > geoip.csv

Delete records (this also works while the loop is running):

    # one record by id
    sqlite3 geoip.db "DELETE FROM geoip WHERE id = 5;"

    # all records for one address
    sqlite3 geoip.db "DELETE FROM geoip WHERE ip = '8.8.8.8';"

    # records older than 30 days
    sqlite3 geoip.db "DELETE FROM geoip WHERE fetched_at < strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '-30 days');"

    # all records (new ids continue after the last deleted one)
    sqlite3 geoip.db "DELETE FROM geoip;"

Empty the whole table. The table and its columns stay, ids start again
from 1 and VACUUM gives the freed space back to the disk:

    sqlite3 geoip.db "DELETE FROM geoip; DELETE FROM sqlite_sequence WHERE name = 'geoip'; VACUUM;"

Drop the table completely. Stop the loop first: the script creates the
table only when it starts, so a running loop would fail on every insert.
The next start creates the table again, and the API columns come back
with the first record:

    sqlite3 geoip.db "DROP TABLE geoip; VACUUM;"

Deleted records cannot be restored, so make a copy first if needed:

    cp geoip.db geoip.db.bak

## Lint

    .venv/bin/pip install -r requirements-dev.txt
    .venv/bin/pylint geoip_loop.py
    .venv/bin/pycodestyle geoip_loop.py
