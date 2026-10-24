#!/bin/bash
# ===== DIP LANDING PROBES — REAL SOL (fees only) — DEV wallet FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS =====
# Owner 10-24 ~01:55 PKT: "see if we can improve our landing by changing txn fee or path change. do whatever u have to do".
# --dip-probe: on real in-envelope dumps, buys that CANNOT fill (min tokens out = u64::MAX -> pump 6042: no token bought, tips
# revert, cost = base + priority fee ~0.0005 SOL each) through the route for the slot's leader client; block position after
# the dump = that route's landing delay (ops/dip/speed/probe_speed.py). No trades. Refuses while another engine runs.
#   usage (server, root): bash /root/sniper-dip/run_dip_probe.sh <tag> <probes> "<routes>" [cu-price-micro, default 5000000]
#          [probe paths "a,b,c" rotated one per probe] [near-leader list file]   (10-24: dip8 + dip_probe.toml = +tpu-direct, bolt, haan)
set -u
TAG=$1; N=$2; ROUTES=$3; CUP=${4:-5000000}; PPATHS=${5:-}; NEAR=${6:-}
D=/root/sniper-dip; B=$D/snipe_engine_dip8; PC=$D/dip_probe.toml
[[ "$N" =~ ^[0-9]+$ ]] && [ "$N" -ge 1 ] && [ "$N" -le 100 ] || { echo "REFUSED: probes 1..100"; exit 1; }
EXTRA=""; [ -n "$PPATHS" ] && EXTRA="$EXTRA --dip-probe-paths $PPATHS"; [ -n "$NEAR" ] && { [ -f "$NEAR" ] || { echo "REFUSED: missing $NEAR"; exit 1; }; EXTRA="$EXTRA --dip-near-leaders $NEAR"; }
[[ "$CUP" =~ ^[0-9]+$ ]] && [ "$CUP" -le 30000000 ] || { echo "REFUSED: cu price <= 30M micro-lamports"; exit 1; }
pgrep -x snipe_engine > /dev/null && { echo "REFUSED: a snipe_engine is running"; exit 1; }
pgrep -f "[s]nipe_engine_dip" > /dev/null && { echo "REFUSED: a dip engine is running"; exit 1; }
[ -x "$B" ] || { echo "REFUSED: missing $B"; exit 1; }
grep -q '^wallet *= *"FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"' $PC || { echo "REFUSED: $PC is not the FRZ wallet"; exit 1; }
[ -e "$D/$TAG.jsonl" ] && { echo "REFUSED: $D/$TAG.jsonl exists"; exit 1; }
setsid nohup bash -c "
  $B --dip --live --dip-probe $N --dip-probe-gap-ms 1500 $EXTRA --fast-send --jito-h2 --fast-presign --fast-derive --fast-verify \
    --dip-tier strict --dip-allow-holder --dip-guard 1.05 --dip-model /root/dip/IMIT1.json --dip-cohort /root/dip/cohort_train.json --dip-log $D/$TAG.jsonl \
    --spend-lamports 20000000 --max-sol 0.021 --max-total-sol 0.1 --max-buys 1 --max-inflight 1 --max-loss-sol 0.06 --minutes 20 \
    --cu-limit 100000 --cu-price-micro $CUP --sell-cu-limit 120000 --sell-cu-price-micro 5000000 \
    --land-poll-ms 100 --land-timeout-ms 3000 --sell-robust --sell-retry-s 1 --sell-deadline-s 30 --sell-fallback-path nozomi \
    --buy-max-slot-delta 1 --rpc-fallback-url-env RMR_RPC_URL --env-name DEV --strict-balance --ks-blind-s 10 \
    --send-path helius --sell-path staked-rpc --route-by-client '$ROUTES' --no-union-harmonic --no-telegram \
    --config $PC --env-file /root/sniper/deploy/.env < /root/.nexus-v2-trading-wallet.pass >> $D/$TAG.log 2>&1
  echo \"DIP_PROBE_DONE $TAG \$(date -u)\" >> $D/$TAG.log" > /dev/null 2>&1 < /dev/null &
sleep 4
echo "started: engine pid $(pgrep -n -f "[s]nipe_engine_dip8 --dip"), log $D/$TAG.log"
