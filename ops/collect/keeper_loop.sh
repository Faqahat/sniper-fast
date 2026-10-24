#!/bin/bash
# runs keeper.sh every 10 min (start: setsid nohup bash /home/moiz/sniper/ops/collect/keeper_loop.sh > /dev/null 2>&1 &)
echo $$ > /home/moiz/sniper-data/collect/keeper_loop.pid
while true; do
  timeout 3000 bash /home/moiz/sniper/ops/collect/keeper.sh
  sleep 600
done
