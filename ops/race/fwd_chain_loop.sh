#!/bin/bash
# READ-ONLY: every 10 min, fetch block S + S+1..S+8 for every new RACE seen launch of the forward paper run.
set -a; . /root/sniper/deploy/.env; set +a
export NOB_RPS=5
cd /root/race
while true; do
  python3 onchain.py /root/race/fwd_onchain.jsonl 3 /root/race/paper_fwd.log >> /root/race/fwd_onchain.log 2>&1
  grep -q PAPER_RACE_DONE /root/race/paper_fwd.log && { python3 onchain.py /root/race/fwd_onchain.jsonl 3 /root/race/paper_fwd.log >> /root/race/fwd_onchain.log 2>&1; echo LOOP_DONE >> /root/race/fwd_onchain.log; break; }
  sleep 600
done
