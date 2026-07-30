#!/usr/bin/env bash
# Shared entrypoint for the bot + manager containers.
# adb does NOT auto-connect to a remote TCP device, so we `adb connect` the
# Redroid container and wait for Android to finish booting before exec'ing the
# real command. Idempotent + safe to re-run (healthchecks reconnect too).
set -euo pipefail

ADB_TARGET="${ADB_TARGET:-redroid:5555}"

echo "[entrypoint] target Redroid adb = ${ADB_TARGET}"

# The MANAGER serves its web UI without the emulator (live view degrades gracefully),
# so it must not block on Android boot. Set WAIT_FOR_BOOT=0 for the manager service.
if [ "${WAIT_FOR_BOOT:-1}" = "0" ]; then
    echo "[entrypoint] WAIT_FOR_BOOT=0 — starting immediately (no emulator wait)."
    exec "$@"
fi

adb start-server >/dev/null 2>&1 || true

booted=0
for attempt in $(seq 1 150); do   # up to ~5 min: Redroid cold-boot is slow
    adb connect "${ADB_TARGET}" >/dev/null 2>&1 || true
    if adb -s "${ADB_TARGET}" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' | grep -q '^1$'; then
        booted=1
        echo "[entrypoint] Android boot_completed on ${ADB_TARGET} (after ${attempt} tries)"
        break
    fi
    sleep 2
done

if [ "${booted}" -ne 1 ]; then
    echo "[entrypoint] WARNING: ${ADB_TARGET} did not report boot_completed; starting anyway." >&2
fi

exec "$@"
