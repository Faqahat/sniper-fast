#!/bin/bash
# PAPER TRADE with the FULL FILTER STACK: basic bundle (dev 0.5-8 SOL, vanilla) + 4yFAz's reverse-engineered
# SELECTION gate (creator freshness: creator had <= N prior on-chain sigs = fresh deployer, not a serial launcher).
# His measured exit ladder. entry-at-floor (models same-slot floor landing = the proven-positive condition).
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/sniper-fast/paper_sel.log
rm -f /root/sniper-fast/paths_sel.jsonl
timeout 36000 ./target/release/snipe_engine --paper-trade \
  --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  --minutes 600 --entry-at-floor --max-r-cap 20 \
  --min-dev-buy 500000000 --max-dev-buy-sol 8 --max-creator-sigs 30 \
  --derisk-frac 0.30 --ride-mult 1.15 --trail-frac 0.95 --cut-r 0.0 --ladder-frac 0.25 \
  --demand-window-ms 2000 --demand-min-r 1.05 --exit-cap-ms 40000 \
  --size-sol 1.0 --dump-paths /root/sniper-fast/paths_sel.jsonl --max-inflight 48 \
  < /root/.nexus-v2-trading-wallet.pass >> /root/sniper-fast/paper_sel.log 2>&1
echo "PAPER_SEL_DONE" >> /root/sniper-fast/paper_sel.log
