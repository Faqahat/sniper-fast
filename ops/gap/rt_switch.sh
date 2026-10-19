#!/bin/bash
# at T+20 min of ck3: give the harness UDP receive thread SCHED_FIFO 10 (A/B within one run)
sleep 1200
P=$(pgrep -x feed_race2); T=$(grep -l udp-constantk /proc/$P/task/*/comm | cut -d/ -f5)
chrt -f -p 10 $T && echo "RT_ON $(date +%s%N) tid=$T $(chrt -p $T | tr "\n" " ")" > /root/gap/race/ck3_rt.txt
