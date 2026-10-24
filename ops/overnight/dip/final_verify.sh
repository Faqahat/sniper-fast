#!/bin/bash
# Final re-verification on ALL data collected so far (read-only; RPC only to decode follower slippage limits).
#  1. rebuild dip events (spacing 5, 2-slot exit, real limits where decoded)
#  2. label every trigger direct / routed (collector raw rows; rule = 99.8% vs RPC truth)
#  3. out-of-fold picks -> decode their followers' real limits -> rebuild
#  4. six-block CV: all triggers, direct-only; OOF picks saved for the hybrid and trades-per-hour numbers
set -u
cd /home/moiz/sniper/ops/overnight/dip
EV=ev_final.jsonl.gz; S=../dipshadow
ENVB="RP_PHASEA_R2=phaseA_dry SELL_LAT=75 SLIPIMP=1 DIP_REAL_SLIP=1 DIP_LATS=35,50,75 DIP_B=0.5 DIP_HS=2 DIP_BUSY=5 DIP_HLAG=0"
echo "[$(TZ=Asia/Karachi date +%H:%M)] build 1"; env $ENVB DIP_OUT=$EV timeout 3500 python3 -I dipbuy5.py > final_build.log 2>&1; head -n 1 final_build.log
echo "[$(TZ=Asia/Karachi date +%H:%M)] trigger sigs"; (cd $S && timeout 3000 python3 -I trig_sigs.py trig_sigs_final.jsonl --all ../dip/$EV 1.0 2>&1 | grep -v -i warn | tail -n 1)
echo "[$(TZ=Asia/Karachi date +%H:%M)] programs of new trigger txs"
(cd $S && python3 -I - <<'PY'
import json
done = {json.loads(l)["sig"] for l in open("trig_progs_all.jsonl")}
new = sorted({json.loads(l).get("sig") for l in open("trig_sigs_final.jsonl")} - done - {None})
json.dump(new, open("trig_sigs_new_list.json", "w")); print("new trigger sigs", len(new))
PY
NPROC=6 timeout 3000 python3 -I scan_progs.py trig_sigs_new_list.json trig_progs_new.jsonl | tail -n 1
cat trig_progs_all.jsonl trig_progs_new.jsonl > trig_progs_final.jsonl
python3 -I direct_rule.py trig_sigs_final.jsonl trig_progs_final.jsonl trig_tx.jsonl direct_flags_final.json 2>&1 | tail -n 2)
echo "[$(TZ=Asia/Karachi date +%H:%M)] OOF picks + follower limits"
rm -f sel_final_pre.jsonl
for M in none filter; do SEL_OUT=sel_final_pre.jsonl DIRECT_FILE=$S/direct_flags_final.json DIRECT_MODE=$([ $M = none ] && echo "" || echo $M) EVF=$EV EXIT=2 LATS=35,50,75 Q=0.05 timeout 3000 python3 -I dipcv.py > /dev/null 2>&1; done
WIN=3 timeout 1800 python3 -I follower_sigs2.py sel_final_pre.jsonl 2>&1 | grep -v -i warn | tail -n 1
(cd ../core && timeout 3600 python3 -I slip_fetch.py ../dip/follower_sigs2.json 2>&1 | tail -n 1)
echo "[$(TZ=Asia/Karachi date +%H:%M)] build 2 (with the new limits)"; env $ENVB DIP_OUT=$EV timeout 3500 python3 -I dipbuy5.py > final_build.log 2>&1; head -n 1 final_build.log
echo "[$(TZ=Asia/Karachi date +%H:%M)] six-block CV"
rm -f sel_final_none.jsonl sel_final_filter.jsonl
for M in none filter; do echo "=== mode $M"; SEL_OUT=sel_final_$M.jsonl DIRECT_FILE=$S/direct_flags_final.json DIRECT_MODE=$([ $M = none ] && echo "" || echo $M) EVF=$EV EXIT=2 LATS=35,50,75 GUARDS=1.02 Q=0.05 timeout 3000 python3 -I dipcv.py 2>&1 | grep -E "^LAT|all blocks|block [0-5]"; done > cv_final.txt 2>&1
grep -E "===|^LAT|all blocks" cv_final.txt
echo "[$(TZ=Asia/Karachi date +%H:%M)] done"
