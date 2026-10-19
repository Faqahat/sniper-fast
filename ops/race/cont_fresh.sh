#!/bin/bash
# PAPER ONLY. Owner: keep the forward proof running until 12:00 am PKT (19:00 UTC).
# When the 'fresh' run ends, start 'fresh2' (same merged binary + flags) until 19:00 UTC, label it on chain, and re-score it
# under the landing models every ~2 h (fp_fresh2.txt). Nothing here sends anything.
cd /root/race
FLAGS="--dev-from-cap --race-gate --race-min-dev-sol 3 --race-min-bundle 2 --race-bundle-ms 3 --race-max-name-len 12 --race-pros /root/race/pros.json --race-track-rejects"
until grep -q PAPER_RACE_DONE /root/race/paper_fresh.log 2>/dev/null; do sleep 60; done
END=$(date -u -d "today 19:00" +%s)
MIN=$(( (END - $(date +%s)) / 60 ))
[ "$MIN" -lt 10 ] && { echo "CONT: too late ($MIN min)"; exit 0; }
echo "CONT: starting fresh2 for $MIN min $(date -u)"
setsid nohup /root/race/paper_race3.sh fresh2 $MIN $FLAGS > /dev/null 2>&1 < /dev/null &
sleep 30
setsid nohup /root/race/chain_loop.sh fresh2 > /dev/null 2>&1 < /dev/null &
set -a; . /root/arbx/deploy/.env; set +a
sleep 3600
while true; do
  python3 forward_proof.py fresh2 > fp_fresh2.tmp 2>&1 && grep -q "^VERDICT" fp_fresh2.tmp && mv fp_fresh2.tmp fp_fresh2.txt && echo "CONT: scored $(date -u)"
  grep -q PAPER_RACE_DONE paper_fresh2.log 2>/dev/null && { sleep 900; python3 forward_proof.py fresh2 > fp_fresh2.txt 2>&1; echo "CONT: final $(date -u)"; break; }
  sleep 7200
done
