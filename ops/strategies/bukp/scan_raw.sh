#!/bin/bash
# Raw scan (read-only): every recorded tx line mentioning BUkpShoE (as signer or account) from R1-R4 raw chunks.
# usage: scan_raw.sh <out dir>   (6 parallel workers)
W=BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP
OUT=$1
for run in run_20261021_2207 run_20261022_1543 run_20261023_1426 run_20261024_1425; do
  ls /home/moiz/sniper-data/collect/$run/txs/*.jsonl.gz
done | xargs -P 6 -I{} sh -c 'f={}; b=$(basename $f .jsonl.gz); r=$(basename $(dirname $(dirname $f))); zcat "$f" 2>/dev/null | LC_ALL=C grep -F "'$W'" > "'$OUT'/${r}__${b}.jsonl" || true'
echo SCAN_DONE
