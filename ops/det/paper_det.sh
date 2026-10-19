#!/bin/bash
# PAPER ONLY (det audit, 2026-10-18): --paper-trade never sends. NEVER add --live here.
# usage: paper_det.sh <tag> <binary> <minutes> [extra engine flags ...]
# Same flags as /root/collect_blfwd.sh. Stall-aware (log AND paths file idle > STALL s -> restart), like paper_race.sh.
# Only ever touches processes whose command line holds "--dump-paths /root/det/paths_<tag>.jsonl".
TAG=$1; BIN=$2; MIN=$3; shift 3; EXTRA="$*"
STALL=${STALL:-600}
cd /root/arbx-det
export PATH=/root/.cargo/bin:$PATH
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o 'KALDERA_TOKEN=[^ ]*' /root/collect_blfwd.sh | head -1 | cut -d= -f2)
LOG=/root/det/paper_$TAG.log
PATHS=/root/det/paths_$TAG.jsonl
END=$(( $(date +%s) + MIN * 60 ))
launch() {
  left=$(( (END - $(date +%s)) / 60 )); [ "$left" -lt 1 ] && return
  setsid bash -c "timeout $(( left * 60 + 120 )) $BIN --paper-trade \
    --minutes $left --entry-at-floor --max-r-cap 20 \
    --min-dev-buy 500000000 --max-dev-buy-sol 8 --uri-blacklist \
    --derisk-frac 0.30 --ride-mult 1.15 --trail-frac 0.95 --cut-r 0.0 --ladder-frac 0.25 --exit-cap-ms 40000 \
    --size-sol 1.0 --dump-paths $PATHS --max-inflight 48 \
    --config /root/arbx-det/probe_shadow.toml --env-file /root/arbx/deploy/.env $EXTRA \
    < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1" >/dev/null 2>&1 </dev/null &
}
mypids() { ps -eo pid,args | grep -- "--dump-paths $PATHS" | grep -v "bash -c\|timeout\|grep" | awk '{print $1}'; }
echo "PAPER_DET start tag=$TAG bin=$BIN minutes=$MIN flags=$EXTRA $(date -u +%FT%TZ) epoch=$(date +%s)" >> $LOG
while true; do
  now=$(date +%s)
  if [ "$now" -ge $(( END + 90 )) ]; then echo "PAPER_DET_DONE $(date -u +%FT%TZ) epoch=$now" >> $LOG; break; fi
  pids=$(mypids)
  a1=$(( now - $(stat -c %Y "$LOG" 2>/dev/null || echo 0) ))
  a2=$(( now - $(stat -c %Y "$PATHS" 2>/dev/null || echo 0) ))
  age=$(( a1 < a2 ? a1 : a2 ))
  if [ -z "$pids" ] && [ "$now" -lt "$END" ]; then echo "PAPER_DET (re)launch $(date -u +%FT%TZ) epoch=$now" >> $LOG; launch
  elif [ -n "$pids" ] && [ "$age" -gt "$STALL" ]; then echo "PAPER_DET stall ${age}s -> restart $(date -u +%FT%TZ) epoch=$now" >> $LOG; for p in $pids; do kill -9 "$p"; done; sleep 2; launch; fi
  sleep 20
done
