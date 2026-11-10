#!/bin/bash
# runs keeper.sh every 10 min (start: setsid nohup bash /home/it/sniper/ops/collect/keeper_loop.sh > /dev/null 2>&1 &)
echo $$ > /data/tapes/collect/keeper_loop.pid
while true; do
  timeout 3000 bash /home/it/sniper/ops/collect/keeper.sh
  sleep 600
done
