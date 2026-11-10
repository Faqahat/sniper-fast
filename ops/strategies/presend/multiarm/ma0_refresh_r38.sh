#!/bin/bash
# MULTIARM: refresh run 38's data (read-only on the AMS server: sudo cat of the run's records) and redo its replay steps.
#   1. copy dip_ams_r38.{jsonl,log,obs.jsonl} (the cut time goes to raw/cut_r38.txt)
#   2. link the recorder chunks of run_20261029_1400 from the run's start, decode the new ones (pa_decode, cached per chunk), build tab38
#   3. ma1_extract -> ma2_validate -> ma3_ctx -> ma5_calib (live re-arm calibration) -> ma6_run (variants) -> ma7_tables
# usage: ma0_refresh_r38.sh VARIANTS.json [REPS]
set -euo pipefail
V=${1:?variants json}; REPS=${2:-8}
H=/home/it/sniper/ops/strategies/presend/multiarm
D=/home/it/sniper-data/multiarm
S=/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/multiarm
REC=/data/tapes/collect/run_20261029_1400/txs
cd "$D/raw"
date -u +"%F %T UTC" > cut_r38.txt
for f in jsonl log obs.jsonl; do
  timeout 300 ssh -p 1996 -o BatchMode=yes it@cyberams "sudo cat /root/prod/runs/dip_ams_r38.$f" > "r38.$f.tmp" && mv "r38.$f.tmp" "r38.$f"
done
# chunks: from the run start, complete ones only (the newest file may still be copying: skip the last one)
mkdir -p "$S/rec38/run_20261029_1400/txs" "$S/dec38"
LAST=$(ls "$REC" | sort | tail -1)
for f in $(ls "$REC" | awk -F'[_.]' '$2>=1793307042' | sort); do
  [ "$f" = "$LAST" ] && continue
  ln -sf "$REC/$f" "$S/rec38/run_20261029_1400/txs/$f"
done
python3 /home/it/sniper/ops/obs/paper_audit/pa_decode.py "$S/dec38" "$S/rec38/run_20261029_1400" --procs 6 | tail -2
rm -rf "$D/tab38.new" && python3 /home/it/sniper/ops/strategies/presend/real/build.py "$S/dec38" "$D/tab38.new" && rm -rf "$D/tab38" && mv "$D/tab38.new" "$D/tab38"
cd "$H"
python3 ma1_extract.py "$D/raw/r38.jsonl" "$D/x_r38.pkl" --name r38 --obs "$D/raw/r38.obs.jsonl" | tail -2
python3 ma2_validate.py "$D/x_r38.pkl" "$D/tab38" "$D/val_r38.json" > /dev/null
python3 ma3_ctx.py "$D/x_r38.pkl" "$D/tab38" "$D/val_r38.json" "$D/ctx_r38.pkl" | tail -2
python3 ma5_calib.py "$D/ctx_r38.pkl" "$D/calib_r38.json" "$REPS" > "$S/calib_r38.log" 2>&1
rm -rf "$D/runs/r38" && python3 ma6_run.py "$D/ctx_r38.pkl" "$V" "$D/runs/r38" --reps "$REPS" --procs 8 > "$S/run_r38.log" 2>&1
python3 ma7_tables.py "$D/runs/r38" "$D/tables_r38.json" | tail -40
cat "$D/raw/cut_r38.txt"
