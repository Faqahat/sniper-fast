#!/bin/bash
# ===== SPEED PROBE (owner runs it; real sends that FAIL BY DESIGN, cost = base + priority fee only) =====
# Question: after Alpenglow, do single-route buys land fast (target <= 45 ms after the create, pros ~39 ms) while our
# multi-route single transaction (Run 2: 73-75 ms) is slow? See ops/final2/SEND_DESIGN.md, ops/overnight/report/DECISION.html.
# Each phase runs ops/run1/probe_buy.sh: on pump.fun launches in close-leader slots, a REAL pump buy of the launch with
# min_tokens_out = u64::MAX, so it always fails on chain (no token is ever bought; tips revert), timed in our shred feed.
# Hard caps per phase: max probes N and max SOL. The DEV wallet (FRZ) pays.
# Before: stop any running snipe_engine (probe_buy.sh refuses otherwise; the 24 h paper engine counts), and top up FRZ
# with ~0.1-0.3 SOL.
# usage (server, root): bash /root/run1/probe_speed.sh [probes per phase, default 25] [max SOL per phase, default 0.05]
# then: python3 /root/run1/probe_report.py /root/run1/ps_*.jsonl
set -u
N=${1:-25}; MAXSOL=${2:-0.05}
export B=${B:-/root/sniper-probe/snipe_engine}
export CUP=${CUP:-30000000}          # 30M uL/CU x 100k CU = 0.003 SOL priority per probe (paid even though it fails)
run_phase() {   # $1 tag, $2 PATHS ("" = today's multi-route design)
  echo "=== phase $1 (PATHS=${2:-multi-route}) $(date -u +%H:%M:%S) UTC"
  if [ -n "$2" ]; then PATHS="$2" bash /root/run1/probe_buy.sh "$1" "$MAXSOL" "$N"; else env -u PATHS bash /root/run1/probe_buy.sh "$1" "$MAXSOL" "$N"; fi
  # wait for this phase to finish (probe_buy.sh detaches the engine)
  while pgrep -x snipe_engine > /dev/null; do sleep 10; done
  grep -h "PROBE_DONE" "/root/run1/$1.log" | tail -n 1
}
if pgrep -x snipe_engine > /dev/null; then echo "REFUSED: a snipe_engine is running (stop the paper engine first)"; exit 1; fi
run_phase ps_helius helius
run_phase ps_nozomi nozomi
run_phase ps_astralane astralane
run_phase ps_landx landx-fra3
run_phase ps_multi ""
echo "=== done $(date -u +%H:%M:%S) UTC. Score: python3 /root/run1/probe_report.py /root/run1/ps_*.jsonl ; expected dip SOL/day per route: python3 /root/run1/probe_to_pnl.py /root/run1/ps_*.jsonl"
