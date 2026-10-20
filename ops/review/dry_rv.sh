#!/bin/bash
# REVIEW: ZERO-COST junk-fanout dry run: live_final.sh flags verbatim, --live -> --junk-fanout; own bpftrace + fd map
TAG=$1; MIN=$2
D=/root/review; cd $D
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o "KALDERA_TOKEN=[^ ]*" /root/collect_blfwd.sh | head -1 | cut -d= -f2)
ROUTES="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+helius+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"
timeout $(( MIN * 60 + 120 )) /root/sniper-final/target/release/snipe_engine --snipe-once --concurrent --junk-fanout \
  --uri-blacklist --min-dev-buy 500000000 --max-dev-buy-sol 8 \
  --dev-from-cap --race-gate --race-min-bundle 1 --race-min-bundle-sol 3 --race-max-bundle-sol 5 --race-create-tip-prefix moon --race-bundle-ms 3 --race-glued \
  --race-pros /root/race/pros.json --race-early \
  --spend-lamports 1000000 --fill-cap 2.5 --max-sol 0.0015 --max-total-sol 0.010 --max-loss-sol 0.075 --max-inflight 2 --minutes $MIN \
  --cu-price-micro 30000000 --cu-limit 90000 --sell-cu-price-micro 1500000 --land-poll-ms 100 \
  --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES" --send-log $D/sends_$TAG.jsonl \
  --config /root/lat/final_landing.toml --env-file /root/sniper/deploy/.env \
  --fast-send --jito-h2 --fast-presign --fast-derive --busy-poll --pin-core 1 --lat-trace $D/trace_$TAG.jsonl \
  < /root/.nexus-v2-trading-wallet.pass > $D/dry_$TAG.log 2>&1 &
EPID=$!
sleep 0.5
ENG=$(pgrep -P $EPID snipe_engine | head -1); [ -z "$ENG" ] && ENG=$EPID
echo "timeout $EPID engine $ENG" > $D/dry_$TAG.pid
BPFTRACE_PERF_RB_PAGES=4096 bpftrace $D/rv.bt $ENG > $D/bt_$TAG.txt 2>&1 &
BPF=$!
( while kill -0 $ENG 2>/dev/null; do echo "T $(date +%s%N)"; ss -tunapH 2>/dev/null | grep "pid=$ENG," ; sleep 0.5; done ) > $D/ss_$TAG.txt &
SSL=$!
wait $EPID
sleep 1; kill $BPF $SSL 2>/dev/null
echo "DRY_DONE $(date -u)" >> $D/dry_$TAG.log
