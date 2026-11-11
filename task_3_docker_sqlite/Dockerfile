# Stage 1: requests and its dependencies (pure Python packages).
FROM python:3.14.10-alpine3.24 AS deps

COPY requirements.txt /build/
RUN pip install --no-cache-dir --no-compile --disable-pip-version-check \
        --root-user-action=ignore --target /deps -r /build/requirements.txt

# Stage 2: a static Python built for size, with OpenSSL and SQLite also
# built from source with only what the script needs, packed with UPX.
FROM alpine:3.24.4 AS build

SHELL ["/bin/ash", "-eo", "pipefail", "-c"]

# Build tools only (compiler, perl, upx, zlib), nothing from this stage
# ends up in the final image.
COPY prepare.sh /build/
RUN sh /build/prepare.sh tools

# Sources pinned in versions.env. Files that "prepare.sh sources sources"
# put into sources/ on the host are used, the rest is downloaded; all of
# them are checked against their checksums.
COPY versions.env /build/
COPY sources* /src/
RUN sh /build/prepare.sh sources /src

# -Os: optimize for size. No unwind tables: C code does not need them.
# No PIE: about 1 MB smaller, but the binary loads at a fixed address.
ENV CFLAGS="-Os -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables -fno-unwind-tables -fno-pie"

# OpenSSL as a TLS 1.2/1.3 client library. no-asm: plain C crypto code,
# smaller and slower. no-err: error codes without text.
WORKDIR /src/openssl
RUN . /build/versions.env \
    && tar -xzf "../openssl-$OPENSSL_VERSION.tar.gz" --strip-components=1 \
    && ./Configure linux-x86_64 --prefix=/opt/openssl --libdir=lib \
        --openssldir=/etc/ssl no-shared no-module no-asm no-err no-docs \
        no-tests no-legacy no-engine no-comp no-dtls no-ssl3 no-tls1 \
        no-tls1_1 no-quic no-srp no-srtp no-nextprotoneg no-ocsp no-ct \
        no-cms no-cmp no-ts no-http no-idea no-camellia no-seed no-bf \
        no-cast no-des no-dsa no-md4 no-mdc2 no-rc2 no-rc4 no-rc5 \
        no-whirlpool no-sm2 no-sm3 no-sm4 no-aria no-ec2m no-siphash \
        no-argon2 no-slh-dsa no-ml-dsa $CFLAGS > /dev/null \
    && { make -j"$(nproc)" build_libs > /tmp/make.log 2>&1 \
        || { tail -40 /tmp/make.log; exit 1; }; } \
    && make install_dev > /dev/null

# SQLite without the features Python and the script do not use.
WORKDIR /src/sqlite
RUN . /build/versions.env \
    && unzip -q -j "../sqlite-amalgamation-$SQLITE_VERSION.zip" \
    && mkdir -p /opt/sqlite/lib /opt/sqlite/include \
    && cc $CFLAGS -DSQLITE_DQS=0 -DSQLITE_DEFAULT_MEMSTATUS=0 \
        -DSQLITE_OMIT_DEPRECATED -DSQLITE_OMIT_SHARED_CACHE \
        -DSQLITE_OMIT_LOAD_EXTENSION -DSQLITE_OMIT_JSON -DSQLITE_USE_ALLOCA \
        -c sqlite3.c -o sqlite3.o \
    && ar rcs /opt/sqlite/lib/libsqlite3.a sqlite3.o \
    && cp sqlite3.h sqlite3ext.h /opt/sqlite/include/

# Python with all C modules linked into one static binary. Modules the
# script cannot use are not built (XML, decimal, Asian codecs,
# subinterpreters, remote debugging); those needing libraries that are
# not installed (ctypes, curses, readline, dbm, bz2, lzma, zstd, uuid,
# tkinter) are left out by configure.
WORKDIR /src/python
RUN . /build/versions.env \
    && tar -xf "../Python-$PYTHON_VERSION.tar.xz" --strip-components=1 \
    && ./configure --prefix=/usr/local --disable-shared --disable-test-modules \
        --without-ensurepip --with-lto \
        --with-openssl=/opt/openssl --with-openssl-rpath=no \
        LIBSQLITE3_CFLAGS="-I/opt/sqlite/include" \
        LIBSQLITE3_LIBS="-L/opt/sqlite/lib -lsqlite3" \
        LDFLAGS="-static -no-pie -Wl,--gc-sections" \
        MODULE_BUILDTYPE=static \
        py_cv_module_pyexpat=n/a py_cv_module__elementtree=n/a \
        py_cv_module__decimal=n/a py_cv_module__multibytecodec=n/a \
        py_cv_module__codecs_cn=n/a py_cv_module__codecs_hk=n/a \
        py_cv_module__codecs_iso2022=n/a py_cv_module__codecs_jp=n/a \
        py_cv_module__codecs_kr=n/a py_cv_module__codecs_tw=n/a \
        py_cv_module__interpreters=n/a py_cv_module__interpchannels=n/a \
        py_cv_module__interpqueues=n/a py_cv_module__remote_debugging=n/a \
        > /dev/null \
    && { make -j"$(nproc)" LINKFORSHARED=" " > /tmp/make.log 2>&1 \
        || { tail -40 /tmp/make.log; exit 1; }; } \
    && { make install LINKFORSHARED=" " > /tmp/install.log 2>&1 \
        || { tail -40 /tmp/install.log; exit 1; }; } \
    && strip "/usr/local/bin/python${PYTHON_VERSION%.*}"

# Pack the binary (Python with OpenSSL, SQLite and zlib in it) with UPX
# at the highest compression. It unpacks itself in memory when it starts.
RUN . /build/versions.env \
    && upx -q --ultra-brute "/usr/local/bin/python${PYTHON_VERSION%.*}" > /dev/null

COPY --from=deps /deps /deps
COPY rootfs.sh /build/
RUN sh /build/rootfs.sh /rootfs /deps

# Final image: no shell, no package manager, no shared libraries, only
# the static Python, its bytecode and the script.
FROM scratch

COPY --from=build /rootfs/ /
COPY geoip_loop.py /app/

USER 65532:65532
WORKDIR /data
# The database lives here; mount a host directory on it.
VOLUME ["/data"]

ENTRYPOINT ["/usr/local/bin/python3", "/app/geoip_loop.py", "--db", "/data/geoip.db"]
