#!/bin/bash
ulimit -v 6000000
cd /tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/f3_omen4check/work
while read rd run a b; do python3 -W ignore calib.py $rd $run $a $b >> calib.log 2>&1; done < jobs.txt
echo DONE >> calib.log
