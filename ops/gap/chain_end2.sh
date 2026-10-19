#!/bin/bash
while pgrep -f chain_ck2.sh >/dev/null; do sleep 3; done
while pgrep -x feed_race2 >/dev/null; do sleep 2; done
/root/gap/paper_feed.sh pf1 11
