#!/bin/bash
# ZERO COST dry run of the exact Run-1 command: real detection, gates, routing, the real Run-1 buy built + signed and
# DISCARDED; only junk bytes go to the paths (--junk-fanout), nothing can land.  usage: bash /root/run1/dry_run1.sh [minutes]
MIN=${1:-60}; cd /root/run1; . /root/run1/run1_common.sh
LOG=/root/run1/dry_run1.log; : > $LOG
FL=("${FLAGS[@]}"); for i in "${!FL[@]}"; do [ "${FL[$i]}" = "--minutes" ] && FL[$((i+1))]=$MIN; done
$B --snipe-once --concurrent --junk-fanout "${FL[@]}" --send-log /root/run1/sends_dry.jsonl --lat-trace /root/run1/trace_dry.jsonl \
  < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1
echo "DRY_RUN1_DONE $(date -u)" >> $LOG
