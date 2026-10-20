#!/bin/bash
# Hourly: A/B filter comparison (ab.py) + his-vs-ours coverage (xref2.py), appended with a timestamp.
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
set -a; . /root/sniper/deploy/.env; set +a
while true; do
  echo "================ SEGMENT $(date -u +%H:%M)UTC ================" >> /root/segment_log.txt
  python3 -I /root/ab.py >> /root/segment_log.txt 2>&1
  echo "--- his vs ours ---" >> /root/segment_log.txt
  timeout 150 python3 -I /root/xref2.py >> /root/segment_log.txt 2>&1
  echo "" >> /root/segment_log.txt
  sleep 3600
done
