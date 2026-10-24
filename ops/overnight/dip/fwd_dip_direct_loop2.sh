#!/bin/bash
# every ~45 min: forward test of the frozen DIP2 / DIP2R models split into direct vs routed triggers (read-only), WITH the real
# slippage limits of the picks' followers decoded first (read-only RPC; estimated limits flatter routed picks) -> dip/fwd_dip_direct.log
cd /home/moiz/sniper/ops/overnight/dip
while true; do
  rm -f fwd_direct_dump_tmp.jsonl
  DUMP=fwd_direct_dump_tmp.jsonl timeout 2400 python3 -I dipfwd_direct.py > /dev/null 2>&1
  if [ -s fwd_direct_dump_tmp.jsonl ]; then
    WIN=3 timeout 1800 python3 -I follower_sigs2.py fwd_direct_dump_tmp.jsonl > /dev/null 2>&1
    (cd ../core && timeout 1800 python3 -I slip_fetch.py ../dip/follower_sigs2.json > /dev/null 2>&1)
  fi
  timeout 2400 python3 -I dipfwd_direct.py 2>&1 | grep -v -i warn >> fwd_dip_direct.log
  sleep 2700
done
