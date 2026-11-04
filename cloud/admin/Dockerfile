# SweetYaar Admin on Cloud Run: the log viewer over the toys' cloud uploads.
# Built by `make deploy-admin` from a staged context: requirements.txt,
# tools/devlog.py, tools/logviewer/ and firmware/esp32/src/DevLogEvents.h.

# GDB for decoding core dumps: Espressif's standalone release. The firmware
# toolchain's own Linux GDB (esp-2021r2-patch5, PlatformIO's on the Mac) needs
# libpython2.7, which current Debian no longer ships; esp-coredump only needs
# GDB to read the ELF and the core, which any newer release does.
FROM debian:bookworm-slim AS gdb
ARG GDB=https://github.com/espressif/binutils-gdb/releases/download/esp-gdb-v16.2_20250324/xtensa-esp-elf-gdb-16.2_20250324-x86_64-linux-gnu.tar.gz
ARG GDB_SHA256=27b58ab12248e04277c4fdc74038cf0a001d5142df091ab94939ad35053738fd
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL -o /tmp/gdb.tar.gz "$GDB" \
    && echo "$GDB_SHA256  /tmp/gdb.tar.gz" | sha256sum -c - \
    && mkdir /opt/xtensa \
    && tar -xzf /tmp/gdb.tar.gz -C /opt/xtensa --strip-components=1

FROM python:3.12-slim
COPY --from=gdb /opt/xtensa /opt/xtensa
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY firmware/esp32/src/DevLogEvents.h /app/firmware/esp32/src/DevLogEvents.h
COPY tools/devlog.py /app/tools/devlog.py
COPY tools/logviewer /app/tools/logviewer
ENV XTENSA_GDB=/opt/xtensa/bin/xtensa-esp32-elf-gdb PYTHONUNBUFFERED=1
USER nobody
ENV HOME=/tmp
CMD ["python", "/app/tools/logviewer/server.py", "--cloud-only"]
