#!/bin/bash
# PAPER "like the wallet": --uri-blacklist (keep all hosts except bot-launchpads), dev 0.5-8, floor entry, exit ladder.
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-fast
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/arbx-fast/paper_blacklist.log
timeout 7200 ./target/release/snipe_engine --paper-trade \
  --minutes 120 --entry-at-floor --max-r-cap 20 \
  --min-dev-buy 500000000 --max-dev-buy-sol 8 --uri-blacklist \
  --derisk-frac 0.30 --ride-mult 1.15 --trail-frac 0.95 --cut-r 0.0 --ladder-frac 0.25 --exit-cap-ms 40000 \
  --size-sol 1.0 --dump-paths /root/arbx-fast/paths_blacklist.jsonl --max-inflight 48 \
  --config probe_shadow.toml --env-file /root/arbx/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass >> /root/arbx-fast/paper_blacklist.log 2>&1
echo "PAPER_BLACKLIST_DONE" >> /root/arbx-fast/paper_blacklist.log
