#!/bin/sh
cd /home/moiz/sniper/ops/overnight/mine
for a in "20 1" "20 3" "35 1" "35 3" "75 1" "75 3"; do
  set -- $a
  timeout 7200 python3 -u -I fit_speed.py $1 $2 > fs_$1_$2.txt 2>&1 &
done
wait
echo FSDONE > fs_done.flag
