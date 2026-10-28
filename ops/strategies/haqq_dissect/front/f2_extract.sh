#!/bin/bash
# FRONT step 2b (read-only): pull the target lines out of the raw recordings (2 parallel workers), dropping the bulky ev/tb/sd fields.
# In: scratch hd_front/pat/<run>__<chunk>.pat ; raw: sniper-data/collect/<run>/txs/<chunk>.jsonl.gz
# Out: sniper-data/haqq_dissect/front/raw/<run>__<chunk>.jsonl
PAT=/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/hd_front/pat
OUT=/home/moiz/sniper-data/haqq_dissect/front/raw
mkdir -p "$OUT"
one() {
  p="$1"; b=$(basename "$p" .pat); run=${b%%__*}; ch=${b#*__}
  f=/home/moiz/sniper-data/collect/$run/txs/$ch.jsonl.gz
  [ -s "$OUT/$b.jsonl" ] && return 0
  [ -f "$f" ] || { echo "missing $f"; return 0; }
  zcat "$f" 2>/dev/null | /usr/bin/grep -F -f "$p" | sed -E 's/,"ev":\[[^]]*\]//; s/,"tb":\[\[.*\]\],"sd"/,"sd"/; s/,"sd":\[\[[^]]*(\],\[[^]]*)*\]\]//' > "$OUT/$b.jsonl.tmp" && mv "$OUT/$b.jsonl.tmp" "$OUT/$b.jsonl"
}
export -f one; export OUT
ls "$PAT"/*.pat | xargs -P 2 -I{} bash -c 'one {}'
echo done
