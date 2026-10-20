#!/bin/bash
# ZERO-COST paper run (--paper-trade never sends): the exact rule-#2 filters of live_final2.sh + the FIX2 gates (applied
# at the decision, GATE line per decided launch) + CREATE-POH lines for the PoH validation.  usage: paper_fix2.sh <tag> <minutes>
TAG=${1:-pfx}; MIN=${2:-30}
D=/root/fix2/run; mkdir -p $D; cd $D
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o "KALDERA_TOKEN=[^ ]*" /root/collect_blfwd.sh | head -1 | cut -d= -f2)
timeout $(( MIN * 60 + 120 )) taskset -c 0,2,3 ${BIN:-/root/sniper-final2/target/release/snipe_engine} --paper-trade --minutes $MIN --entry-at-floor --max-r-cap 20 \
  --min-dev-buy 500000000 --max-dev-buy-sol 8 --uri-blacklist \
  --derisk-frac 0 --ladder-frac 0 --ride-mult 99 --cut-r 0 --exit-cap-ms 1000 \
  --size-sol 2.0 --dump-paths $D/paths_$TAG.jsonl --max-inflight 48 \
  --config /root/fix2/final2_landing.toml --env-file /root/sniper/deploy/.env \
  --dev-from-cap --race-gate --race-min-bundle 1 --race-min-bundle-sol 3 --race-max-bundle-sol 5 --race-create-tip-prefix moon --race-bundle-ms 3 --race-glued \
  --race-pros /root/race/pros.json --race-early \
  --close-leaders /root/fix2/close_leaders_5ms.txt --max-create-ms 150 --log-create-poh \
  < /root/.nexus-v2-trading-wallet.pass > $D/paper_$TAG.log 2>&1
echo "PAPER_DONE $(date -u)" >> $D/paper_$TAG.log
