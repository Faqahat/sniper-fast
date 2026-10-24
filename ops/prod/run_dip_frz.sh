#!/bin/bash
# ===== DIP plumbing test — REAL SOL, tiny — DEV wallet FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS =====
# Owner OK 2026-10-24 ~01:00 PKT: before run 1 on the PROD wallet, 1-2 dip trades at 0.02 SOL on the FRZ test wallet
# (~0.01 SOL total) prove the live buy -> exit -> sell path. Same engine, selector, exits, guard, routes and fees as
# /root/prod/run_dip_prod.sh; only the wallet, the size, the caps and Telegram (off) differ. The passphrase comes from
# the DEV pass file (as the probe / paper engines). Runs detached; stop early with SIGTERM to the engine (no new buys,
# an open position finishes its exit). Refuses while any other engine runs (one engine per server).
#   usage (server, root): bash /root/sniper-dip/run_dip_frz.sh [tag] [trades] [minutes] [strict|wider] [guard, default 1.05]
set -u
TAG=${1:-frz_t1}; TRADES=${2:-2}; MIN=${3:-30}; TIER=${4:-strict}; GUARD=${5:-1.05}
D=/root/sniper-dip
B=$D/snipe_engine_dip8
PC=$D/dip_probe.toml
ROUTES="bam=nozomi+bolt;jito=bolt+astralane;harmonic=nozomi+helius;fd=nozomi+landx-fra3;agave=nozomi+helius;other=nozomi+bolt;default=nozomi+bolt"
[[ "$TRADES" =~ ^[0-9]+$ ]] && [ "$TRADES" -ge 1 ] && [ "$TRADES" -le 3 ] || { echo "REFUSED: trades 1..3"; exit 1; }
[[ "$MIN" =~ ^[0-9]+$ ]] && [ "$MIN" -ge 1 ] && [ "$MIN" -le 90 ] || { echo "REFUSED: minutes 1..90"; exit 1; }
case "$TIER" in strict|wider) ;; *) echo "REFUSED: tier strict|wider"; exit 1;; esac
awk -v g="$GUARD" 'BEGIN{exit !(g>=1.0 && g<=1.10)}' || { echo "REFUSED: guard 1.00..1.10"; exit 1; }
pgrep -x snipe_engine > /dev/null && { echo "REFUSED: a snipe_engine is running"; exit 1; }
pgrep -f "snipe_engine_dip" > /dev/null && { echo "REFUSED: a dip engine is running"; exit 1; }
[ -x "$B" ] || { echo "REFUSED: missing $B"; exit 1; }
grep -q '^wallet *= *"FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"' $PC || { echo "REFUSED: $PC is not the FRZ wallet"; exit 1; }
[ -e "$D/$TAG.jsonl" ] && { echo "REFUSED: $D/$TAG.jsonl exists (pick a new tag)"; exit 1; }
setsid nohup bash -c "
  $B --dip --live --fast-send --jito-h2 --fast-presign --fast-derive --fast-verify \
    --dip-tier $TIER --dip-allow-holder --dip-tp 0.05 --dip-sl 0.10 --dip-hold-slots 6 --dip-guard $GUARD --dip-spacing-slots 5 \
    --dip-model /root/dip/IMIT1.json --dip-cohort /root/dip/cohort_train.json --dip-log $D/$TAG.jsonl \
    --spend-lamports 20000000 --max-sol 0.021 --max-total-sol 0.1 --max-buys $TRADES --max-inflight 1 --max-loss-sol 0.02 --minutes $MIN \
    --cu-limit 100000 --cu-price-micro 5000000 --sell-cu-limit 120000 --sell-cu-price-micro 5000000 \
    --land-poll-ms 100 --land-timeout-ms 3000 --sell-robust --sell-retry-s 1 --sell-deadline-s 30 --sell-fallback-path nozomi \
    --buy-max-slot-delta 1 --rpc-fallback-url-env RMR_RPC_URL --env-name DEV --strict-balance --ks-blind-s 10 \
    --send-path helius --sell-path staked-rpc --route-by-client '$ROUTES' --no-union-harmonic --no-telegram \
    --config $PC --env-file /root/sniper/deploy/.env < /root/.nexus-v2-trading-wallet.pass >> $D/$TAG.log 2>&1
  echo \"DIP_FRZ_DONE $TAG \$(date -u)\" >> $D/$TAG.log" > /dev/null 2>&1 < /dev/null &
sleep 4
echo "started: engine pid $(pgrep -n -f "$B"), log $D/$TAG.log, records $D/$TAG.jsonl"
