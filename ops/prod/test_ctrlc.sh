#!/bin/bash
# ZERO COST test of run_prod.sh's Ctrl-c handling (AUDIT6 H6-1): the SAME launch structure (engine -> log file directly,
# setsid tail viewer, INT trap) but in Dev junk-fanout mode (FRZ wallet + its pass file, nothing can land). Run it inside
# tmux, then press Ctrl-c (or: tmux send-keys -t ctest C-c). PASS = log has "SIGNAL SIGINT", "EXIT CHECK", "SNIPE-LIVE DONE",
# "CTEST_DONE" and no "panicked".
. /root/run1/run1_common.sh
LOG=/root/prod/runs/ctrlc_test.log; : > "$LOG"
FL=("${FLAGS[@]}"); for i in "${!FL[@]}"; do [ "${FL[$i]}" = "--minutes" ] && FL[$((i+1))]=10; done
setsid tail -n +1 -F "$LOG" &
TAILPID=$!
trap 'echo; echo "(Ctrl-c -> engine: draining; wait for CTEST_DONE)"' INT
$B --snipe-once --concurrent --junk-fanout "${FL[@]}" --no-telegram < /root/.nexus-v2-trading-wallet.pass >> "$LOG" 2>&1
RC=$?
echo "CTEST_DONE rc=$RC $(date -u)" >> "$LOG"
sleep 1; kill $TAILPID 2>/dev/null
trap - INT
