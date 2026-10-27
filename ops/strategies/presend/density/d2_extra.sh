#!/bin/bash
# DENSITY step 2b: scenarios added after runs 28/27's main pass (same seeds and windows; d3_tables.py merges rep_r*_extra.pkl)
cd /home/moiz/sniper/ops/strategies/presend/density
until grep -q ALLDONE /home/moiz/sniper-data/presend_density/d2.log; do sleep 5; done
python3 drun.py 28 --draws 100 --procs 14 --tag extra --only base_lag15,pos2_lag15,cap3_k8_lag15,cap3_k16_lag15,a3_k8_pos2_lag15,cap3_k8_pos2_lag15,b1_k4_lag15,base_ws80,b1_k4_ws80,a3_k8_ws80,cap3_k8_ws80
python3 drun.py 27 --draws 100 --procs 14 --tag extra --only base_ws80,b1_k4_ws80,a3_k8_ws80,cap3_k8_ws80
echo EXTRADONE
