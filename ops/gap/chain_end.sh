#!/bin/bash
while pgrep -f chain_ck2.sh >/dev/null; do sleep 3; done
while pgrep -x feed_race2 >/dev/null; do sleep 2; done
UDP_PIN_CPU=3 UDP_BUSY_POLL=1 /root/gap/paper_feed.sh pf1 11
