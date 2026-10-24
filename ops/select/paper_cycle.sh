#!/bin/bash
# One FORWARD PAPER-TEST cycle (read-only, no money): copy the new collection run from the server (only new/changed
# files), rebuild phases A-C (history joined with run 1), score with the frozen strategies, write paper/forward.txt.
set -e
D=/home/moiz/sniper-data/collect; R2=${R2:-run_20261022_1543}; R1=run_20261021_2207; H=$(dirname "$0")
mkdir -p $D/$R2/txs
ssh -p 1996 it@84.32.100.36 "sudo bash -c 'cd /root/sniper-collect/$R2 && find txs -name \"*.gz\" -printf \"%s %p\n\"'" > $D/paper/remote_list.txt
need=$(while read sz p; do [ -f "$D/$R2/$p" ] && [ "$(stat -c %s "$D/$R2/$p")" = "$sz" ] || echo "$p"; done < $D/paper/remote_list.txt)
ssh -p 1996 it@84.32.100.36 "sudo tar -C /root/sniper-collect/$R2 -cf - launches.jsonl enrich.jsonl run.json $(echo $need)" | tar -xf - -C $D/$R2
rm -rf $D/phaseA_fwd $D/phaseB_fwd
nice python3 -I $H/a_extract.py $D/$R2 $D/phaseA_fwd 14 > $D/paper/a.log 2>&1
nice python3 -I $H/b_launch.py $D/phaseA_fwd $D/$R2 $D/phaseB_fwd 14 > $D/paper/b.log 2>&1
python3 -I $H/c_join.py $D/phaseB,$D/phaseB_fwd $D/$R1,$D/$R2 $D/paper/table_all.jsonl.gz > $D/paper/c.log 2>&1
START=$(python3 -c "import json; print(json.load(open('$D/$R2/run.json'))['start_time'])")
python3 -I $H/g_forward.py $D/paper/table_all.jsonl.gz $START $D/paper $D/paper/frozen_fsell_eos.json $D/paper/frozen_fsell.json $D/paper/frozen_h5s.json $D/paper/frozen_sk2_eos.json $D/paper/frozen_h3s.json $D/paper/frozen_sk1_eos.json $D/paper/frozen_live_fsell.json $D/paper/frozen_live2_fsell.json
