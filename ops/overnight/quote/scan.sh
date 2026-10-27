#!/bin/sh
f="$1"; run=$(basename $(dirname $(dirname "$f"))); b=$(basename "$f" .jsonl.gz)
zcat "$f" 2>/dev/null | grep -F -f /home/moiz/sniper/ops/overnight/quote/qmints.txt > /home/moiz/sniper/ops/overnight/quote/raw/${run}_${b}.jsonl
