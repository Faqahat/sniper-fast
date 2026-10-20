#!/bin/bash
# ZERO-COST DRY RUN of the live pipeline: real feeds -> detection -> Gate B -> per-leader-client routing -> the real buy
# built + signed and DISCARDED -> only JUNK (undecodable 4 bytes) to each routed path. Nothing can land, nothing is paid.
# NEVER add --live (the engine refuses --junk-fanout with --live).  usage: dry_fanout.sh <tag> <minutes> [config]
TAG=${1:-dry}; MIN=${2:-30}; CFG=${3:-/root/lat/lat_dry.toml}
cd /root/lat
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o 'KALDERA_TOKEN=[^ ]*' /root/collect_blfwd.sh | head -1 | cut -d= -f2)
ROUTES="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+helius+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"
timeout $(( MIN * 60 + 120 )) /root/sniper-lat/target/release/snipe_engine --snipe-once --concurrent --junk-fanout \
  --uri-blacklist --min-dev-buy 500000000 --max-dev-buy-sol 8 \
  --dev-from-cap --race-gate --race-min-dev-sol 3 --race-min-bundle 2 --race-bundle-ms 3 --race-max-name-len 12 --race-pros /root/race/pros.json --race-early \
  --spend-lamports 1000000 --fill-cap 2.5 --max-sol 0.0015 --max-total-sol 10 --max-loss-sol 0.001 --max-inflight 8 --minutes $MIN \
  --cu-price-micro 30000000 --cu-limit 90000 --sell-cu-price-micro 1500000 \
  --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES" --send-log /root/lat/sends_$TAG.jsonl \
  --config $CFG --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass > /root/lat/dry_$TAG.log 2>&1
echo "DRY_DONE $(date -u)" >> /root/lat/dry_$TAG.log
