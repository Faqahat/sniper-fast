#!/bin/bash
# NEAR-LIVE paper run: every ~2 min copy the newest collector data (read-only) and paper-trade new picks -> live_trades.jsonl
cd /home/moiz/sniper/ops/overnight/sel
echo $$ > live_loop.pid
while true; do
  /home/moiz/sniper-data/work/sync_live.sh >> live.log 2>&1 || echo "sync failed $(date -u +%H:%M)" >> live.log
  RP_PHASEA_R3=phaseA_r3live timeout 600 python3 -I live_sim.py >> live.log 2>&1
  sleep 90
done
