#!/bin/bash
# ===== LIVE — THE OWNER RUNS THIS, NOBODY ELSE. Real transactions, real SOL. =====
# ONE multi-path landing test (/root/lat/NOTES.md): up to 10 buys of 0.001 SOL (~$0.10) on Gate B launches only, each
# buy routed by its create-slot leader's client to 2-4 paths at once (ONE signature: it can land once), sold at once
# via staked-rpc. Caps: per-buy 0.0015 SOL, cumulative buy spend 0.010 SOL (= 10 buys, then it stops firing), balance
# kill-switch 0.075 SOL, 90 min, 2 in flight. Wallet held 0.1108 SOL at 2026-10-19 09:40 UTC.
# Before: stop any paper/dry engine and build on the box (CPU); nothing else may use the Helius keyless budget.
# usage: live_lat.sh <tag>      then: python3 /root/lat/lat_measure.py /root/lat/live_land_<tag>.log /root/lat/sends_<tag>.jsonl
TAG=${1:-lat1}
cd /root/lat
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o 'KALDERA_TOKEN=[^ ]*' /root/collect_blfwd.sh | head -1 | cut -d= -f2)
ROUTES="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+helius+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"
LOG=/root/lat/live_land_${TAG}.log
: > $LOG
/root/sniper-lat/target/release/snipe_engine --snipe-once --concurrent --live \
  --uri-blacklist --min-dev-buy 500000000 --max-dev-buy-sol 8 \
  --dev-from-cap --race-gate --race-min-dev-sol 3 --race-min-bundle 2 --race-bundle-ms 3 --race-max-name-len 12 \
  --race-pros /root/race/pros.json --race-early \
  --spend-lamports 1000000 --fill-cap 2.5 --max-sol 0.0015 --max-total-sol 0.010 --max-loss-sol 0.075 --max-inflight 2 --minutes 90 \
  --cu-price-micro 30000000 --cu-limit 90000 --sell-cu-price-micro 1500000 --land-poll-ms 100 \
  --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES" --send-log /root/lat/sends_${TAG}.jsonl \
  --config /root/lat/lat_landing.toml --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1
echo "LIVE_LAT_DONE $TAG $(date -u)" >> $LOG
