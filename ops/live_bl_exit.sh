#!/bin/bash
# LIVE exit-ladder (HOLD), blacklist filter, staked-rpc, $1/trade, $5 hard loss cap. The real strategy test.
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/sniper-fast/live_bl_exit.log
./target/release/snipe_engine --snipe-once --concurrent --live --exit-ladder \
  --uri-blacklist \
  --close-leaders /root/sniper-fast/close_leaders.txt \
  --spend-lamports 9626000 \
  --max-sol 0.011 --max-total-sol 0.120 --max-loss-sol 0.048 --max-inflight 10 \
  --min-dev-buy 500000000 --max-dev-buy-sol 8 --minutes 30 \
  --derisk-frac 0.30 --ride-mult 1.15 --trail-frac 0.95 --cut-r 0.0 --ladder-frac 0.25 --exit-cap-ms 40000 \
  --cu-price-micro 2000000 \
  --send-path staked-rpc \
  --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass >> /root/sniper-fast/live_bl_exit.log 2>&1
echo "LIVE_BL_EXIT_DONE" >> /root/sniper-fast/live_bl_exit.log
