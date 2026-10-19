#!/bin/bash
# READ-ONLY: every 10 min, fetch on-chain contest/bundle records (block S + S+1) for new fired paper launches of both runs.
set -a; . /root/arbx/deploy/.env; set +a
export NOB_RPS=6
cd /root/det
while true; do
  python3 contest.py /root/det/contest.jsonl 4 /root/det/paper_B.log /root/det/paper_A.log >> /root/det/onchain_loop.log 2>&1
  if grep -q PAPER_DET_DONE /root/det/paper_B.log && grep -q PAPER_DET_DONE /root/det/paper_A.log; then
    python3 contest.py /root/det/contest.jsonl 4 /root/det/paper_B.log /root/det/paper_A.log >> /root/det/onchain_loop.log 2>&1
    echo LOOP_DONE >> /root/det/onchain_loop.log; break
  fi
  sleep 600
done
