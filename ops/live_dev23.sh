#!/bin/bash
# LIVE test: URI-host trusted + dev 2-3 SOL + paper exit ladder (same selection as paper_urihost trades). $3 cap.
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-fast
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/arbx-fast/live_dev23.log
./target/release/snipe_engine --snipe-once --concurrent --live --exit-ladder \
  --uri-whitelist \
  --close-leaders /root/arbx-fast/close_leaders.txt \
  --spend-lamports 2500000 \
  --max-sol 0.003 --max-total-sol 0.040 --max-loss-sol 0.017 --max-inflight 20 \
  --min-dev-buy 2000000000 --max-dev-buy-sol 3 --minutes 60 \
  --derisk-frac 0.30 --ride-mult 1.15 --trail-frac 0.95 --cut-r 0.0 --ladder-frac 0.25 --exit-cap-ms 40000 \
  --send-path staked-rpc --cu-price-micro 5000000 \
  --config probe_shadow.toml --env-file /root/arbx/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass >> /root/arbx-fast/live_dev23.log 2>&1
echo "LIVE_DEV23_DONE" >> /root/arbx-fast/live_dev23.log
