#!/bin/sh
# SMARTEXIT step 0: grep live pre-send events + hold tapes out of every run r37..r55 (read-only on run files).
R=/home/moiz/sniper-data/runs; O=/home/moiz/sniper-data/smartexit/ev; mkdir -p $O
S55=/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/r55
PAT='"ev":"presend_live_(arm|fill|exit|sell_land|realized|close|ata_close)"'
ex() { r=$1; j=$2; shift 2
  grep -h -E "$PAT" $j > $O/ev_r$r.jsonl
  cat "$@" | grep -h '"ev":"hold_tape"' > $O/ht_r$r.jsonl
  echo r$r $(wc -l < $O/ev_r$r.jsonl) $(wc -l < $O/ht_r$r.jsonl); }
for r in 37 38 39 40 41 42 43 44 45 46 47 48; do ex $r $R/ams/runs/dip_ams_r$r.jsonl $R/ams/runs/dip_ams_r$r.obs.jsonl*; done
for r in 49 50 51 52 53 54; do ex $r $R/ams_r$r/dip_ams_r$r.jsonl $R/ams_r$r/dip_ams_r$r.obs.jsonl*; done
ex 55 $S55/dip_ams_r55.jsonl $S55/dip_ams_r55.obs.jsonl* $R/ams_r55_snap/dip_ams_r55.obs.jsonl
