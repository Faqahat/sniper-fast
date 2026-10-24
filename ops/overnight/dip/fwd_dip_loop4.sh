#!/bin/bash
# hourly forward test of the frozen dip models (read-only): DIP (8-slot), DIP4 (4-slot, one trade per launch per 20 slots) and
# DIP4 with one trade per launch per 5 slots; follower slippage imputed; appended to dip/fwd_dip.log
cd /home/moiz/sniper/ops/overnight/dip
while true; do
  for i in 1 2 3 4 5 6; do
    if ! ps -eo args | grep -E 'a_extract|cycle.sh' | grep -v grep > /dev/null; then break; fi
    sleep 120
  done
  echo "=== $(TZ=Asia/Karachi date '+%F %H:%M PKT') (follower slippage imputed)" >> fwd_dip.log
  SLIPIMP=1 timeout 2400 python3 -I dipfwd.py >> fwd_dip.log 2>&1
  timeout 2400 python3 -I dipfwd4.py >> fwd_dip.log 2>&1
  FWD_LABEL=" [spacing 5 slots]" DIP_BUSY=5 timeout 2400 python3 -I dipfwd4.py >> fwd_dip.log 2>&1
  sleep 2700
done
