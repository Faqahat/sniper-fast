#!/bin/bash
# hourly forward test of the frozen generic / become-them strategies (read-only); results appended to fwd_loop.log
cd /home/moiz/sniper/ops/overnight/core
while true; do
  for i in 1 2 3 4 5 6; do
    if ! ps -eo args | grep -E 'a_extract|cycle.sh' | grep -v grep > /dev/null; then break; fi
    sleep 120
  done
  echo "=== $(TZ=Asia/Karachi date '+%F %H:%M PKT')" >> ../dryrun/fwd_loop.log
  timeout 2400 python3 -I fwd_generic.py >> ../dryrun/fwd_loop.log 2>&1
  sleep 3600
done
