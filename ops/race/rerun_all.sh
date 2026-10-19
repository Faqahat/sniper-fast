#!/bin/bash
# re-run every analysis after the 217 ms slot-time correction (READ-ONLY)
cd /root/race
python3 race_build.py > rerun_build.log 2>&1
python3 race_an.py > an_final.txt 2>&1
python3 gate_variants.py > gate_variants.txt 2>&1
python3 fwd_eval.py paper_fwd.log fwd_onchain.jsonl paths_fwd.jsonl 100 > fwd_eval.txt 2>&1
python3 land_req.py paper_fwd.log fwd_onchain.jsonl paths_fwd.jsonl > land_req.txt 2>&1
python3 hc_search.py paper_fwd.log fwd_onchain.jsonl paths_fwd.jsonl > hc_fwd1.txt 2>&1
python3 score_run.py fwd > score_fwd.txt 2>&1
echo RERUN_DONE > rerun.done
