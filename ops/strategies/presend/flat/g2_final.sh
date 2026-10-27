#!/bin/bash
# FLAT study: after r28 ended (w1_wait.sh READY). usage: g2_final.sh HI_UNIX_S
# fetch the final r28 records (read-only sudo cat), extract phase 3 (20:49 PKT -> HI), rebuild r28, cut at HI - 60 s, run the gate.
set -e
HI=$1; D=/home/moiz/sniper-data/presend_flat; cd /home/moiz/sniper/ops/strategies/presend/flat
timeout 300 ssh -p 1996 -o ConnectTimeout=20 -o BatchMode=yes it@84.32.104.202 'sudo cat /root/prod/runs/dip_ams_r28.jsonl' > $D/r28/dip_ams_r28.jsonl.tmp && mv $D/r28/dip_ams_r28.jsonl.tmp $D/r28/dip_ams_r28.jsonl
timeout 300 ssh -p 1996 -o ConnectTimeout=20 -o BatchMode=yes it@84.32.104.202 'sudo cat /root/prod/runs/dip_ams_r28.log' > $D/r28/dip_ams_r28.log.tmp && mv $D/r28/dip_ams_r28.log.tmp $D/r28/dip_ams_r28.log
python3 f1_extract.py 3 --hi $HI --procs 14 > $D/f1_p3_final.log 2>&1; tail -2 $D/f1_p3_final.log
python3 f2_live.py r28 && python3 f3_base.py r28 && python3 f4_features.py r28 && python3 h_cut.py $HI
python3 g1_gate.py --out g1_gate_final
