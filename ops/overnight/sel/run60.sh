#!/bin/bash
# dump-buy replay at a 60 ms landing, sizes 0.5 / 1 / 2 SOL (same events as the study; real follower limits), then the tier table
cd /home/moiz/sniper/ops/overnight/sel
for B in 0.5 1.0 2.0; do
  env RP_PHASEA_R2=phaseA_sel SELL_LAT=75 SLIPIMP=1 DIP_REAL_SLIP=1 SEL_SLIP=1 DIP_LATS=60 DIP_B=$B DIP_HS=4 DIP_BUSY=0 DIP_HLAG=0 DIP_MAX_AGE=1800 \
      DIP_COHORT_FILE=cohort_train.json DIP_OUT=sel60_b${B}_events.jsonl.gz DIP_XOUT=sel60_b${B}_exits.npy timeout 3000 nice python3 -I selexit2.py > /dev/null 2>&1
done
python3 -I eval60.py
