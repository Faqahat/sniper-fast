#!/bin/bash
# claim 3 (selection leak): rebuild HLAG 100/400 with true vs stale selection (with trigger sigs), label direct/routed, CV both
cd /home/moiz/sniper/ops/overnight/verify_dip
while [ ! -f v2_out/run_hlag_jobs.done ]; do sleep 10; done
export RP_PHASEA_R2=phaseA_dry SELL_LAT=75 SLIPIMP=1 DIP_REAL_SLIP=1 DIP_LATS=35,50,75 DIP_B=0.5 DIP_HS=2 DIP_BUSY=5 V2_SLIP=v2_snap/slip_args_snap.jsonl NPROC=6
for H in 100 400; do
  DIP_HLAG=$H V2_OUT_BASE=v2_out/evs_h${H}_true.jsonl.gz V2_OUT_STALE=v2_out/evs_h${H}_stale.jsonl.gz python3 -I v2_hlag_sel_sig.py > v2_out/hlag_sel_sig_$H.txt 2>&1
done
python3 -I v2_label.py v2_out/labels_sel.json v2_out/evs_h100_true.jsonl.gz v2_out/evs_h100_stale.jsonl.gz v2_out/evs_h400_true.jsonl.gz v2_out/evs_h400_stale.jsonl.gz > v2_out/labels_sel.txt 2>&1
for H in 100 400; do for V in true stale; do
  DIRECT_FILE=v2_out/labels_sel.json EVF=v2_out/evs_h${H}_$V.jsonl.gz EXIT=2 LATS=35,50,75 OUT=v2_out/oof_sel_h${H}_$V.jsonl python3 -I v2_cv.py > v2_out/v2cv_sel_h${H}_$V.log 2>&1 &
done; done; wait
echo done > v2_out/run_hlag_sel2.done
