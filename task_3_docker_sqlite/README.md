# geoip_loop in Docker

Task: package the geoip_loop.py script into a Docker container, make
sure the script runs when the container starts and that the SQLite
database is created on the host machine, not inside the container.
Bonus: smallest possible image.

`requirements.txt` is the same as in task 2. `geoip_loop.py` is the
task 2 script with one change: its requests session (`make_session()`)
sends a request again when the server has closed the kept-alive
connection.

## Files

| File | Purpose |
| --- | --- |
| `Dockerfile` | Builds a static Python from source, packs it with UPX, final stage is `scratch` |
| `prepare.sh` | Installs the build tools (compiler, perl, upx, zlib), downloads and checks the sources |
| `versions.env` | Versions and checksums of Python, OpenSSL and SQLite |
| `rootfs.sh` | Runs in the build stage, collects the files of the final image |
| `geoip-loop.tar.gz` | Image `geoip-loop:latest` (`docker save`), ready for `docker load` |
| `SHA256SUMS` | Checksum of the archive |
| `.dockerignore` | Sends only the files the build needs (never `data/` or `tests/`) |
| `geoip_loop.py` | The script from task 2, plus retries of dropped connections |
| `requirements.txt` | Same as in task 2 |
| `tests/` | Test of the image: `test-image.sh` with `tls_check.py` and `retry_check.py` |

## Build the image

Needs Docker 23 or newer (BuildKit). Step 1 also needs `wget` or
`curl`, `sha256sum`, and `sha3sum` or `openssl` on the host.

Run these commands in this directory, in this order:

1. Download the Python, OpenSSL and SQLite sources into `sources/` and
   check them against `versions.env`. This step is optional: without
   `sources/` the build downloads them itself.

   ```sh
   sh prepare.sh sources sources
   ```

   Each file ends with `sha256 OK` (SQLite: `sha3-256 OK`). Running it
   again keeps the files that are already right.

2. Build the image, about 8.5 minutes on 4 CPUs:

   ```sh
   docker build -t geoip-loop .
   ```

3. Check the size:

   ```sh
   docker images geoip-loop
   ```

4. Save the image compressed and write its checksum:

   ```sh
   docker save geoip-loop:latest | gzip -9 > geoip-loop.tar.gz
   sha256sum geoip-loop.tar.gz > SHA256SUMS
   ```

What `docker build` does, in order:

1. `python:3.14.10-alpine3.24`: `pip install` of requests and its
   dependencies.
2. `alpine:3.24.4`: `prepare.sh tools` installs the compiler, perl, upx
   and zlib.
3. `prepare.sh sources /src` takes the files from `sources/`, downloads
   the missing ones and checks all of them.
4. Builds OpenSSL 3.5.9 and SQLite 3.54.1 as static libraries, then
   Python 3.14.10 as one static binary with both linked in.
5. `strip`, then `upx --ultra-brute` packs that binary.
6. `rootfs.sh` collects the binary, the standard library as bytecode and
   the dependencies.
7. `scratch`: only those files and the script.

## Load the saved image

```sh
sha256sum -c SHA256SUMS            # geoip-loop.tar.gz: OK
docker load -i geoip-loop.tar.gz   # Loaded image: geoip-loop:latest
docker images geoip-loop           # IMAGE ID 1c9945676b7c
```

## Run

```sh
mkdir -p data
docker run -d --name geoip-loop --restart unless-stopped \
    --user "$(id -u):$(id -g)" \
    -v "$PWD/data:/data" \
    geoip-loop
```

- The script starts with the container (`ENTRYPOINT`) and writes to
  `/data/geoip.db`, which is `./data/geoip.db` on the host.
- `-v "$PWD/data:/data"` mounts the host directory into the container.
- `--user "$(id -u):$(id -g)"` makes the database file belong to you
  instead of a container user.
- `--restart unless-stopped` starts the container again after a crash
  or a reboot, until you stop it yourself.

Create `data/` before the first run. If Docker creates it, it is owned
by root and the script exits with `unable to open database file`.

`/data` is also declared as a `VOLUME`, so without `-v` the database
goes to an anonymous Docker volume, never into the container layer.

The image needs no write access outside `/data` and no capabilities,
so it also runs with `--read-only --cap-drop ALL --security-opt
no-new-privileges`.

## Commands

| Command | What it does |
| --- | --- |
| `docker ps --filter name=geoip-loop` | Shows if the container is running |
| `docker logs -f geoip-loop` | Follows the log, one line per saved record |
| `docker stop geoip-loop` | Stops it: SIGTERM, the script logs `Stopped` and exits 0 |
| `docker start geoip-loop` | Starts the same container again |
| `docker restart geoip-loop` | Stop and start |
| `docker rm geoip-loop` | Removes the container, `data/geoip.db` stays |
| `docker rmi geoip-loop` | Removes the image (load or build it again) |

Read the data on the host:

```sh
sqlite3 data/geoip.db "SELECT id, fetched_at, ip, city, country FROM geoip;"
sqlite3 data/geoip.db "SELECT count(*) FROM geoip;"
```

## Script options

Arguments after the image name go to the script:

| Option | What it does |
| --- | --- |
| `--help` | Shows the options |
| `--once` | Saves one record and exits (exit 0 if it worked) |
| `--interval N` | Seconds between lookups, default 60 |
| `--ips IP [IP ...]` | Looks up these addresses instead of the current IP |
| `--ips-file FILE` | Looks up the addresses in FILE, one per line, `#` comments |
| `--db FILE` | Database file, set by the image to `/data/geoip.db` |

```sh
docker run --rm geoip-loop --help
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/data:/data" geoip-loop --once
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/data:/data" geoip-loop --once --ips 8.8.8.8 1.1.1.1
# data/ips.txt on the host, /data is the working directory
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/data:/data" geoip-loop --once --ips-file ips.txt
docker run -d --name geoip-loop --restart unless-stopped \
    --user "$(id -u):$(id -g)" -v "$PWD/data:/data" geoip-loop --interval 300
```

## Image size

| Image | Unpacked | Compressed | Archive |
| --- | --- | --- | --- |
| `geoip-loop:latest` | 7.6 MB | 6.7 MB | 6.7 MB `geoip-loop.tar.gz` |

Compressed is `CONTENT SIZE` in `docker images`, what `docker pull`
downloads; on Docker 29 `DISK USAGE` is the two added together.

The image has three parts:

- `/usr/local/bin/python3.14` (2.7 MB): one static binary with the C
  modules, OpenSSL, SQLite and zlib linked in, packed with UPX (8.1 MB
  before packing). No shared libraries, no dynamic loader. It unpacks
  itself in memory at start, which takes about 0.2 s.
- `/usr/local/lib/python314.zip` (3.5 MB): the standard library as
  bytecode only (no sources, no docstrings), without packages the
  script cannot use (tkinter, idlelib, ensurepip, unittest, xml, ...).
- requests and its dependencies, also bytecode only, and the script.

## Making Python and OpenSSL smaller

From the compiler to UPX, in the order the build does it:

1. Compiler and linker flags, the same for OpenSSL, SQLite and
   Python (`CFLAGS` in the Dockerfile):
   - `-Os`: optimize for size instead of speed.
   - `-ffunction-sections -fdata-sections` with `-Wl,--gc-sections`:
     every function and variable gets its own section, so the linker
     can drop the ones nothing uses.
   - `-fno-asynchronous-unwind-tables -fno-unwind-tables`: no stack
     unwind tables (`.eh_frame`), C code does not need them.
   - `-fno-pie` with `-no-pie`: a binary at a fixed address, without
     position independent code and its relocations.
2. OpenSSL 3.5.9, built from source as a static TLS 1.2/1.3 client
   library and nothing more (`./Configure` options in the Dockerfile):
   - `no-shared no-module`: static library, no loadable providers.
   - Protocols and features the script does not use are left out:
     QUIC, DTLS, SSLv3, TLS 1.0 and 1.1, engines, the legacy provider,
     compression, SRP, SRTP, NPN, OCSP, certificate transparency, CMS,
     CMP, time stamps and the HTTP client.
   - Old or rare algorithms are left out: IDEA, Camellia, SEED,
     Blowfish, CAST, DES, DSA, MD4, MDC2, RC2, RC4, RC5, Whirlpool,
     SM2, SM3, SM4, ARIA, binary curves, SipHash, Argon2 and the post
     quantum signatures SLH-DSA and ML-DSA.
   - `no-err`: error codes without their text strings.
   - `no-asm`: the C versions of the crypto code instead of the larger
     assembly versions.
   - Only the libraries are built (`make build_libs`): no `openssl`
     command, documentation or tests.
3. SQLite 3.54.1 from the amalgamation, one object file, without
   JSON, extension loading, shared cache and deprecated interfaces
   (`SQLITE_OMIT_*`), with `SQLITE_DEFAULT_MEMSTATUS=0`.
4. Python 3.14.10, built from source:
   - `MODULE_BUILDTYPE=static` and `-static`: all C modules, OpenSSL,
     SQLite, zlib and musl in one binary; no `.so` files, no dynamic
     loader. `LINKFORSHARED=" "`: the symbols are not exported for
     extension modules (no `-export-dynamic`).
   - `--with-lto`: link time optimization over the whole interpreter.
   - C modules the script cannot use are not built
     (`py_cv_module_<name>=n/a`): XML, decimal, the Asian codecs,
     subinterpreters and remote debugging. ctypes, curses, readline,
     dbm, bz2, lzma, zstd, uuid and tkinter are left out because their
     libraries are not installed. `--disable-test-modules` and
     `--without-ensurepip`.
5. `strip` removes the symbol table and debug information. The
   binary is now 8.1 MB, about 2.1 MB of it OpenSSL.
6. UPX with `--ultra-brute` tries every compression method and filter
   and keeps the smallest result. The binary goes from 8.1 MB to
   2.7 MB and unpacks itself in memory when it starts.

## Making the rest of the image smaller

- Standard library (`rootfs.sh`): only bytecode compiled with
  optimization level 2 (no docstrings, no asserts), no `.py` sources,
  in one deflate compressed `python314.zip`. Packages the script
  cannot use are not included: tkinter, turtle, idlelib, ensurepip,
  unittest, venv, xml, xmlrpc, curses, ctypes, pydoc data, the REPL
  and the tests.
- Dependencies (requests, urllib3, idna, charset_normalizer,
  certifi): also bytecode only. The compiled speedups of
  charset_normalizer are removed; a static Python cannot load them
  and its pure Python code is used instead.
- Final image, `FROM scratch`: no Debian or Alpine, no shell, no
  package manager, no shared libraries; only the binary, the bytecode
  and the script.

## Size after each step

Same script and dependencies in every row. Unpacked is the sum of the
files in the image, compressed is what `docker pull` downloads.

| Step | Unpacked | Compressed |
| --- | --- | --- |
| `python:3.14.10-slim-trixie` + `pip install` | 128.7 MB | 48.4 MB |
| `python:3.14.10-alpine3.24` + `pip install` | 60.2 MB | 22.7 MB |
| Files of that Python copied to `scratch` | 22.5 MB | 11.3 MB |
| Static Python with Alpine's OpenSSL and SQLite, `-Os` | 18.9 MB | 9.7 MB |
| Own OpenSSL (no QUIC, no old algorithms) and SQLite builds, LTO | 16.7 MB | 8.6 MB |
| No unwind tables | 15.8 MB | 8.2 MB |
| Fewer OpenSSL algorithms, `no-err` | 15.3 MB | 8.1 MB |
| OpenSSL `no-asm` | 14.1 MB | 7.7 MB |
| No PIE | 13.0 MB | 7.4 MB |
| UPX `--ultra-brute` (this image) | 7.6 MB | 6.7 MB |

## Tests

```sh
sh tests/test-image.sh               # tests geoip-loop:latest, about a minute
```

Needs Docker, sqlite3 and network access. It checks `--help`, a
hardened `--once` run, that the database is on the host and owned by
you, `--ips-file`, a run without `-v`, TLS (verified connections, four
bad badssl.com certificates rejected), that a dropped kept-alive
connection is retried, the restart after `kill -9`, a clean
`docker stop` and the error for a missing host directory. Each check
prints `ok` or `FAILED`; the exit code is 0 only if all passed.

## Notes

- There is no shell in the image. To look inside, use Python:
  `docker run --rm -v "$PWD/data:/data" --entrypoint python3 geoip-loop -c "..."`
- Tracebacks from the standard library show file and line, but no
  source text.
- The default user is 65532 (no name). `--user` overrides it.
