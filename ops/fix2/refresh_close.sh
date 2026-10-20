#!/bin/bash
# ZERO COST: re-measure the close-leader list from THIS server (ICMP to current + next epoch leaders, close5_new.py)
# and replace /root/fix2/close_leaders_5ms.txt only if the new list looks sane (>= 150 leaders). Cron: every 6 h,
# so a new epoch's leaders and moved validators are picked up. Old list kept as close_leaders_5ms.prev.txt.
set -a; . /root/sniper/deploy/.env; set +a
cd /root/fix2 || exit 1
timeout 300 python3 close5_new.py > /root/fix2/refresh_close.out 2>&1 || { echo "$(date -u +%FT%TZ) FAIL measure" >> refresh_close.log; exit 1; }
n=$(grep -c . close_leaders_5ms_new.txt)
if [ "$n" -ge 150 ]; then
  cp -p close_leaders_5ms.txt close_leaders_5ms.prev.txt
  cp -p close_leaders_5ms_new.txt close_leaders_5ms.txt
  echo "$(date -u +%FT%TZ) OK $n leaders $(grep 'slot share covered' refresh_close.out)" >> refresh_close.log
else
  echo "$(date -u +%FT%TZ) SKIP only $n leaders (kept old list)" >> refresh_close.log
fi
