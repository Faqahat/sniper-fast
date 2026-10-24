#!/bin/bash
# hourly forward test of the frozen dip-buy models (read-only); results appended to dip/fwd_dip.log
cd /home/moiz/sniper/ops/overnight/dip
while true; do
  for i in 1 2 3 4 5 6; do
    if ! ps -eo args | grep -E 'a_extract|cycle.sh' | grep -v grep > /dev/null; then break; fi
    sleep 120
  done
  echo "=== $(TZ=Asia/Karachi date '+%F %H:%M PKT')" >> fwd_dip.log
  timeout 2400 python3 -I dipfwd.py >> fwd_dip.log 2>&1
  sleep 3000
done
