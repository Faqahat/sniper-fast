#!/bin/bash
# Keep URI-host paper run going (append) until 100 PAPER done. Auto-recovers from DEAD or HUNG engine (stale log > 240s).
cd /root/arbx-fast
export PATH=/root/.cargo/bin:$PATH
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
LOG=/root/arbx-fast/paper_urihost.log
launch_engine() {
  setsid bash -c "timeout 7200 ./target/release/snipe_engine --paper-trade \
    --minutes 120 --entry-at-floor --max-r-cap 20 \
    --min-dev-buy 500000000 --max-dev-buy-sol 8 --uri-whitelist \
    --derisk-frac 0.30 --ride-mult 1.15 --trail-frac 0.95 --cut-r 0.0 --ladder-frac 0.25 --exit-cap-ms 40000 \
    --size-sol 1.0 --dump-paths /root/arbx-fast/paths_urihost.jsonl --max-inflight 48 \
    --config probe_shadow.toml --env-file /root/arbx/deploy/.env \
    < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1" >/dev/null 2>&1 </dev/null &
}
while true; do
  d=$(grep -c "PAPER done" "$LOG" 2>/dev/null)
  if [ "${d:-0}" -ge 100 ]; then
    for p in $(pgrep -f "release/snipe_engine --paper-trade"); do kill -9 "$p" 2>/dev/null; done
    echo "COLLECT_100_DONE done=$d $(date -u)" >> "$LOG"
    break
  fi
  running=$(pgrep -f "release/snipe_engine --paper-trade" | wc -l)
  age=$(( $(date +%s) - $(stat -c %Y "$LOG" 2>/dev/null || echo 0) ))
  if [ "$running" -eq 0 ]; then
    launch_engine
  elif [ "$age" -gt 240 ]; then
    # hung: kill stale engine, next loop relaunches
    for p in $(pgrep -f "release/snipe_engine --paper-trade"); do kill -9 "$p" 2>/dev/null; done
    sleep 2
    launch_engine
  fi
  sleep 30
done
