#!/bin/bash
# INSIDER: r39-so-far replay inputs (read-only server reads: sudo cat), all outputs in our own folders.
set -euo pipefail
H=/home/it/sniper/ops/strategies/presend/insider; M=/home/it/sniper/ops/strategies/presend/multiarm
D=/home/it/sniper-data/insider; S=/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/insider
REC=/data/tapes/collect/run_20261029_1400/txs
mkdir -p $D/raw $S/rec39/run_20261029_1400/txs $S/dec39
date -u +"%F %T UTC" > $D/raw/cut_r39.txt
timeout 300 ssh -p 1996 -o BatchMode=yes it@cyberams "sudo cat /root/prod/runs/dip_ams_r39.jsonl" > $D/raw/r39.jsonl.tmp && mv $D/raw/r39.jsonl.tmp $D/raw/r39.jsonl
LAST=$(ls "$REC" | sort | tail -1)
for f in $(ls "$REC" | awk -F'[_.]' '$2>=1793319956' | sort); do [ "$f" = "$LAST" ] && continue; ln -sf "$REC/$f" "$S/rec39/run_20261029_1400/txs/$f"; done
nice python3 /home/it/sniper/ops/obs/paper_audit/pa_decode.py $S/dec39 $S/rec39/run_20261029_1400 --procs 5 | tail -2
rm -rf $D/tab39.new && nice python3 /home/it/sniper/ops/strategies/presend/real/build.py $S/dec39 $D/tab39.new && rm -rf $D/tab39 && mv $D/tab39.new $D/tab39
cd $M
nice python3 ma1_extract.py $D/raw/r39.jsonl $D/x_r39.pkl --name r39 --obs $D/r39.obs.jsonl | tail -2
nice python3 ma2_validate.py $D/x_r39.pkl $D/tab39 $D/val_r39.json > /dev/null
nice python3 $H/in0_ctx.py $D/x_r39.pkl $D/tab39 $D/val_r39.json $D/ctx_r39.pkl | tail -2
echo R39 DONE
