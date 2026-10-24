#!/bin/bash
# ===== LIVE — REAL SOL. Run ONLY on the owner's explicit go (FRZ / DEV wallet first). =====
# FINAL-2 "become them" (ops/final2/PLAN.md): FINAL-2 picks at the glued-bundle close (scorer over a local socket),
# buy 0.5 SOL only if first after the bundle (0.5% guard), sell ~8 s later (optional activity check A7).
# usage (server, root): bash /root/sniper-f2/live_f2.sh <tag>      (detaches itself; Stop: kill -TERM <engine pid>)
# Differences vs Run 2 (ops/run1/run1_common.sh), each deliberate:
#   - NO rule #2 filters (race min/max bundle, tip prefix), NO uri blacklist, NO dev-buy band, NO close-leaders / max-create-ms:
#     the replay did not use them; FINAL-2 has its own guards
#   - --final2-sock (selection) + --hold-ms 7700 (sell ~8 s after the buy) instead of --hold-slots 2
#   - FEES (owner's decision, paid settings): every FAILED guarded buy pays the priority fee (~60% of attempts fail at 75 ms).
#     Run 2 used --cu-price-micro 110000000 x --cu-limit 100000 = 0.011 SOL; the strategy needs ~0.003 (CU_PRICE below).
#     Tips stay as in the landing toml until the owner decides on the send design (ops/final2/SEND_DESIGN.md).
TAG=${1:-f2}
if [ -z "$F2_DETACHED" ]; then
  F2_DETACHED=1 setsid nohup bash "$0" "$@" > /root/sniper-f2/live_${TAG}.out 2>&1 < /dev/null &
  echo "live_f2.sh detached: pid $! — output /root/sniper-f2/live_${TAG}.out, engine log /root/sniper-f2/engine_${TAG}.log"
  exit 0
fi
set -a; . /root/sniper/deploy/.env; set +a
cd /root/sniper-f2
B=/root/sniper-f2/snipe_engine_final2
C=/root/run1/run1_landing.toml
ENV_NAME=${ENV_NAME:-DEV}
CU_PRICE=${CU_PRICE:-30000000}           # 0.003 SOL priority at 100k CU (owner decides; Run 2 was 110000000)
ACT=${ACT:-}                              # set ACT="--hold-activity-k 1 --hold-activity-cap-ms 800" to enable the A7 exit
CRUN=${CRUN:-/root/sniper-collect/run_20261022_1543}   # the RUNNING collection (scorer history)
# ROUTES: Run 2's multi-route design by default. Owner's option after the speed probe (ops/final2/probe_speed.sh): one route per
# leader client, e.g. ROUTES_OVERRIDE="bam=helius;jito=helius;harmonic=nozomi;fd=astralane;agave=helius;other=landx-fra3;default=helius"
ROUTES=${ROUTES_OVERRIDE:-$(grep '^ROUTES=' /root/run1/run1_common.sh | head -n 1 | sed 's/^ROUTES=//; s/^"//; s/"$//')}
LOG=/root/sniper-f2/engine_${TAG}.log; : > $LOG
export FINAL2_SOCK=/root/sniper-f2/f2.sock
python3 -I scorer.py "$LOG" frozen_live3_fsell.json,frozen_dump2.json,frozen_live2_fsell.json shadow_seed.json "$CRUN" /root/sniper-collect/tipmap.json out_${TAG} final_config2.json > scorer_${TAG}.log 2>&1 &
SPID=$!
echo "scorer pid $SPID — waiting 90 s for its history"; sleep 90
[ -S "$FINAL2_SOCK" ] || { echo "no scorer socket — abort"; kill $SPID; exit 1; }
FLAGS=(--min-dev-buy 0 --max-dev-buy-sol 100
  --dev-from-cap --race-gate --race-bundle-ms 3 --race-glued --race-pros /root/race/pros.json --create-ms-src wall
  --final2-sock "$FINAL2_SOCK" --final2-timeout-ms 5
  --spend-lamports 500000000 --slip-cap-bps 50 --fill-cap 1.005 --max-sol 0.6 --max-total-sol 8 --max-buys 15 --max-loss-sol 0.3 --ks-blind-s 10 --max-inflight 2 --minutes 120
  --cu-price-micro "$CU_PRICE" --cu-limit 100000 --sell-cu-limit 120000 --sell-cu-price-micro 5000000
  --hold-slots 0 --hold-ms 7700 --hold-max-ms 9000 --land-poll-ms 100 --land-timeout-ms 3000 $ACT
  --sell-robust --sell-retry-s 1 --sell-deadline-s 30 --sell-fallback-path nozomi --buy-max-slot-delta 1 --rpc-fallback-url-env RMR_RPC_URL
  --alt-cache-file /root/run1/alt_tables.txt --env-name $ENV_NAME --strict-balance
  --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES"
  --config $C --env-file /root/sniper/deploy/.env
  --fast-send --jito-h2 --fast-presign --fast-derive --fast-verify --busy-poll --pin-core 1)
$B --snipe-once --concurrent --live "${FLAGS[@]}" --send-log /root/sniper-f2/sends_${TAG}.jsonl --lat-trace /root/sniper-f2/trace_${TAG}.jsonl \
  < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1 &
EPID=$!
echo "engine pid $EPID, scorer pid $SPID, log $LOG"
trap 'kill -TERM $EPID 2>/dev/null' INT TERM
while kill -0 $EPID 2>/dev/null; do wait $EPID; done
echo "F2_DONE $TAG $(date -u)" >> $LOG
kill $SPID 2>/dev/null
echo "after the run: grep -E 'FINAL2|FIRE|HOLD-ACTIVITY|ROUND-TRIP' $LOG ; compare each fill with the replay (ops/overnight/core/verify_live.py style)"
