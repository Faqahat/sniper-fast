#!/bin/bash
# FORWARD PAPER test of the race gate (2026-10-18). PAPER ONLY: --paper-trade never sends. Never add --live here.
# usage: paper_race.sh <tag> <minutes> [extra engine flags ...]
# Stall-aware: if the log stops growing for 300 s the engine is restarted (same pattern as /root/collect_blfwd.sh).
TAG=$1; MIN=$2; shift 2; EXTRA="$*"
cd /root/sniper-race   # SEPARATE race build, never the live /root/sniper-fast binary
export PATH=/root/.cargo/bin:$PATH
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o 'KALDERA_TOKEN=[^ ]*' /root/collect_blfwd.sh | head -1 | cut -d= -f2)
LOG=/root/race/paper_$TAG.log
END=$(( $(date +%s) + MIN * 60 ))
launch() {
  left=$(( (END - $(date +%s)) / 60 )); [ "$left" -lt 1 ] && return
  setsid bash -c "timeout $(( left * 60 + 120 )) ./target/release/snipe_engine --paper-trade \
    --minutes $left --entry-at-floor --max-r-cap 20 \
    --min-dev-buy 500000000 --max-dev-buy-sol 8 --uri-blacklist \
    --derisk-frac 0.30 --ride-mult 1.15 --trail-frac 0.95 --cut-r 0.0 --ladder-frac 0.25 --exit-cap-ms 40000 \
    --size-sol 1.0 --dump-paths /root/race/paths_$TAG.jsonl --max-inflight 48 \
    --config probe_shadow.toml --env-file /root/sniper/deploy/.env $EXTRA \
    < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1" >/dev/null 2>&1 </dev/null &
}
echo "PAPER_RACE start tag=$TAG minutes=$MIN flags=$EXTRA $(date -u)" >> $LOG
while true; do
  now=$(date +%s)
  if [ "$now" -ge $(( END + 90 )) ]; then echo "PAPER_RACE_DONE $(date -u)" >> $LOG; break; fi
  pids=$(ps -eo pid,args | grep "[r]elease/snipe_engine --paper-trade" | grep -- "paths_$TAG.jsonl" | awk '{print $1}')
  age=$(( now - $(stat -c %Y "$LOG" 2>/dev/null || echo 0) ))
  if [ -z "$pids" ] && [ "$now" -lt "$END" ]; then echo "PAPER_RACE (re)launch $(date -u)" >> $LOG; launch
  elif [ -n "$pids" ] && [ "$age" -gt 300 ]; then echo "PAPER_RACE stall ${age}s -> restart $(date -u)" >> $LOG; for p in $pids; do kill -9 "$p"; done; sleep 2; launch; fi
  sleep 20
done
