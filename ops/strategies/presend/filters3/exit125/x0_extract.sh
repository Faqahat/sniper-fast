#!/bin/sh
# EXIT-125v200 step 0: grep the live pre-send events + hold tapes out of the run files (read-only)
R=/home/moiz/sniper-data/runs; O=/home/moiz/sniper-data/filters3/exit125
for r in 42 43 44 45 46 47 48; do
  grep -h -E '"ev":"presend_live_(fill|exit|sell_land|realized|close|ata_close)"' $R/ams/runs/dip_ams_r$r.jsonl > $O/ev_r$r.jsonl
  grep -h '"ev":"hold_tape"' $R/ams/runs/dip_ams_r$r.obs.jsonl* > $O/ht_r$r.jsonl
done
grep -h -E '"ev":"presend_live_(fill|exit|sell_land|realized|close|ata_close)"' $R/ams_r49/dip_ams_r49.jsonl > $O/ev_r49.jsonl
grep -h '"ev":"hold_tape"' $R/ams_r49/dip_ams_r49.obs.jsonl* > $O/ht_r49.jsonl
grep -h -E '"ev":"presend_live_(fill|exit|sell_land|realized|close|ata_close)"' $R/ams_r50/dip_ams_r50.jsonl > $O/ev_r50.jsonl
