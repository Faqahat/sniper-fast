#!/bin/bash
# claim 3 jobs (background): full HLAG=0 identity check, then true-vs-stale selection builds at HLAG=100 and 400
cd /home/moiz/sniper/ops/overnight/verify_dip
export RP_PHASEA_R2=phaseA_dry SELL_LAT=75 SLIPIMP=1 DIP_REAL_SLIP=1 DIP_LATS=35,50,75 DIP_B=0.5 DIP_HS=2 DIP_BUSY=5 V2_SLIP=v2_snap/slip_args_snap.jsonl NPROC=6
DIP_HLAG=0 python3 -I v2_hlag_identity.py > v2_out/hlag_identity.txt 2>&1
for H in 100 400; do
  DIP_HLAG=$H V2_OUT_BASE=v2_out/ev_h${H}_truesel.jsonl.gz V2_OUT_STALE=v2_out/ev_h${H}_stalesel.jsonl.gz python3 -I v2_hlag_sel.py > v2_out/hlag_sel_$H.txt 2>&1
done
echo done > v2_out/run_hlag_jobs.done
