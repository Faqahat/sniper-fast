#!/bin/bash
# DV8 study, full re-run (read-only on recordings/run records). ~20 min on the container. Outputs in /home/moiz/sniper-data/dv8.
set -e
S=/home/moiz/sniper/ops/strategies/dv8; O=/home/moiz/sniper-data/dv8; cd $O
# 0. tape: decoded chunks (dec/ = symlinks to presend_real/dec + haqq_model/dec + own decodes of run_20261027_1410 and the 8 re-decoded
#    chunks that were truncated when first decoded), merged with build.py
# python3 /home/moiz/sniper/ops/strategies/presend/real/decode.py $O/dec /home/moiz/sniper-data/collect/run_20261027_1410 --procs 6
# python3 /home/moiz/sniper/ops/strategies/presend/real/build.py $O/dec $O/tab
python3 $S/c0_coverage.py       # coverage per hour / day
python3 $S/l1_live.py           # live run records -> fires / pre-send attempts (FRA r26 copy in $O/live via read-only sudo cat)
python3 $S/l2_landing.py        # landing model (MEASURED) + far-leader shift (INFERRED)
python3 $S/c1_calib.py          # replay vs live fills / fires
python3 $S/c2_rank.py           # contention-aware landing model, calibration OLS
python3 $S/c3_hazard.py         # alternative hazard landing model (not used: no better than rank)
python3 $S/u1_universe.py       # dump universe + simulated outcomes
python3 $S/u1_check.py          # vectorised vs scalar sim check
python3 -c "
import numpy as np, json; Z=np.load('$O/uni.npz'); ids=json.load(open('$O/tab/ids.json')); CR=json.load(open('$O/tab/creates.json'))
np.save('$O/mayhem.npy', np.array([bool(CR.get(ids[m],{}).get('mayhem') or CR.get(ids[m],{}).get('mayhem_ix')) for m in Z['M']['mint']]))"
python3 $S/c4_s7outliers.py     # old +70 'buy every dump' = mayhem artifacts
python3 $S/c5_dv8old_mayhem.py  # earlier DV8 +31.8 reproduced, mayhem share
python3 $S/g1_walkforward.py    # DV8 walk-forward per day
python3 $S/g2_everydump.py      # buy-every-dump decomposition
python3 $S/g3_asdesigned.py     # DV8 as designed (8,000 picks/day)
python3 $S/a1_actual.py         # what we made per day + haqq per day
python3 $S/c6_liveday.py        # replay pipeline on our actual fires per day
