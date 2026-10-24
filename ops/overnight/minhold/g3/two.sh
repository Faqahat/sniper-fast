#!/bin/sh
f="$1"; run=$(basename $(dirname $(dirname "$f"))); b=$(basename "$f" .jsonl.gz)
zcat "$f" 2>/dev/null | grep -F -f /home/moiz/sniper/ops/overnight/minhold/g3/mints.txt > /home/moiz/sniper/ops/overnight/minhold/g3/p2/${run}_${b}.jsonl
