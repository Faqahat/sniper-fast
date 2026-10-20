#!/bin/bash
# ZERO COST dry run of the exact Run-1 command: real detection, gates, routing, the real Run-1 buy built + signed (and
# M1 re-signed at the decision) and DISCARDED; only junk bytes go to the paths (--junk-fanout), nothing can land.
# The guard runs as in the live run (dry log names): a rule-#2 mismatch SIGTERMs this dry engine.
# usage: bash /root/run1/dry_run1.sh [minutes]
# detaches itself (setsid nohup), like run1.sh
MIN=${1:-60}
if [ -z "$RUN1_DETACHED" ]; then
  RUN1_DETACHED=1 setsid nohup bash "$0" "$@" > /root/run1/dry_run1.out 2>&1 < /dev/null &
  echo "dry_run1.sh detached (setsid nohup): pid $! — output /root/run1/dry_run1.out, engine log /root/run1/dry_run1.log"
  exit 0
fi
cd /root/run1; . /root/run1/run1_common.sh
LOG=/root/run1/dry_run1.log; : > $LOG
GLOG=/root/run1/guard_dry.log
FL=("${FLAGS[@]}"); for i in "${!FL[@]}"; do [ "${FL[$i]}" = "--minutes" ] && FL[$((i+1))]=$MIN; done
$B --snipe-once --concurrent --junk-fanout "${FL[@]}" --send-log /root/run1/sends_dry.jsonl --lat-trace /root/run1/trace_dry.jsonl \
  < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1 &
EPID=$!
python3 /root/run1/guard_run1.py $LOG $GLOG DRY_RUN1_DONE $EPID >> $GLOG 2>&1 &
GPID=$!
echo "dry engine pid $EPID, guard pid $GPID, log $LOG, guard log $GLOG"
trap 'kill -TERM $EPID 2>/dev/null' INT TERM
while kill -0 $EPID 2>/dev/null; do wait $EPID; done
echo "DRY_RUN1_DONE $(date -u)" >> $LOG
for i in $(seq 1 30); do kill -0 $GPID 2>/dev/null || break; sleep 3; done
kill $GPID 2>/dev/null && echo "$(date -u +%H:%M:%S) GUARD stopped by dry_run1.sh" >> $GLOG
