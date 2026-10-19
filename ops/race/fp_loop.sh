#!/bin/bash
# re-score the fresh forward run under the landing models every ~2 h and refresh NOTES.md (READ-ONLY)
set -a; . /root/arbx/deploy/.env; set +a
cd /root/race
sleep 3300
while true; do
  python3 forward_proof.py fresh > fp_fresh.tmp 2>&1 && grep -q "^VERDICT" fp_fresh.tmp && mv fp_fresh.tmp fp_fresh.txt && python3 fp_update.py >> fp_loop.log 2>&1
  grep -q PAPER_RACE_DONE paper_fresh.log && break
  sleep 7200
done
