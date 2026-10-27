#!/bin/bash
# FRA (run as root via sudo): start the Shreder recorder in the background, detached, nice 10 / ionice best-effort 7.
# usage: sudo /root/shreder/run_rec.sh RUN MINUTES
# env:   FILTER=all|broad (default all = unfiltered streams, auto-fallback to broad if refused)
#        MODE=two|both    two = pre and bin on separate connections (default, cleanest timing);
#                         both = ONE subscription carrying both sources (only if Shreder allows a single connection)
#        EXCLUDE_VOTES=1  account_exclude=[Vote program] on the unfiltered Binary stream (cuts volume; not allowed on preconf)
#        PUMP_PAIR=1      also record server-side pump-filtered streams fpre/fbin (2 extra subscriptions)
#        EXTRA="..."      extra shreder_rec args
set -eu
RUN=${1:?RUN name}; MIN=${2:?minutes}
BASE=${SHREDER_BASE:-/root/shreder}; OUT=$BASE/data/$RUN; BIN=$BASE/bin/shreder_rec
FILTER=${FILTER:-all}
mkdir -p "$OUT"
if pgrep -f "[s]hreder_rec --out $OUT " >/dev/null; then echo "already running pid $(cat "$OUT/rec.pid")"; exit 1; fi
ARGS=(--out "$OUT" --minutes "$MIN" --status-secs 30 --quiet --queue 100000)
if [ "${MODE:-two}" = both ]; then ARGS+=(--stream "mix:both:$FILTER"); else ARGS+=(--stream "pre:pre:$FILTER" --stream "bin:bin:$FILTER"); fi
if [ "${EXCLUDE_VOTES:-0}" = 1 ]; then ARGS+=(--exclude-votes); fi
if [ "${PUMP_PAIR:-0}" = 1 ]; then ARGS+=(--stream fpre:pre:pump --stream fbin:bin:pump); fi
# shellcheck disable=SC2206
[ -n "${EXTRA:-}" ] && ARGS+=($EXTRA)
sha256sum "$BIN" > "$OUT/binary.sha256"
( chronyc tracking 2>/dev/null || true ) > "$OUT/chrony_start.txt"
setsid nohup nice -n 10 ionice -c2 -n7 "$BIN" "${ARGS[@]}" > "$OUT/stdout.log" 2>&1 < /dev/null &
sleep 1
RP=$(pgrep -f "[s]hreder_rec --out $OUT " | head -1)
if [ -n "$RP" ] && [ "$RP" -gt 1 ]; then echo "$RP" > "$OUT/rec.pid"; else rm -f "$OUT/rec.pid"; fi
# OOM order on FRA: feed race (800) dies first, then this recorder (500), never collect.py/engines (0)
[ -n "$RP" ] && [ "$RP" -gt 1 ] && echo 500 > "/proc/$RP/oom_score_adj" 2>/dev/null || true
if [ -n "$RP" ] && [ "$RP" -gt 1 ] && kill -0 "$RP" 2>/dev/null; then echo "started pid $(cat "$OUT/rec.pid") out $OUT minutes $MIN filter $FILTER mode ${MODE:-two} exclude_votes ${EXCLUDE_VOTES:-0} pump_pair ${PUMP_PAIR:-0}"; else echo "FAILED to start"; tail -5 "$OUT/stdout.log"; exit 1; fi
