#!/bin/bash
# claim 6: six-block CV with the model retrained on each exit's label, claim follower model vs DW=1000 ms (same data/build)
cd /home/moiz/sniper/ops/overnight/verify_dip
run() { EVF=v2_out/ev_dw.jsonl.gz EXIT=$1 LATS=35,50,75 OUT=v2_out/oof_dw_exit$1.jsonl python3 -I v2_cv.py > v2_out/v2cv_dw_exit$1.log 2>&1; }
run 4 & run 8 & run 20 & run 4w1000 & wait
run 8w1000 & run 20w1000 & run 40 & run 40w1000 & wait
echo done > v2_out/run_exit_cv.done
