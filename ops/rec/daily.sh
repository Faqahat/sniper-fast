#!/bin/bash
# sniper-rec daily maintenance (sniper-rec-daily.timer, 01:30 PKT): catalog (rec days + old FRA runs), slim extract of
# yesterday, archive (only when the remote is configured), compat links. Log: $REC_ROOT/logs/daily.log
set -u
H=/home/moiz/sniper/ops/rec; L=${REC_ROOT:-/home/moiz/sniper-data/rec}/logs/daily.log
exec >> "$L" 2>&1
echo "== $(TZ=Asia/Karachi date '+%F %T PKT') daily"
y=$(TZ=Asia/Karachi date -d yesterday +%F)
python3 -I $H/rec.py catalog --all
if python3 -I $H/rec.py path "$y" > /dev/null 2>&1; then python3 -I $H/rec.py slim "$y" || echo "slim $y failed"; fi
if [ -n "${FTP_HOST:-}" ] || [ "${REC_REMOTE:-ftp}" != "ftp" ]; then
  python3 -I $H/rec.py archive || echo "archive reported failures (watchdog alerts)"
else
  echo "archive: remote not configured yet (FTP_HOST empty)"
fi
python3 -I $H/rec.py link
python3 -I $H/rec.py catalog
echo "== done $(TZ=Asia/Karachi date '+%T PKT')"
