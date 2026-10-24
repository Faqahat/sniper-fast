#!/bin/bash
# wait for the follower-limit decode, rebuild the replay with real limits, score the frozen tiers, then the timing check
cd /home/moiz/sniper/ops/overnight/sel
while pgrep -f "[s]lip_fetch_sel.py" > /dev/null; do sleep 10; done
echo "[$(TZ=Asia/Karachi date +%H:%M)] decode done: $(wc -l < slip_args_sel.jsonl) lines"
env RP_PHASEA_R2=phaseA_sel SELL_LAT=75 SLIPIMP=1 DIP_REAL_SLIP=1 SEL_SLIP=1 DIP_LATS=35,50,75 DIP_B=0.5 DIP_HS=4 DIP_BUSY=0 DIP_HLAG=0 DIP_MAX_AGE=1800 DIP_COHORT_FILE=cohort_train.json DIP_OUT=sel3r_events.jsonl.gz DIP_XOUT=sel3r_exits.npy timeout 7000 nice python3 -I selexit2.py > selexit2_real.log 2>&1
echo "[$(TZ=Asia/Karachi date +%H:%M)] rebuild done"
SELV=3 timeout 1800 python3 -I sel_real_eval.py > real_eval.txt 2>&1
echo "[$(TZ=Asia/Karachi date +%H:%M)] real-limit eval done"; cat real_eval.txt
for T in top4 top2; do
  EX=$(python3 -I -c "import json; print(','.join(str(x) for x in json.load(open('IMIT1.json'))['exits']['$T']))")
  for SH in 0 15; do echo "== $T exit $EX routed shift $SH"; timeout 3000 python3 -I sel_reallat.py picks_imit1_${T}_test.jsonl $EX $SH 2>&1 | tail -6; done
done > reallat.txt 2>&1
echo "[$(TZ=Asia/Karachi date +%H:%M)] timing check done"; cat reallat.txt
