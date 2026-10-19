#!/bin/bash
# Keep the URI-host paper run going (append mode) until 100 PAPER done, then stop. Preserves existing log.
cd /root/arbx-fast
export PATH=/root/.cargo/bin:$PATH
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
while true; do
  d=$(grep -c "PAPER done" paper_urihost.log 2>/dev/null)
  if [ "${d:-0}" -ge 60 ]; then
    pkill -f "snipe_engine --paper-trade"
    echo "COLLECT_60_DONE done=$d $(date -u)" >> paper_urihost.log
    break
  fi
  if ! pgrep -f "snipe_engine --paper-trade" >/dev/null 2>&1; then
    setsid bash -c "timeout 7200 ./target/release/snipe_engine --paper-trade \
      --minutes 120 --entry-at-floor --max-r-cap 20 \
      --min-dev-buy 500000000 --max-dev-buy-sol 8 --uri-whitelist \
      --derisk-frac 0.30 --ride-mult 1.15 --trail-frac 0.95 --cut-r 0.0 --ladder-frac 0.25 --exit-cap-ms 40000 \
      --size-sol 1.0 --dump-paths /root/arbx-fast/paths_urihost.jsonl --max-inflight 48 \
      --config probe_shadow.toml --env-file /root/arbx/deploy/.env \
      < /root/.nexus-v2-trading-wallet.pass >> /root/arbx-fast/paper_urihost.log 2>&1" >/dev/null 2>&1 </dev/null &
  fi
  sleep 30
done
