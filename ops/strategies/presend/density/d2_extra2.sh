#!/bin/bash
# DENSITY step 2c: checks of the recommended lever on all runs (same seeds and windows; merged by d3_tables.py)
cd /home/moiz/sniper/ops/strategies/presend/density
for r in 28 27 25 26 24; do python3 drun.py $r --draws 100 --procs 14 --tag extra2 --only cap2_k8_cut,cap2_k8_lag15,cap2_k8_corr,a2_k8_cut,hg_k8,hg_k8_cut; done
echo EXTRA2DONE
