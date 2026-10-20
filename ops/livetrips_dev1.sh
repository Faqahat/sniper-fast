#!/bin/bash
# LIVE round-trips only (buy+immediate sell, NO hold), dev>=1 vanilla, close-gated, $3 loss cap. Measures fill multiple.
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/sniper-fast/livetrips_dev1.log
./target/release/snipe_engine --snipe-once --concurrent --live \
  --close-leaders /root/sniper-fast/close_leaders.txt \
  --spend-lamports 2500000 --fill-cap 2.0 \
  --max-sol 0.003 --max-total-sol 0.040 --max-loss-sol 0.017 --max-inflight 20 \
  --min-dev-buy 1000000000 --max-dev-buy-sol 8 --minutes 20 \
  --send-path staked-rpc --cu-price-micro 5000000 \
  --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass >> /root/sniper-fast/livetrips_dev1.log 2>&1
echo "LIVETRIPS_DEV1_DONE" >> /root/sniper-fast/livetrips_dev1.log
