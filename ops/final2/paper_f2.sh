#!/bin/bash
# FINAL-2 PAPER run on the server (NO SENDS): the scorer in serve mode + the engine in --paper-trade with the F2 selection.
# Run as root from /root/sniper-f2 after deploy_f2.sh. Needs the owner's OK. Checks: FINAL2 lines (pick / srv_us / wait_us),
# no TIMEOUT / SEND-FAIL, picks vs the shadow scorer's final_pick on the same launches (/root/sniper-shadow/out/shadow_scores.jsonl).
# The collector run dir must be the RUNNING collection (the scorer's creator / dump history comes from its closed chunks).
set -a; . /root/sniper/deploy/.env; set +a
cd /root/sniper-f2
CRUN=${CRUN:-/root/sniper-collect/run_20261022_1543}
MIN=${MIN:-120}
export FINAL2_SOCK=/root/sniper-f2/f2.sock
touch engine.log
nohup python3 -I scorer.py engine.log frozen_live3_fsell.json,frozen_dump2.json,frozen_live2_fsell.json shadow_seed.json "$CRUN" /root/sniper-collect/tipmap.json out final_config2.json > scorer.log 2>&1 &
echo "scorer pid $! — waiting 90 s for its history to load"; sleep 90
[ -S "$FINAL2_SOCK" ] || { echo "no scorer socket — abort"; exit 1; }
./snipe_engine_final2 --config /root/run1/run1_landing.toml --paper-trade --minutes "$MIN" \
  --min-dev-buy 0 --max-dev-buy-sol 100 --race-gate --race-glued --race-bundle-ms 3 --create-ms-src wall \
  --final2-sock "$FINAL2_SOCK" --final2-timeout-ms 5 2>> engine.log
echo "paper run done: grep FINAL2 engine.log | tail"
