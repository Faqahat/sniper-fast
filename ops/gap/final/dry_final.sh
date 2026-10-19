#!/bin/bash
# ZERO-COST junk-fanout dry run of the FINAL engine (never --live): the exact live_final.sh flags with --live replaced by
# --junk-fanout, + a bpftrace write trace and fd map (decision -> first write).  usage: dry_final.sh <tag> <minutes>
TAG=$1; MIN=$2
D=/root/gap/final; cd $D
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o "KALDERA_TOKEN=[^ ]*" /root/collect_blfwd.sh | head -1 | cut -d= -f2)
ROUTES="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+helius+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"
timeout $(( MIN * 60 + 120 )) /root/arbx-final/target/release/snipe_engine --snipe-once --concurrent --junk-fanout \
  --uri-blacklist --min-dev-buy 500000000 --max-dev-buy-sol 8 \
  --dev-from-cap --race-gate --race-min-bundle 1 --race-min-bundle-sol 3 --race-max-bundle-sol 5 --race-create-tip-prefix moon --race-bundle-ms 3 --race-glued \
  --race-pros /root/race/pros.json --race-early \
  --spend-lamports 1000000 --fill-cap 2.5 --max-sol 0.0015 --max-total-sol 0.010 --max-loss-sol 0.075 --max-inflight 2 --minutes $MIN \
  --cu-price-micro 30000000 --cu-limit 90000 --sell-cu-price-micro 1500000 --land-poll-ms 100 \
  --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES" --send-log $D/sends_$TAG.jsonl \
  --config /root/lat/final_landing.toml --env-file /root/arbx/deploy/.env \
  --fast-send --jito-h2 --fast-presign --fast-derive --busy-poll --pin-core 1 --lat-trace $D/trace_$TAG.jsonl \
  < /root/.nexus-v2-trading-wallet.pass > $D/dry_$TAG.log 2>&1 &
EPID=$!
echo $EPID > $D/dry_$TAG.pid
sleep 1
ENG=$(pgrep -P $EPID -f snipe_engine | head -1); [ -z "$ENG" ] && ENG=$EPID
echo "engine pid $ENG" >> $D/dry_$TAG.pid
BPFTRACE_PERF_RB_PAGES=2048 bpftrace $D/wtrace.bt $ENG > $D/wt_$TAG.txt 2>&1 &
BPF=$!
bash $D/fdmap.sh $ENG $D/fd_$TAG.txt &
FDM=$!
BPFTRACE_PERF_RB_PAGES=2048 bpftrace $D/nettrace.bt $ENG > $D/net_$TAG.txt 2>/dev/null &
NET=$!
bash $D/fdmap2.sh $ENG $D/fd2_$TAG.txt &
FDM2=$!
wait $EPID
sleep 1; kill $BPF $FDM $NET $FDM2 2>/dev/null
echo "DRY_DONE $(date -u)" >> $D/dry_$TAG.log
