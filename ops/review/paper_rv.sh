#!/bin/bash
# REVIEW: independent 30-min PAPER run (never sends), exact live_final.sh filter flags (+ --race-track-rejects for reject logging)
TAG=${1:-rv1}; MIN=${2:-30}
D=/root/review; cd $D
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o "KALDERA_TOKEN=[^ ]*" /root/collect_blfwd.sh | head -1 | cut -d= -f2)
timeout $(( MIN * 60 + 90 )) /root/sniper-final/target/release/snipe_engine --paper-trade --minutes $MIN --entry-at-floor --max-r-cap 20 \
  --uri-blacklist --min-dev-buy 500000000 --max-dev-buy-sol 8 \
  --dev-from-cap --race-gate --race-min-bundle 1 --race-min-bundle-sol 3 --race-max-bundle-sol 5 --race-create-tip-prefix moon --race-bundle-ms 3 --race-glued \
  --race-pros /root/race/pros.json --race-early --race-track-rejects \
  --derisk-frac 0 --ladder-frac 0 --ride-mult 99 --cut-r 0 --exit-cap-ms 1000 \
  --size-sol 2.0 --dump-paths $D/paths_$TAG.jsonl --max-inflight 48 \
  --config /root/lat/final_landing.toml --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass > $D/paper_$TAG.log 2>&1
echo "PAPER_DONE $(date -u)" >> $D/paper_$TAG.log
