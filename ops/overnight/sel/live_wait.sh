#!/bin/bash
# wait for new live paper trades after line OFFSET, collect a batch for up to BATCH seconds, then print them (for the chat)
OFF=$1; BATCH=${2:-240}; F=/home/moiz/sniper/ops/overnight/sel/live_trades.jsonl
while [ "$(wc -l < $F 2>/dev/null || echo 0)" -le "$OFF" ]; do sleep 20; done
sleep $BATCH
N=$(wc -l < $F); echo "NEXT_OFFSET=$N"
python3 -I /home/moiz/sniper/ops/overnight/sel/live_post.py $OFF
