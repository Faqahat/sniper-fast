#!/bin/bash
# VERIFY final refresh: decode the newest chunks, drop truncated (still copying) ones, rebuild the fresh tape, refresh r27,
# rerun every forward test. Outputs: DATA/final_*.txt
V=/home/moiz/sniper-data/haqq_dissect/verify; C=/home/moiz/sniper/ops/strategies/haqq_dissect/verify
cd $C
./v0_decode.sh > $V/v0_decode_final.log 2>&1
python3 - <<'PY'
import glob, json, os, numpy as np
for f in glob.glob("/home/moiz/sniper-data/haqq_dissect/verify/dec/*.npz"):
    m = json.loads(np.load(f, allow_pickle=True)["meta"][0])
    if m["truncated"]: os.remove(f); print("removed truncated", os.path.basename(f))
PY
python3 /home/moiz/sniper/ops/strategies/presend/real/build.py $V/dec $V/tab
timeout 120 ssh -p 1996 it@84.32.100.36 'sudo cat /root/prod/runs/dip_r27.jsonl' > $V/live/dip_r27.jsonl.part && mv $V/live/dip_r27.jsonl.part $V/live/dip_r27.jsonl
rm -f $V/our_sighs.pkl $V/v2b_donors_fra.pkl
python3 v1_rsim_fwd.py $V/tab --draws 5 --tag fwdF --cov 0.94 > $V/v1_fwdF.log 2>&1
python3 v1_rsim_fwd.py $V/tab --draws 5 --tag fwdF_h0 --cov 0.94 --cfg any:20:30:8:0 > $V/v1_fwdF_h0.log 2>&1
python3 v1b_report.py $V/fwdF_res.pkl > $V/final_claim1_rsim.txt
python3 v1b_report.py $V/fwdF_h0_res.pkl > $V/final_claim1_rsim_noholder.txt
python3 v2b_reimpl.py $V/tab freshF --fresh --seeds 10 --cov 0.94 > $V/v2b_freshF.log 2>&1
python3 v2b_reimpl.py $V/tab freshFfra --fresh --seeds 10 --cov 0.94 --donors fra > $V/v2b_freshFfra.log 2>&1
python3 v2c_report.py $V/v2b_freshF.pkl hour > $V/final_claim1_mine_ams.txt
python3 v2c_report.py $V/v2b_freshFfra.pkl hour > $V/final_claim1_mine_fra.txt
python3 v6_null.py fwdF v2b_freshF v2b_freshFfra > $V/final_claim1_null.txt
python3 v4_wave_live.py > $V/final_claim2_wave_live.txt
python3 v5_validate.py --seeds 10 > $V/final_v5_validate.txt
python3 v2a_live_gap.py $V/tab freshF /home/moiz/sniper-data/runs/fra/runs/dip_r26.jsonl $V/live/dip_r27.jsonl > $V/final_v2a_fresh.txt

python3 v8_live_hours.py $V/fwdF_res.pkl > $V/final_v8_live_hours.txt
echo FINAL_DONE
