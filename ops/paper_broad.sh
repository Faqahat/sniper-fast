#!/bin/bash
# BROAD overnight collector: tracks EVERY pump create (no dev/vanilla filter) + dumps all paths, on BOTH feeds.
# Lets us iterate ANY filter OFFLINE against 4yFAz's actual buys to converge on a positive + his-matching selection.
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/sniper-fast/paper_broad.log
timeout 36000 ./target/release/snipe_engine --paper-trade \
  --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  --minutes 600 --max-r-cap 20 \
  --min-dev-buy 0 --max-dev-buy-sol 999 --allow-nonvanilla \
  --derisk-frac 0.30 --ride-mult 1.15 --trail-frac 0.95 --cut-r 0.0 --ladder-frac 0.25 \
  --demand-window-ms 2000 --demand-min-r 1.05 --exit-cap-ms 40000 \
  --size-sol 1.0 --dump-paths /root/sniper-fast/paths_broad.jsonl --max-inflight 64 \
  < /root/.nexus-v2-trading-wallet.pass >> /root/sniper-fast/paper_broad.log 2>&1
echo "PAPER_BROAD_DONE" >> /root/sniper-fast/paper_broad.log
