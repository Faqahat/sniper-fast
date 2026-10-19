#!/bin/bash
while pgrep -x feed_race >/dev/null; do sleep 2; done
BIN=/root/gap/bin/feed_race2 /root/gap/feed_race.sh 12 ck2a > /root/gap/race/ck2a.out 2>&1
BIN=/root/gap/bin/feed_race2 CFG=/root/gap/feed_race_busy.toml /root/gap/feed_race.sh 12 ck2b > /root/gap/race/ck2b.out 2>&1
BIN=/root/gap/bin/feed_race2 /root/gap/feed_race.sh 40 ck3 > /root/gap/race/ck3.out 2>&1
