#!/bin/bash
# LANDING TEST (owner OK 2026-10-18): $0.10 round-trips, blacklist filter, HIGH per-CU priority on the BUY only
# (100M micro-lamports x 90k CU = 0.009 SOL), sells at the low 1.5M fee. Usage: live_land.sh <send-path> <tag>
# Caps: 6 buys of 0.001 SOL (total spend cap 0.006), loss kill-switch 0.07 SOL, 40 min.
PATHNAME=${1:-helius}
TAG=${2:-helius}
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
LOG=/root/sniper-fast/live_land_${TAG}.log
: > $LOG
./target/release/snipe_engine --snipe-once --concurrent --live \
  --uri-blacklist \
  --close-leaders /root/sniper-fast/close_leaders.txt \
  --spend-lamports 1000000 --fill-cap 2.5 \
  --max-sol 0.0015 --max-total-sol 0.006 --max-loss-sol 0.070 --max-inflight 2 \
  --min-dev-buy 500000000 --max-dev-buy-sol 8 --minutes 40 \
  --cu-price-micro 100000000 --cu-limit 90000 --sell-cu-price-micro 1500000 \
  --send-path $PATHNAME --sell-path staked-rpc \
  --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1
echo "LIVE_LAND_DONE $TAG" >> $LOG
