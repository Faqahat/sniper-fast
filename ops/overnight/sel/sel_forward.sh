#!/bin/bash
# FORWARD test of the frozen IMIT1 selector on data it has never seen (after FWD_FROM PKT): R2 (ended ~18:31 PKT) + the new
# run R3 (run_20261023_1426, from 19:26 PKT, synced read-only by sync_r3.sh),
# rebuild events + exit grid (same builder, cohort from TRAIN, real limits known so far), score with IMIT1, report the tiers
# with their TP/SL/time-limit exits, hour by hour, side by side with the three wallets. Local only, free.
set -u
cd /home/moiz/sniper/ops/overnight/sel
FWD_FROM=${FWD_FROM:-"10-23 18:20"}
D=/home/moiz/sniper-data/collect
/home/moiz/sniper-data/work/sync_r3.sh > /home/moiz/sniper-data/work/sync_r3.log 2>&1 || echo "R3 sync failed (using what is local)"
if [ ! -d $D/phaseA_selfwd ]; then                                     # R2 stopped at ~18:31 PKT: one stable copy is enough
  while [ -d $D/phaseA_dry.new ]; do sleep 20; done; cp -a $D/phaseA_dry $D/phaseA_selfwd
fi
env RP_PHASEA_R2=phaseA_selfwd RP_PHASEA_R3=phaseA_r3 SELL_LAT=75 SLIPIMP=1 DIP_REAL_SLIP=1 SEL_SLIP=1 DIP_LATS=35,50,75 DIP_B=0.5 DIP_HS=4 DIP_BUSY=0 DIP_HLAG=0 \
    DIP_MAX_AGE=1800 DIP_COHORT_FILE=cohort_train.json DIP_OUT=sel4f_events.jsonl.gz DIP_XOUT=sel4f_exits.npy timeout 7000 nice python3 -I selexit2.py > selexit2_fwd.log 2>&1
cp sel3_exits_grid.json sel4f_exits_grid.json
echo "== FORWARD from $FWD_FROM PKT (IMIT1 frozen 10-23 ~18:55 PKT, trained on dumps before 10-23 06:00 PKT)"
SELV=4f SPLIT="$FWD_FROM" timeout 1800 python3 -I sel_score_frozen.py IMIT1.json x5_score_fwd.npy 2>&1 | grep -v "TRAIN"
for T in top2 top4; do
  THR=$(python3 -I -c "import json; print(json.load(open('IMIT1.json'))['thresholds']['$T'])")
  EI=$(python3 -I -c "import json; g=[tuple(x) for x in json.load(open('sel4f_exits_grid.json'))['grid']]; m=json.load(open('IMIT1.json')); print(g.index(tuple(m['exits']['$T'])))")
  echo "== $T hour by hour"; SELV=4f SPLIT="$FWD_FROM" timeout 900 python3 -I sel_x_hourly.py x5_score_fwd.npy $THR $EI 2>&1 | tail -n +2
done
