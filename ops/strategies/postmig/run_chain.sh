#!/bin/bash
# waits for pass 1, then merge/build/wallets per run (3 runs in parallel = 3 processes)
L=/home/moiz/sniper-data/strategies/postmig
until ! pgrep -f "[p]m1_extract.py" >/dev/null; do sleep 5; done
for r in R3 R2 R4; do (python3 pm2_merge.py $r && python3 pm3_build.py $r && python3 pm4_wallets.py $r) > $L/chain_$r.log 2>&1 & done
wait
echo ALLDONE >> $L/chain_R3.log
