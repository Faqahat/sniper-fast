#!/bin/bash
# PAPER test of URI-HOST filter (zero cost): dev>=0.5 vanilla + --uri-whitelist (trusted launch tools only), floor entry, exit ladder.
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/sniper-fast/paper_urihost.log
timeout 7200 ./target/release/snipe_engine --paper-trade \
  --minutes 120 --entry-at-floor --max-r-cap 20 \
  --min-dev-buy 500000000 --max-dev-buy-sol 8 --uri-whitelist \
  --derisk-frac 0.30 --ride-mult 1.15 --trail-frac 0.95 --cut-r 0.0 --ladder-frac 0.25 --exit-cap-ms 40000 \
  --size-sol 1.0 --dump-paths /root/sniper-fast/paths_urihost.jsonl --max-inflight 48 \
  --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass >> /root/sniper-fast/paper_urihost.log 2>&1
echo "PAPER_URIHOST_DONE" >> /root/sniper-fast/paper_urihost.log
