#!/bin/bash
# Every 10 min: compare 4yFAz's new landed buys (since paper start) vs what our paper run tracked. Append summary.
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-fast
set -a; . /root/arbx/deploy/.env; set +a
while true; do
  python3 -I /root/xref2.py >> /root/xref_log.txt 2>&1
  echo "----- $(date -u +%H:%M:%S)UTC -----" >> /root/xref_log.txt
  sleep 600
done
