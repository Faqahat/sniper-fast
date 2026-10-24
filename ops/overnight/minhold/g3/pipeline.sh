#!/bin/sh
cd /home/moiz/sniper/ops/overnight/minhold/g3
until grep -q PASS1DONE pass1.log 2>/dev/null; do sleep 10; done
python3 -I mints.py
mkdir -p p2
xargs -P 8 -n 1 ./two.sh < files.txt
echo PASS2DONE
