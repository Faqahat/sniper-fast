#!/bin/bash
# FRONT addendum (read-only): raw lines for FRA r27's armed mints after the dv8 tape end (slot > 462200814), plus per-slot max tx index.
S=/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/hd_front/r27
O=/home/moiz/sniper-data/haqq_dissect/front/r27
for f in $(ls /home/moiz/sniper-data/collect/run_20261027_1410/txs/ | awk -F'[_.]' '$2>1793131532'); do
  b=${f%.jsonl.gz}; [ -s $O/$b.mint.jsonl ] && continue
  zcat /home/moiz/sniper-data/collect/run_20261027_1410/txs/$f | tee >(/usr/bin/grep -o '^{"s":[0-9]*,"i":[0-9]*' > $O/$b.si.tmp) | /usr/bin/grep -F -f $S/mints.txt > $O/$b.mint.tmp
  sleep 0.2; mv $O/$b.si.tmp $O/$b.si; mv $O/$b.mint.tmp $O/$b.mint.jsonl
done
echo done
