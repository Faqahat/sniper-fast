#!/bin/sh
# one raw file -> lines touching the group wallets (separate output per input file)
f="$1"; run=$(basename $(dirname $(dirname "$f"))); b=$(basename "$f" .jsonl.gz)
zcat "$f" 2>/dev/null | grep -F -f /home/moiz/sniper/ops/overnight/minhold/g3/grp.txt > /home/moiz/sniper/ops/overnight/minhold/g3/p1/${run}_${b}.jsonl
