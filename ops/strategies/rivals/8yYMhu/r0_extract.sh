#!/bin/bash
# 8yYMhu step 0 (read-only on recordings): every recorded line mentioning the wallet, one output file per input file (resumable).
# Usage: r0_extract.sh [parallel=3]
W=8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3
OUT=/home/moiz/sniper-data/rivals/8yYMhu/ext
mkdir -p $OUT
P=${1:-3}
ls /home/moiz/sniper-data/collect/run_202610{24,25,26,27,28}_*/txs/*.jsonl.gz | while read f; do
  r=$(basename $(dirname $(dirname $f))); b=$(basename $f .jsonl.gz)
  [ -e $OUT/${r}__${b}.done ] || echo "$f"
done | xargs -P $P -I{} bash -c '
  f={}; r=$(basename $(dirname $(dirname $f))); b=$(basename $f .jsonl.gz)
  if gzip -dc "$f" 2>/dev/null | grep -F '"$W"' > '"$OUT"'/${r}__${b}.jsonl; then :; fi
  gzip -t "$f" 2>/dev/null && touch '"$OUT"'/${r}__${b}.done || echo "TRUNC $f"
'
echo ALLDONE
