#!/bin/bash
# ===== LIVE on the DEV wallet (FRZ) — owner-authorized 2026-10-20: "run on the dev wallet frz to check we did not lose
# the edge after the refactor and engine changes, $5 cap" (overall loss accepted). =====
# Same rule/gates/exit as Run 1 (run1_common.sh); owner: buy size AS BEFORE (live test 2: 0.001 SOL), FEE CAP $5
# (kill switch = $5 of SOL at /root/solprice.json's price). Fee = live test 2's (cu price 30M uL x 100k CU = 0.003 SOL
# priority, Jito tip 0.002 + relay 0.001 ~ 0.0065 SOL/trade -> ~7 trades). Max 7 landed buys, no profit lock, 90 min.
# Detaches; guard + Telegram (DEV) on.
TAG=${1:-edge1}
. /root/run1/run1_common.sh
PX=$(python3 -c "import json; print(json.load(open('/root/solprice.json'))['sol_usd'])")
SPEND=1000000; MAXSOL=0.0015
LOSS=${LOSS_SOL:-$(python3 -c "print(round(5.0 / $PX, 4))")}   # LOSS_SOL overrides (SOL)
echo "SOL price $PX USD -> buy size 0.001 SOL, fee/loss cap 5 USD = $LOSS SOL"
LOG=/root/run1/live_${TAG}.log; : > $LOG
FL=("${FLAGS[@]}")
for i in "${!FL[@]}"; do
  case "${FL[$i]}" in
    --config) FL[$((i+1))]=/root/run1/edge_landing.toml;; --spend-lamports) FL[$((i+1))]=$SPEND;; --max-sol) FL[$((i+1))]=$MAXSOL;;
    --max-total-sol) FL[$((i+1))]=${MAXTOTAL:-0.06};; --max-buys) FL[$((i+1))]=${MAXBUYS:-7};; --max-loss-sol) FL[$((i+1))]=$LOSS;; --minutes) FL[$((i+1))]=${MINUTES:-90};;
    --cu-price-micro) FL[$((i+1))]=30000000;; --lock-tiers) FL[$((i+1))]=100:0;;
  esac
done
setsid nohup bash -c "
  $B --snipe-once --concurrent --live $(printf '%q ' "${FL[@]}") --send-log /root/run1/sends_${TAG}.jsonl --lat-trace /root/run1/trace_${TAG}.jsonl \
    < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1
  echo \"RUN1_DONE ${TAG} \$(date -u)\" >> $LOG" > /dev/null 2>&1 < /dev/null &
sleep 3
P=$(pgrep -n -x snipe_engine)
setsid nohup python3 /root/run1/guard_run1.py $LOG /root/run1/guard_${TAG}.log RUN1_DONE $P > /root/run1/guard_${TAG}.out 2>&1 < /dev/null &
echo "started engine pid $P, log $LOG"
