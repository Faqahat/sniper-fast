#!/bin/bash
# ZERO-COST junk-fanout dry run of the FIX2 engine (never --live): live_final2.sh's exact flags with --live replaced by
# --junk-fanout, + bpftrace write/connect trace and fd maps (detection -> first write proof).  usage: dry_fix2.sh <tag> <minutes>
TAG=$1; MIN=$2
D=/root/fix2/run; mkdir -p $D; cd $D
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o "KALDERA_TOKEN=[^ ]*" /root/collect_blfwd.sh | head -1 | cut -d= -f2)
# old landed bundles of the final1 live test: in junk mode our bundles are refused (no id), so the poller polls these
export JITO_POLL_PROBE_IDS="ab0c66e50e98d4276b70161231b8c901b371c1b0270e9eb09bd28ce9b57b3804,6bf4ad0ac0855024151fcaebc428e251509a840be45b6f366fb58a519d8fb350,62e916786295527bd12341712c51a58208fc21b3e05b274ef2d74db2f82e2904"
ROUTES="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=harmonic-bundle+jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"
timeout $(( MIN * 60 + 150 )) /root/arbx-final2/target/release/snipe_engine --snipe-once --concurrent --junk-fanout \
  --uri-blacklist --min-dev-buy 500000000 --max-dev-buy-sol 8 \
  --dev-from-cap --race-gate --race-min-bundle 1 --race-min-bundle-sol 3 --race-max-bundle-sol 5 --race-create-tip-prefix moon --race-bundle-ms 3 --race-glued \
  --race-pros /root/race/pros.json --race-early \
  --close-leaders /root/fix2/close_leaders_5ms.txt --max-create-ms 150 \
  --spend-lamports 1000000 --fill-cap 2.5 --max-sol 0.0015 --max-total-sol 0.017 --max-loss-sol 0.170 --max-inflight 2 --minutes $MIN \
  --cu-price-micro 30000000 --cu-limit 105000 --sell-cu-price-micro 1500000 --land-poll-ms 100 \
  --sell-robust --sell-retries 2 --sell-retry-s 4 --strict-balance --jito-poll --landed-via \
  --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES" --send-log $D/sends_$TAG.jsonl \
  --config /root/fix2/final2_landing.toml --env-file /root/arbx/deploy/.env \
  --fast-send --jito-h2 --fast-presign --fast-derive --busy-poll --pin-core 1 --lat-trace $D/trace_$TAG.jsonl \
  < /root/.nexus-v2-trading-wallet.pass > $D/dry_$TAG.log 2>&1 &
EPID=$!
echo $EPID > $D/dry_$TAG.pid
sleep 1
ENG=$(pgrep -P $EPID -f snipe_engine | head -1); [ -z "$ENG" ] && ENG=$EPID
echo "engine pid $ENG" >> $D/dry_$TAG.pid
BPFTRACE_PERF_RB_PAGES=2048 bpftrace /root/gap/final/nettrace.bt $ENG > $D/net_$TAG.txt 2>/dev/null &
NET=$!
echo "bpftrace pid $NET" >> $D/dry_$TAG.pid
bash /root/gap/final/fdmap2.sh $ENG $D/fd2_$TAG.txt &
FDM2=$!
wait $EPID
sleep 1; kill $NET $FDM2 2>/dev/null
echo "DRY_DONE $(date -u)" >> $D/dry_$TAG.log
