#!/bin/bash
# ZERO-COST junk-fanout dry run (never --live) with a bpftrace write trace + fd map.  usage: dry.sh <tag> <minutes> <bin> [extra engine flags...]
TAG=$1; MIN=$2; BIN=$3; shift 3
cd /root/fast
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o 'KALDERA_TOKEN=[^ ]*' /root/collect_blfwd.sh | head -1 | cut -d= -f2)
ROUTES="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+helius+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"
timeout $(( MIN * 60 + 120 )) $BIN --snipe-once --concurrent --junk-fanout \
  --uri-blacklist --min-dev-buy 500000000 --max-dev-buy-sol 8 \
  --dev-from-cap --race-gate --race-min-dev-sol 3 --race-min-bundle 2 --race-bundle-ms 3 --race-max-name-len 12 --race-pros /root/race/pros.json --race-early \
  --spend-lamports 1000000 --fill-cap 2.5 --max-sol 0.0015 --max-total-sol 10 --max-loss-sol 0.001 --max-inflight 8 --minutes $MIN \
  --cu-price-micro 30000000 --cu-limit 90000 --sell-cu-price-micro 1500000 \
  --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES" --send-log /root/fast/sends_$TAG.jsonl \
  --config /root/lat/lat_dry.toml --env-file /root/arbx/deploy/.env "$@" \
  < /root/.nexus-v2-trading-wallet.pass > /root/fast/dry_$TAG.log 2>&1 &
EPID=$!
echo $EPID > /root/fast/dry_$TAG.pid
sleep 1
ENG=$(pgrep -P $EPID -f snipe_engine | head -1); [ -z "$ENG" ] && ENG=$EPID
echo "engine pid $ENG" >> /root/fast/dry_$TAG.pid
BPFTRACE_PERF_RB_PAGES=2048 bpftrace /root/fast/wtrace.bt $ENG > /root/fast/wt_$TAG.txt 2>&1 &
echo "bpf pid $!" >> /root/fast/dry_$TAG.pid
bash /root/fast/fdmap.sh $ENG /root/fast/fd_$TAG.txt &
wait $EPID
sleep 1; pkill -P $$ 2>/dev/null
echo "DRY_DONE $(date -u)" >> /root/fast/dry_$TAG.log
