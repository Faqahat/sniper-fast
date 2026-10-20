#!/bin/bash
# ZERO-COST: watch the feed, simulate the real v3 buy on the first launch, print unitsConsumed.
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/sniper-fast/measure_cu.log
timeout 150 ./target/release/snipe_engine --simulate \
  --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  --spend-lamports 9500000 \
  < /root/.nexus-v2-trading-wallet.pass >> /root/sniper-fast/measure_cu.log 2>&1
echo "MEASURE_DONE" >> /root/sniper-fast/measure_cu.log
