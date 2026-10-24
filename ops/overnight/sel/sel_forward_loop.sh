#!/bin/bash
# forward test of IMIT1 every 60 min while the new collector run is going (ends ~19:26 PKT 10-24 + 1 h tail) -> sel_forward.log
cd /home/moiz/sniper/ops/overnight/sel
echo $$ > sel_forward_loop.pid
for i in $(seq 1 27); do
  echo "########## $(TZ=Asia/Karachi date '+%m-%d %H:%M') PKT forward run $i" >> sel_forward.log
  timeout 3000 ./sel_forward.sh >> sel_forward.log 2>&1
  sleep 3600
done
