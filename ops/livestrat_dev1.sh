#!/bin/bash
# LIVE 4yFAz STRATEGY (exit-ladder HOLD, not round-trip): dev>=1 vanilla, close-gated, his measured ladder.
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-fast
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/arbx-fast/livestrat_dev1.log
./target/release/snipe_engine --snipe-once --concurrent --live --exit-ladder \
  --close-leaders /root/arbx-fast/close_leaders.txt \
  --spend-lamports 2500000 --fill-cap 2.0 \
  --max-sol 0.003 --max-total-sol 0.051 --max-loss-sol 0.04 --max-inflight 20 \
  --min-dev-buy 1000000000 --max-dev-buy-sol 8 --minutes 20 \
  --derisk-frac 0.30 --ride-mult 1.40 --trail-frac 0.92 --cut-r 0.80 --ladder-frac 0.25 --exit-cap-ms 9000 \
  --send-path staked-rpc --cu-price-micro 5000000 \
  --config probe_shadow.toml --env-file /root/arbx/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass >> /root/arbx-fast/livestrat_dev1.log 2>&1
echo "LIVESTRAT_DEV1_DONE" >> /root/arbx-fast/livestrat_dev1.log
