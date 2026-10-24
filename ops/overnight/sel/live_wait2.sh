#!/bin/bash
# wait for new live paper trades after line OFFSET (batch for up to BATCH s), then print them for the chat. Also a watchdog:
# if the live loop died (it did once, 00:11 PKT 10-24), restart it detached.
OFF=$1; BATCH=${2:-240}; D=/home/moiz/sniper/ops/overnight/sel; F=$D/live_trades.jsonl
alive() { kill -0 "$(cat $D/live_loop.pid 2>/dev/null)" 2>/dev/null; }
restart() { (cd $D && setsid nohup ./live_loop.sh > /dev/null 2>&1 < /dev/null &); echo "WATCHDOG: live loop restarted $(TZ=Asia/Karachi date +%H:%M) PKT" >> $D/live.log; }
while [ "$(wc -l < $F 2>/dev/null || echo 0)" -le "$OFF" ]; do alive || restart; sleep 20; done
end=$(( $(date +%s) + BATCH )); while [ "$(date +%s)" -lt "$end" ]; do alive || restart; sleep 20; done
N=$(wc -l < $F); echo "NEXT_OFFSET=$N"
python3 -I $D/live_post.py $OFF
