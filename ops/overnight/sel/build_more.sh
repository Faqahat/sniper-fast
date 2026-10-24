#!/bin/bash
# new strategy datasets at a 60 ms landing (and 75 ms), R1 + R2 (study data, real/imputed follower limits), cohort from TRAIN only
cd /home/moiz/sniper/ops/overnight/sel
C="RP_PHASEA_R2=phaseA_sel SELL_LAT=75 SLIPIMP=1 DIP_REAL_SLIP=1 SEL_SLIP=1 DIP_LATS=60,75 DIP_B=0.5 DIP_HS=4 DIP_BUSY=0 DIP_HLAG=0 DIP_MAX_AGE=1800 DIP_COHORT_FILE=cohort_train.json"
env $C TRIG=buy DIP_OUT=mom_events.jsonl.gz DIP_XOUT=mom_exits.npy DIP_GOUT=mom_exits_grid.json timeout 5000 nice python3 -I selexit3.py > mom_build.log 2>&1
env $C TRIG=sell DIP_OUT=dip60_events.jsonl.gz DIP_XOUT=dip60_exits.npy DIP_GOUT=dip60_exits_grid.json timeout 5000 nice python3 -I selexit3.py > dip60_build.log 2>&1
echo BUILT
