#!/bin/bash
# FRONT steps 2b + 5c in ONE pass over each raw chunk (decompress once, 2 workers):
#  (2b) target lines by '{"s":SLOT,"i":IDX,' prefix  -> sniper-data/haqq_dissect/front/raw/<chunk>.jsonl   (S + control)
#  (5c) every tx touching a paying dump's mint in [dump-2, dump+1] -> sniper-data/haqq_dissect/front/win/<chunk>.jsonl.gz
PAT=/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/hd_front/pat
W=/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/hd_front/win
O1=/home/moiz/sniper-data/haqq_dissect/front/raw
O2=/home/moiz/sniper-data/haqq_dissect/front/win
FLT=/home/moiz/sniper/ops/strategies/haqq_dissect/front/f5_filter.py
mkdir -p "$O1" "$O2"
one() {
  b="$1"; run=${b%%__*}; ch=${b#*__}
  f=/home/moiz/sniper-data/collect/$run/txs/$ch.jsonl.gz
  [ -f "$f" ] || { echo "missing $f"; return 0; }
  need1=0; need2=0
  [ -f "$PAT/$b.pat" ] && [ ! -s "$O1/$b.jsonl" ] && need1=1
  [ -f "$W/$b.mints" ] && [ ! -s "$O2/$b.jsonl.gz" ] && need2=1
  SED='s/,"ev":\[[^]]*\]//; s/,"tb":\[\[.*\]\],"sd"/,"sd"/; s/,"sd":\[\[[^]]*(\],\[[^]]*)*\]\]//'
  if [ $need1 = 1 ] && [ $need2 = 1 ]; then
    zcat "$f" 2>/dev/null | tee >(/usr/bin/grep -F -f "$PAT/$b.pat" | sed -E "$SED" > "$O1/$b.jsonl.tmp") | /usr/bin/grep -F -f "$W/$b.mints" | python3 -I "$FLT" "$W/$b.json" | gzip -1 > "$O2/$b.jsonl.gz.tmp"
    sleep 0.2; mv "$O1/$b.jsonl.tmp" "$O1/$b.jsonl"; mv "$O2/$b.jsonl.gz.tmp" "$O2/$b.jsonl.gz"
  elif [ $need1 = 1 ]; then
    zcat "$f" 2>/dev/null | /usr/bin/grep -F -f "$PAT/$b.pat" | sed -E "$SED" > "$O1/$b.jsonl.tmp" && mv "$O1/$b.jsonl.tmp" "$O1/$b.jsonl"
  elif [ $need2 = 1 ]; then
    zcat "$f" 2>/dev/null | /usr/bin/grep -F -f "$W/$b.mints" | python3 -I "$FLT" "$W/$b.json" | gzip -1 > "$O2/$b.jsonl.gz.tmp" && mv "$O2/$b.jsonl.gz.tmp" "$O2/$b.jsonl.gz"
  fi
}
export -f one; export PAT W O1 O2 FLT
( ls "$PAT" | sed 's/\.pat$//'; ls "$W" | grep '\.mints$' | sed 's/\.mints$//' ) | sort -u | xargs -P 2 -I{} bash -c 'one {}'
echo done
