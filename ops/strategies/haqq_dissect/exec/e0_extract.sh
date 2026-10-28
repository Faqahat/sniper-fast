#!/bin/bash
# Extract haqq + our wallets' txs (landed AND failed) from every raw-recording chunk. Read-only. One output file per chunk.
# Usage: e0_extract.sh  (3 parallel zcat|grep)
OUT=/home/moiz/sniper-data/haqq_dissect/exec/ext
now=$(date +%s)
for r in /home/moiz/sniper-data/collect/run_2026*/; do
  [ -d "$r/txs" ] || continue
  rn=$(basename $r)
  for f in $r/txs/txs_*.jsonl.gz; do
    m=$(stat -c %Y "$f"); [ $((now-m)) -lt 240 ] && continue
    o=$OUT/${rn}__$(basename $f .jsonl.gz).jsonl
    [ -s "$o.done" ] && continue
    echo "$f $o"
  done
done | xargs -P 3 -n 2 sh -c 'zcat "$0" 2>/dev/null | grep -F -e haqqiUUXB5gp7 -e 2g7rYv7yCQuNsx -e EgxfYgEbruk94 > "$1"; echo ok > "$1.done"'
echo DONE
