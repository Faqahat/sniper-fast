#!/bin/bash
# ===== LIVE — REAL SOL. Run ONLY on the owner's explicit go. =====  usage: bash /root/run1/run1.sh run1
TAG=${1:-run1}; cd /root/run1; . /root/run1/run1_common.sh
LOG=/root/run1/live_${TAG}.log; : > $LOG
$B --snipe-once --concurrent --live "${FLAGS[@]}" --send-log /root/run1/sends_${TAG}.jsonl --lat-trace /root/run1/trace_${TAG}.jsonl \
  < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1
echo "RUN1_DONE $TAG $(date -u)" >> $LOG
