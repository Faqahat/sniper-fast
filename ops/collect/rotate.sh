#!/bin/bash
# Raw recorder rotation on the server (owner OK 10-24 06:50 PKT: "record all the runs raw ... so we can do this daily while
# tuning the bot"). Cron every 5 min (root): when the current 24 h collector window ends within 6 min, start the NEXT run so
# consecutive runs overlap (the old run's tail keeps following its own tokens for TAIL_MIN more minutes; the new run records
# every create from its start: no gap like 10-23 18:33-19:26). If no collector runs at all (crash, reboot), start one now.
# Timezone-free (the window times come from run.json; the server clock is Europe/Vilnius with DST).
# Read-only collector (no wallet, no sends). Off switch: touch /root/sniper-collect/ROTATE_OFF.
# Install: /root/sniper-collect/rotate.sh;  crontab: */5 * * * * /root/sniper-collect/rotate.sh >> /root/sniper-collect/rotate.log 2>&1
set -u
cd /root/sniper-collect || exit 1
[ -e ROTATE_OFF ] && exit 0
now=$(date +%s)
log() { echo "$(date -u +%FT%TZ) $*"; }
start_run() {
  local R=run_$(date -u +%Y%m%d_%H%M)
  [ -e "$R" ] && { log "refused: $R exists"; return 1; }
  local free; free=$(df --output=avail -B1G /root | tail -1 | tr -d ' ')
  if [ "$free" -lt 18 ]; then log "refused: only ${free} GB free (a day needs ~17 GB; the host keeper deletes copied runs)"; return 1; fi
  if [ -n "${DRY:-}" ]; then log "DRY: would start $R ($1); ${free} GB free"; return 0; fi
  echo "$R" > current_run
  ( set -a; . /root/sniper/deploy/.env; set +a
    OUT=/root/sniper-collect/$R HOURS=24 TAIL_MIN=20 BLOCK_RPS=6 FETCH_THREADS=10 ENRICH_WORKERS=4 RPS=20 setsid nohup python3 -I collect.py > $R.log 2>&1 < /dev/null & )
  log "started $R ($1); ${free} GB free"
}
ncol=$(pgrep -fc "^python3 -I collect.py$" || true)
cur=$(cat current_run 2>/dev/null || true)
wend=$(python3 -c "import json,sys; print(int(json.load(open(sys.argv[1]))['window_end_time']))" "$cur/run.json" 2>/dev/null || echo 0)
if [ "${ncol:-0}" -eq 0 ]; then
  start_run "no collector was running (current_run=$cur)"
elif [ "$wend" -gt 0 ] && [ "$now" -ge $(( wend - 360 )) ]; then
  if [ "${ncol:-0}" -ge 2 ]; then log "refused: $ncol collectors already running"; exit 0; fi
  start_run "window of $cur ends $(( wend - now )) s from now"
fi
