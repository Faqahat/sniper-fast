#!/bin/bash
# Demand-gated paper: blacklist + co-buy >=2 SOL + exit ladder. Auto-recovers dead/hung engine. Stops at 60 done.
cd /root/sniper-fast
export PATH=/root/.cargo/bin:$PATH
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
LOG=/root/sniper-fast/paper_cobuy.log
launch() {
  setsid bash -c "timeout 7200 ./target/release/snipe_engine --paper-trade \
    --minutes 120 --entry-at-floor --max-r-cap 20 \
    --min-dev-buy 500000000 --max-dev-buy-sol 8 --uri-blacklist --demand-cobuy-sol 2.0 \
    --derisk-frac 0.30 --ride-mult 1.15 --trail-frac 0.95 --cut-r 0.0 --ladder-frac 0.25 --exit-cap-ms 40000 \
    --size-sol 1.0 --dump-paths /root/sniper-fast/paths_cobuy.jsonl --max-inflight 48 \
    --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
    < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1" >/dev/null 2>&1 </dev/null &
}
while true; do
  d=$(grep -c "PAPER done" "$LOG" 2>/dev/null)
  if [ "${d:-0}" -ge 60 ]; then
    for p in $(pgrep -f "release/snipe_engine --paper-trade"); do kill -9 "$p" 2>/dev/null; done
    echo "COLLECT_COBUY_DONE done=$d $(date -u)" >> "$LOG"; break
  fi
  running=$(pgrep -f "release/snipe_engine --paper-trade" | wc -l)
  age=$(( $(date +%s) - $(stat -c %Y "$LOG" 2>/dev/null || echo 0) ))
  if [ "$running" -eq 0 ]; then launch
  elif [ "$age" -gt 300 ]; then for p in $(pgrep -f "release/snipe_engine --paper-trade"); do kill -9 "$p" 2>/dev/null; done; sleep 2; launch; fi
  sleep 30
done
