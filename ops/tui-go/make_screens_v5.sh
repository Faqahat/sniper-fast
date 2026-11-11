#!/bin/sh
# dipmon v5: text screenshots of the new panels (tab 9 Stats; Trades / Filters / details on dip47 runs) and --snapshot --v5 dumps
#   sh make_screens_v5.sh BIN OUTDIR TAG RUN.jsonl [extra dipmon flags...]
B=$1; O=$2/$3; F=$4; shift 4
mkdir -p "$O"
A="--file $F --usd 150 --no-usd --now 1794430000 $*"
for s in 200x60 160x50 120x40 80x30 50x30; do
  $B $A --screen $s --tab 9 > "$O/${s}_09-stats.txt"
done
$B $A --screen 200x40 --tab 4 > "$O/200x40_04-trades.txt"
$B $A --screen 200x50 --tab 8 > "$O/200x50_08-filters.txt"
$B $A --screen 160x50 --tab 4 --page detail > "$O/160x50_04-detail.txt"
$B $A --snapshot --v5 > "$O/snapshot_v5.txt"
$B $A --snapshot --json --v5 > "$O/snapshot_v5.json"
ls "$O" | wc -l
