#!/bin/bash
# REAL replay: the follow-up runs (read-only, local CPU only): final calibration with diagnostics, the probe-hour check, the
# pessimistic landing, the follower-cut stress. Sizes (V5) are run separately for the variants that pass at 0.35.
set -u
cd /home/moiz/sniper/ops/strategies/presend/real
O=/home/moiz/sniper-data/presend_real
python3 calib.py --draws 400 --procs 14 --tag final > $O/calib_final.log 2>&1
python3 probehours.py --draws 40 > $O/probehours.log 2>&1
python3 variants.py --draws 4 --nulls 0 --procs 14 --mode corr --tag corr > $O/variants_corr.log 2>&1
python3 variants.py --draws 4 --nulls 0 --procs 14 --cut 0.2 --tag cut20 > $O/variants_cut20.log 2>&1
echo AFTER_DONE >> $O/variants_cut20.log
