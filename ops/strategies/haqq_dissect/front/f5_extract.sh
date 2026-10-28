#!/bin/bash
# FRONT step 5c (read-only): every tx touching a paying dump's mint in slots [dump-2, dump+1] (landed and failed), 2 workers.
# Out: sniper-data/haqq_dissect/front/win/<chunk>.jsonl.gz
W=/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/hd_front/win
OUT=/home/moiz/sniper-data/haqq_dissect/front/win
FLT=/home/moiz/sniper/ops/strategies/haqq_dissect/front/f5_filter.py
mkdir -p "$OUT"
one() {
  p="$1"; b=$(basename "$p" .mints); run=${b%%__*}; ch=${b#*__}
  f=/home/moiz/sniper-data/collect/$run/txs/$ch.jsonl.gz
  [ -s "$OUT/$b.jsonl.gz" ] && return 0
  [ -f "$f" ] || { echo "missing $f"; return 0; }
  zcat "$f" 2>/dev/null | /usr/bin/grep -F -f "$p" | python3 -I "$FLT" "$W/$b.json" | gzip -1 > "$OUT/$b.jsonl.gz.tmp" && mv "$OUT/$b.jsonl.gz.tmp" "$OUT/$b.jsonl.gz"
}
export -f one; export OUT W FLT
ls "$W"/*.mints | xargs -P 2 -I{} bash -c 'one {}'
echo done
