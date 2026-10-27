#!/bin/sh
# text screenshots for ops/tui/screens (dipmon --screens renders each tab off-screen at a size; no terminal needed)
#   live/   AMS r26's records replayed to 60% of the run (RUNNING look; real data), every tab + help + a trade's details
#   ended/  AMS r26 finished (the final banner, END CHECK), overview + pre-send
#   quiet/  QUIET demo: r26's records + synthetic dip20 QUIET lines (the engine's formats), 10% into the run = warm-up
set -e
cd "$(dirname "$0")/.."
SRC=${SRC:-/home/moiz/sniper-data/runs/ams/runs/dip_ams_r26.jsonl}
OUT=screens
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
rm -rf "$OUT"/live "$OUT"/ended "$OUT"/quiet
T=$(python3 tests/replay.py "$SRC" "$TMP/live" --until-frac 0.6 --quiet | sed -n 's/^T_CUT=//p')
NOW=$(python3 -c "print(int(float('$T'))/1e9)")
python3 dipmon.py --file "$TMP/live/dip_ams_r26.jsonl" --usd 100 --strict --assume-running --now "$NOW" --screens "$OUT/live" > /dev/null
python3 dipmon.py --file "$SRC" --usd 100 --strict --screens "$OUT/ended" --screens-only overview,presend,regular > /dev/null
T=$(python3 tests/replay.py "$SRC" "$TMP/quiet" --until-frac 0.10 --dip20 --quiet | sed -n 's/^T_CUT=//p')
NOW=$(python3 -c "print(int(float('$T'))/1e9)")
python3 dipmon.py --file "$TMP/quiet/dip_ams_r26.jsonl" --usd 100 --strict --assume-running --now "$NOW" --screens "$OUT/quiet" \
  --screens-only overview,presend,config > /dev/null
ls "$OUT"/live "$OUT"/ended "$OUT"/quiet | wc -l
du -sh "$OUT"
