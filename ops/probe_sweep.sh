#!/bin/bash
# SELF-TRANSFER PROBE (no real buys). Sweeps the requested cu_limit to test the
# scheduler-packing hypothesis for lever #1 (slim the buy tx). Same gate/path/cu_price
# across arms so 450 vs 50k vs 120k is a clean apples-to-apples same-slot comparison.
# --max-sol is a HARD cost cap (per_send now includes the real priority fee).
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}

run_arm () {
  local CUL=$1
  local LOG=/root/sniper-fast/probe_cul_${CUL}.log
  : > "$LOG"
  echo "=== ARM cu_limit=$CUL START $(date +%H:%M:%S) ===" >> "$LOG"
  timeout 700 ./target/release/snipe_engine --shadow --warm-probe-on-trigger --live \
    --max-sol 0.04 --max-sends 50 --min-dev-buy 0 --duration-s 640 \
    --send-path staked-rpc --land-poll-ms 15 --cu-price-micro 5000000 \
    --probe-cu-limit "$CUL" \
    --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
    < /root/.nexus-v2-trading-wallet.pass >> "$LOG" 2>&1
  echo "=== ARM cu_limit=$CUL DONE $(date +%H:%M:%S) ===" >> "$LOG"
}

run_arm 450
run_arm 50000
run_arm 120000
echo "SWEEP_DONE" > /root/sniper-fast/probe_sweep.done
