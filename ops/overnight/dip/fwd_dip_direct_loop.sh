#!/bin/bash
# hourly-ish forward test of the frozen DIP2 models split into direct vs routed triggers (read-only) -> dip/fwd_dip_direct.log
cd /home/moiz/sniper/ops/overnight/dip
while true; do
  sleep 2700
  timeout 2400 python3 -I dipfwd_direct.py 2>&1 | grep -v -i warn >> fwd_dip_direct.log
done
