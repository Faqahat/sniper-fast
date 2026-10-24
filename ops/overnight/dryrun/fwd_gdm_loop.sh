#!/bin/bash
# hourly GDM forward test (read-only; gdm/fwd/fwd_gdm.sh has its own lock and waits for a busy dry-run cycle)
while true; do
  echo "=== $(TZ=Asia/Karachi date '+%F %H:%M PKT')" >> /home/moiz/sniper/ops/overnight/dryrun/fwd_gdm_loop.log
  timeout 1800 bash /home/moiz/sniper/ops/overnight/gdm/fwd/fwd_gdm.sh >> /home/moiz/sniper/ops/overnight/dryrun/fwd_gdm_loop.log 2>&1
  sleep 3600
done
