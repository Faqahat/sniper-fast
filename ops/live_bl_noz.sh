#!/bin/bash
# LIVE round-trips via NOZOMI (Frankfurt, 0.002 SOL tip, cu 1M), blacklist filter. Measures fill vs staked-rpc. ~$5 cap.
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/sniper-fast/live_bl_noz.log
./target/release/snipe_engine --snipe-once --concurrent --live \
  --uri-blacklist \
  --close-leaders /root/sniper-fast/close_leaders.txt \
  --spend-lamports 2500000 --fill-cap 2.0 \
  --max-sol 0.003 --max-total-sol 0.100 --max-loss-sol 0.050 --max-inflight 20 \
  --min-dev-buy 500000000 --max-dev-buy-sol 8 --minutes 30 \
  --cu-price-micro 1000000 \
  --send-path nozomi \
  --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass >> /root/sniper-fast/live_bl_noz.log 2>&1
echo "LIVE_BL_NOZ_DONE" >> /root/sniper-fast/live_bl_noz.log
