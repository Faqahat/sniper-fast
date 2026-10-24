#!/bin/bash
# FINAL-2 PAPER cycle (read-only, no money): copy the running collection from the server, rebuild phases A-C, the
# anti-dump history (f_dump) and the merged table, fetch the live shadow scorer's records, paper-trade FINAL-2
# (first in line right after the bundle, as the owner asked; the 74 ms real-landing view is written too).
set -e
D=/home/moiz/sniper-data/collect; R2=${R2:-run_20261022_1543}; R1=run_20261021_2207; H=$(dirname "$(readlink -f "$0")"); SH=$H/../shadow
mkdir -p $D/$R2/txs $D/shadow
ssh -p 1996 it@84.32.100.36 "sudo bash -c 'cd /root/sniper-collect/$R2 && find txs -name \"*.gz\" -printf \"%s %p\n\"'" > $D/paper/remote_list.txt
need=$(while read sz p; do [ -f "$D/$R2/$p" ] && [ "$(stat -c %s "$D/$R2/$p")" = "$sz" ] || echo "$p"; done < $D/paper/remote_list.txt)
ssh -p 1996 it@84.32.100.36 "sudo tar -C /root/sniper-collect/$R2 -cf - launches.jsonl enrich.jsonl run.json $(echo $need)" | tar -xf - -C $D/$R2
rm -rf $D/phaseA_fwd $D/phaseB_fwd
nice python3 -I $H/a_extract.py $D/$R2 $D/phaseA_fwd 14 > $D/paper/a.log 2>&1
nice python3 -I $H/b_launch.py $D/phaseA_fwd $D/$R2 $D/phaseB_fwd 14 > $D/paper/b.log 2>&1
python3 -I $H/c_join.py $D/phaseB,$D/phaseB_fwd $D/$R1,$D/$R2 $D/paper/table_all.jsonl.gz > $D/paper/c.log 2>&1
python3 -I $H/f_dump.py $D/paper/table_all.jsonl.gz $D/phaseA,$D/phaseA_fwd $D/$R1/launches.jsonl,$D/$R2/launches.jsonl $D/paper/dump_feats.jsonl.gz > $D/paper/f.log 2>&1
python3 -I $H/merge_dump.py $D/paper/table_all.jsonl.gz $D/paper/dump_feats.jsonl.gz $D/paper/table_dump.jsonl.gz > /dev/null
ssh -p 1996 it@84.32.100.36 'sudo cat /root/sniper-shadow/out/shadow_scores.jsonl' > $D/shadow/scores_v3.jsonl
for LM in 0 74; do
  LAND_MS=$LM python3 -I $SH/paper_live.py $SH/final_config2.json $D/paper/table_dump.jsonl.gz $D/phaseA_fwd $D/$R2/launches.jsonl $D/shadow/scores_v1.jsonl,$D/shadow/scores_v2.jsonl,$D/shadow/scores_v3.jsonl $D/shadow/final2_L$LM > /dev/null
done
cp $D/shadow/final2_L0/paper_trades.txt $SH/final2_paper_trades.txt
sed -n 1,9p $SH/final2_paper_trades.txt; echo "--- same trades at our measured 74 ms landing:"; sed -n 4,6p $D/shadow/final2_L74/paper_trades.txt
