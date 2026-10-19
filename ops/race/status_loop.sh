#!/bin/bash
# refresh the NOTES.md progress line every 15 min until both overnight runs are done
while true; do
  python3 /root/race/status_update.py > /dev/null 2>&1
  grep -q PAPER_RACE_DONE /root/race/paper_night.log && grep -q PAPER_RACE_DONE /root/race/paper_mnight.log && break
  sleep 900
done
