#!/bin/bash
# READ-ONLY: every 5 min, fetch block S + S+1..S+8 for every new RACE seen launch of paper run <tag>; final pass at the end.
TAG=$1
set -a; . /root/sniper/deploy/.env; set +a
export NOB_RPS=${NOB_RPS:-8}
cd /root/race
while true; do
  python3 onchain.py /root/race/${TAG}_onchain.jsonl 4 /root/race/paper_${TAG}.log >> /root/race/${TAG}_onchain.log 2>&1
  grep -q PAPER_RACE_DONE /root/race/paper_${TAG}.log && { python3 onchain.py /root/race/${TAG}_onchain.jsonl 4 /root/race/paper_${TAG}.log >> /root/race/${TAG}_onchain.log 2>&1; echo LOOP_DONE >> /root/race/${TAG}_onchain.log; break; }
  sleep 300
done
