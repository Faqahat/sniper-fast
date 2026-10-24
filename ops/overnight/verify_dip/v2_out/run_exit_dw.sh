#!/bin/bash
# claim 6: exits with follower slippage limits applied only to followers that could not yet have seen our buy (DW ms after it)
cd /home/moiz/sniper/ops/overnight/verify_dip
while [ ! -f v2_out/run_hlag_sel2.done ]; do sleep 10; done
export RP_PHASEA_R2=phaseA_dry SELL_LAT=75 SLIPIMP=1 DIP_REAL_SLIP=1 DIP_LATS=35,50,75 DIP_B=0.5 DIP_HS=2,4,8,10,20,40,80 DIP_BUSY=5 DIP_HLAG=0 V2_DWS=0,400,1000 V2_SLIP=/home/moiz/sniper/ops/overnight/verify_dip/v2_snap/slip_args_snap.jsonl
cd v2_mods && DIP_OUT=../v2_out/ev_dw.jsonl.gz python3 -I dipbuy5_dw.py > ../v2_out/ev_dw_build.log 2>&1; cd ..
# fixed picks: the 2-slot model's out-of-fold picks, every exit variant priced on them
ALLP=1 EVF=v2_out/ev_dw.jsonl.gz EXIT=2 LATS=35,50,75 OUT=v2_out/oof_dw_exit2.jsonl python3 -I v2_cv.py > v2_out/v2cv_dw_exit2.log 2>&1
echo done > v2_out/run_exit_dw.done
