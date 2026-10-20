#!/bin/bash
# ===== LIVE — REAL SOL. Run ONLY on the owner's explicit go. =====  usage: bash /root/run1/run1.sh run1   (detaches itself)
# H1: the guard (guard_run1.py) watches this run's log, verifies every FIRE on chain against rule #2, and on a mismatch
# stops THIS engine (its PID, checked against /root/sniper-run1/target/release/snipe_engine) with SIGTERM: the engine
# stops new fires and drains its open positions (sells until 0, then HELD-AT-EXIT). Never SIGKILL a live engine.
# M-1 (audit 3): the run DETACHES itself from the terminal (setsid nohup, stdin /dev/null): a dropped SSH session cannot
# kill it (the engine also handles SIGHUP as stop + drain). Its own output goes to /root/run1/run1_<tag>.out.
TAG=${1:-run1}
if [ -z "$RUN1_DETACHED" ]; then
  RUN1_DETACHED=1 setsid nohup bash "$0" "$@" > /root/run1/run1_${TAG}.out 2>&1 < /dev/null &
  echo "run1.sh detached (setsid nohup): pid $! — output /root/run1/run1_${TAG}.out, engine log /root/run1/live_${TAG}.log"
  exit 0
fi
cd /root/run1; . /root/run1/run1_common.sh
LOG=/root/run1/live_${TAG}.log; : > $LOG
GLOG=/root/run1/guard_${TAG}.log
$B --snipe-once --concurrent --live "${FLAGS[@]}" --send-log /root/run1/sends_${TAG}.jsonl --lat-trace /root/run1/trace_${TAG}.jsonl \
  < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1 &
EPID=$!
python3 /root/run1/guard_run1.py $LOG $GLOG RUN1_DONE $EPID >> $GLOG 2>&1 &
GPID=$!
echo "engine pid $EPID, guard pid $GPID, log $LOG, guard log $GLOG"
# a signal to this script stops the engine the same way (SIGTERM -> drain)
trap 'kill -TERM $EPID 2>/dev/null' INT TERM
while kill -0 $EPID 2>/dev/null; do wait $EPID; done
echo "RUN1_DONE $TAG $(date -u)" >> $LOG
# the guard finishes the on-chain checks of the last fires (it exits by itself after RUN1_DONE; <= ~90 s), then stop it
for i in $(seq 1 30); do kill -0 $GPID 2>/dev/null || break; sleep 3; done
kill $GPID 2>/dev/null && echo "$(date -u +%H:%M:%S) GUARD stopped by run1.sh" >> $GLOG
