#!/bin/bash
# LIVE round-trips, blacklist filter, NEW cu_price 1.5M (was 5M). Measures fill improvement. ~20 trades, $3 loss cap.
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-fast
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/arbx-fast/live_bl_rt.log
./target/release/snipe_engine --snipe-once --concurrent --live \
  --uri-blacklist \
  --close-leaders /root/arbx-fast/close_leaders.txt \
  --spend-lamports 2500000 --fill-cap 2.0 \
  --max-sol 0.003 --max-total-sol 0.070 --max-loss-sol 0.030 --max-inflight 20 \
  --min-dev-buy 500000000 --max-dev-buy-sol 8 --minutes 30 \
  --cu-price-micro 1500000 --cu-limit 250000 \
  --send-path staked-rpc \
  --config probe_shadow.toml --env-file /root/arbx/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass >> /root/arbx-fast/live_bl_rt.log 2>&1
echo "LIVE_BL_RT_DONE" >> /root/arbx-fast/live_bl_rt.log
