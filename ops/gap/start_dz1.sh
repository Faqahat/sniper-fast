#!/bin/bash
# wait for the ck3 wrapper (and its chain) to finish writing its summary, then start the DZ race
while pgrep -x feed_race2 >/dev/null; do sleep 1; done
for i in $(seq 1 120); do [ -s /root/gap/race/summary_ck3.txt ] && break; sleep 1; done
BIN=/root/gap/bin/feed_race3 /root/gap/feed_race.sh 45 dz1 > /root/gap/race/dz1.out 2>&1
