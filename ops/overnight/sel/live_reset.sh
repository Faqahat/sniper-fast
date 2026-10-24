#!/bin/bash
# rebuild the live paper backlog (since the new run started) with the current live_sim.py, then restart the live loop
cd /home/moiz/sniper/ops/overnight/sel
/home/moiz/sniper-data/work/sync_r3.sh > /dev/null 2>&1
rm -f live_trades.jsonl live_seen.json
RP_PHASEA_R3=phaseA_r3 SINCE_PKT="10-23 19:26" timeout 1800 python3 -I live_sim.py 2>&1 | tail -1
wc -l < live_trades.jsonl
rm -rf /home/moiz/sniper-data/collect/phaseA_r3live
setsid nohup ./live_loop.sh > /dev/null 2>&1 < /dev/null &
sleep 2; echo "loop pid $(cat live_loop.pid)"
