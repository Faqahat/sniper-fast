#!/bin/bash
# PAPER smoke of the arbx-feed engine with the constant-k UDP feed (--paper-trade never sends). usage: paper_feed.sh <tag> <minutes>
TAG=${1:-pf}; MIN=${2:-10}
cd /root/gap
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o "KALDERA_TOKEN=[^ ]*" /root/collect_blfwd.sh | head -1 | cut -d= -f2)
timeout $(( MIN * 60 + 90 )) /root/arbx-feed/target/release/snipe_engine --paper-trade --minutes $MIN --entry-at-floor --max-r-cap 20 \
  --min-dev-buy 500000000 --max-dev-buy-sol 8 --uri-blacklist \
  --derisk-frac 0 --ladder-frac 0 --ride-mult 99 --cut-r 0 --exit-cap-ms 1000 \
  --size-sol 2.0 --dump-paths /root/gap/paths_$TAG.jsonl --max-inflight 48 \
  --config /root/gap/probe_dz.toml --env-file /root/arbx/deploy/.env \
  --dev-from-cap --race-gate --race-min-dev-sol 3 --race-min-bundle 2 --race-bundle-ms 3 --race-max-name-len 12 \
  --race-pros /root/race/pros.json --race-track-rejects --race-early \
  < /root/.nexus-v2-trading-wallet.pass > /root/gap/paper_$TAG.log 2>&1
echo "PAPER_SMOKE_DONE $(date -u)" >> /root/gap/paper_$TAG.log
