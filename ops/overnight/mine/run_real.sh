#!/bin/sh
cd /home/moiz/sniper/ops/overnight/mine
until grep -q "^done" labels_real.log 2>/dev/null; do sleep 20; done
for a in "10 1" "20 1" "35 1" "50 1" "75 1" "10 3" "20 3" "35 3"; do
  set -- $a
  timeout 7200 python3 -u -I fit_real.py $1 $2 > fr_$1_$2.txt 2>&1 &
done
wait
echo FRDONE > fr_done.flag
