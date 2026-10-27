#!/bin/bash
# DENSITY step 2: every scenario on runs 24-28, 100 draws each (read-only, offline)
cd /home/moiz/sniper/ops/strategies/presend/density
for r in 28 27 25 26 24; do python3 drun.py $r --draws 100 --procs 14; done
echo ALLDONE
