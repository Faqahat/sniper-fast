#!/bin/bash
set -euo pipefail
H=/home/moiz/sniper/ops/strategies/presend/insider; M=/home/moiz/sniper/ops/strategies/presend/multiarm
D=/home/moiz/sniper-data/insider; R=/home/moiz/sniper-data/runs/ams/runs
cd $M
nice python3 ma1_extract.py $R/dip_ams_r36.jsonl $D/x_r36.pkl --name r36 --obs $R/dip_ams_r36.obs.jsonl | tail -2
nice python3 ma2_validate.py $D/x_r36.pkl /home/moiz/sniper-data/paper_audit/tab36 $D/val_r36.json > /dev/null
nice python3 $H/in0_ctx.py $D/x_r36.pkl /home/moiz/sniper-data/paper_audit/tab36 $D/val_r36.json $D/ctx_r36.pkl | tail -2
echo R36 DONE
