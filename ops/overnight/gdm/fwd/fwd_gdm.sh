#!/bin/bash
# FORWARD TEST of FRZ-GDM-U (dryrun/frozen_gdm.json, frozen 10-23 09:10 PKT): read-only, offline, nothing traded, no RPC.
# Run at any time; each run appends a timestamped report to gdm/fwd/forward_gdm.txt for launches created after the
# freeze and >= 6 min old in the synced data. Writes ONLY new paths:
#   /home/moiz/sniper-data/collect/phaseA_gdmfwd   our incremental phase-A rows (R2 raw chunks from 04:57 PKT on)
#   /home/moiz/sniper-data/collect/phaseB_gdmfwd   our phase-B launch rows (rebuilt each run)
#   /home/moiz/sniper-data/collect/phaseB_gdmhist  one-time frozen copy of phaseB_fwd rows created before 04:59 PKT
#   /home/moiz/sniper-data/collect/paper/{table_gdmfwd_all,dump_feats_gdmfwd,dump_feats_gdmfwd.raw,table_gdmfwd}.jsonl.gz
#   gdm/fwd/*  (labels, features, picks, become_eval output, logs, report)
# Reads: run_20261021_2207 + run_20261022_1543 (raw collection synced by the dry-run loop), phaseA (R1), phaseA_gf (R2
# static snapshot), phaseB (R1), phaseB_fwd (one-time copy), core/gf_launches.json, gdm/labels.json, shadow/scores_v*.jsonl.
# CPU: nice, at most 6 worker processes per step. A lock prevents overlapping runs.
set -euo pipefail
D=/home/moiz/sniper-data/collect; G=/home/moiz/sniper/ops/overnight/gdm; F=$G/fwd; S=/home/moiz/sniper/ops/select
R1=run_20261021_2207; R2=run_20261022_1543
START_TS=1792713436      # first R2 raw chunk we extract (10-23 04:57:16 PKT)
CUT=1792713556           # R2 launches created before this come from the phaseB_fwd copy, from it on from our phase B
LAB_CUT=1792723800       # 07:50 PKT: labels before = gdm/labels.json (static snapshot), from it on = our forward labels
FREEZE=$(python3 -I -c "import json; print(json.load(open('/home/moiz/sniper/ops/overnight/dryrun/frozen_gdm.json'))['frozen_at_unix'])")
mkdir -p $F/logs
exec 9>$F/.lock
flock -n 9 || { echo "fwd_gdm: another run is active, skipping"; exit 0; }
log() { echo "[$(TZ=Asia/Karachi date '+%H:%M:%S')] $*" | tee -a $F/logs/run.log; }
# be polite to the dry-run loop: wait (max 10 min) while it syncs / extracts
for i in $(seq 1 10); do ps -eo args | grep -E 'a_extract|cycle.sh|sync.sh' | grep -v grep > /dev/null || break; log "dry-run cycle busy, waiting"; sleep 60; done
T0=$(date +%s)
[ -f $D/phaseB_gdmhist/_ok ] || nice python3 -I $F/mk_hist.py $D/phaseB_fwd $D/phaseB_gdmhist $CUT | tee -a $F/logs/run.log
log "phase A (incremental)"; nice python3 -I $F/gdm_pha.py $D/$R2 $D/phaseA_gdmfwd $START_TS 6 >> $F/logs/run.log 2>&1
log "phase B"; rm -rf $D/phaseB_gdmfwd.new
nice python3 -I $S/b_launch.py $D/phaseA_gdmfwd $D/$R2 $D/phaseB_gdmfwd.new 6 > $F/logs/b.log 2>&1
rm -rf $D/phaseB_gdmfwd; mv $D/phaseB_gdmfwd.new $D/phaseB_gdmfwd
log "table (c_join, f_dump, merge)"
nice python3 -I $F/c_join_gdm.py $D/phaseB,$D/phaseB_gdmhist@@$CUT,$D/phaseB_gdmfwd@$CUT@ $D/$R1,$D/$R2 $D/paper/table_gdmfwd_all.jsonl.gz > $F/logs/c.log 2>&1
nice python3 -I $F/f_dump6.py $D/paper/table_gdmfwd_all.jsonl.gz $D/phaseA,$D/phaseA_gf,$D/phaseA_gdmfwd $D/$R1/launches.jsonl,$D/$R2/launches.jsonl $D/paper/dump_feats_gdmfwd.jsonl.gz > $F/logs/f.log 2>&1
nice python3 -I $S/merge_dump.py $D/paper/table_gdmfwd_all.jsonl.gz $D/paper/dump_feats_gdmfwd.jsonl.gz $D/paper/table_gdmfwd.jsonl.gz.tmp > /dev/null
mv $D/paper/table_gdmfwd.jsonl.gz.tmp $D/paper/table_gdmfwd.jsonl.gz
DEND=$(python3 -I -c "
import json
a = json.load(open('$D/phaseA_gdmfwd/_data_end.json'))['data_end']; mx = 0
for l in open('$D/$R2/launches.jsonl'):
    try: mx = max(mx, json.loads(l).get('bt') or 0)
    except Exception: pass
print(int(min(a, mx)))")
HI=$((DEND - 360))
log "labels + features (data end $DEND, window $FREEZE -> $HI)"
nice env RP_PHASEA_R2=phaseA_gdmfwd python3 -I $F/fwd_labels.py $LAB_CUT $DEND $F/labels_fwd.json >> $F/logs/run.log 2>&1
nice python3 -I $F/fwd_features.py $D/paper/table_gdmfwd.jsonl.gz $F/labels_fwd.json $LAB_CUT $FREEZE $HI $F/feats_fwd >> $F/logs/run.log 2>&1
log "score + replay + report"
nice python3 -I $F/fwd_eval.py $F/feats_fwd $FREEZE $HI $DEND
log "done in $(( $(date +%s) - T0 )) s"
