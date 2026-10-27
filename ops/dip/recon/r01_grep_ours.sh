#!/bin/bash
# r01: grep every recording chunk for our two wallets (FRA 2g7rYv7y..., AMS EgxfYgEb...) -> one file per chunk (read-only on the recording)
# usage: r01_grep_ours.sh <run dir> <min chunk ts> <out dir>
RUN=$1; MIN=$2; OUT=$3
mkdir -p $OUT
ls $RUN/txs/txs_*.jsonl.gz | while read f; do
  ts=$(basename $f | sed 's/txs_\([0-9]*\).*/\1/'); [ $ts -ge $MIN ] && echo $f
done | nice -n 10 xargs -P 3 -I{} sh -c 'b=$(basename {} .jsonl.gz); zcat {} 2>/dev/null | grep -F -e 2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE -e EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR > '$OUT'/$b.ours.jsonl; true'
echo DONE
