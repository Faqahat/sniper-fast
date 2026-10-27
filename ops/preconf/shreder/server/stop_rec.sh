#!/bin/bash
# FRA (root): graceful stop (SIGTERM -> recorder flushes and closes its files), SIGKILL only after 30 s.
# usage: sudo /root/shreder/stop_rec.sh RUN
set -u
RUN=${1:?RUN name}; OUT=${SHREDER_BASE:-/root/shreder}/data/$RUN
[ -f "$OUT/rec.pid" ] || { echo "no pid file"; exit 1; }
P=$(cat "$OUT/rec.pid")
case "$P" in ''|*[!0-9]*) echo "bad pid '$P'"; exit 1;; esac
[ "$P" -gt 1 ] || { echo "bad pid $P"; exit 1; }
grep -q shreder_rec "/proc/$P/cmdline" 2>/dev/null || { echo "pid $P is not shreder_rec (already stopped?)"; exit 0; }
if ! kill -0 "$P" 2>/dev/null; then echo "not running (pid $P)"; exit 0; fi
kill -TERM "$P"
for i in $(seq 1 60); do kill -0 "$P" 2>/dev/null || { echo "stopped pid $P"; ( chronyc tracking 2>/dev/null || true ) > "$OUT/chrony_end.txt"; tail -2 "$OUT/rec.log" | cut -c1-400; exit 0; }; sleep 0.5; done
echo "still alive after 30 s -> SIGKILL"; kill -KILL "$P"
( chronyc tracking 2>/dev/null || true ) > "$OUT/chrony_end.txt"
