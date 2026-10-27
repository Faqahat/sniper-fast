#!/bin/bash
# Overlap test "E" (coordinator OK 10-27 ~16:55 PKT): SAMPLED side-by-side recording on SHYFT only.
# The host fetches every 6th slot (~0.78 getBlock/s + getSlot every 30 s; hard cap 0.95 req/s, so <= 1 call in any
# 1-second window), saves the raw blocks for the exact replay comparison, and stops by itself after 6 h. guard.py
# watches FRA's counters read-only every 3 min and stops it at once on any FRA SHYFT 429, a rising ck share, a host
# limit error or a growing host lag. No Constant-K, no RMR. Data: /home/moiz/sniper-data/rec/overlap/E1 (not a day dir).
# Usage: overlap_e.sh start | stop | status
set -u
R=/home/moiz/sniper-data/rec/overlap/E1; H=/home/moiz/sniper/ops/rec
case "${1:-status}" in
start)
  [ -e "$R/HOLD" ] && { echo "HOLD present in $R: $(cat $R/HOLD)"; exit 1; }
  mkdir -p "$R/logs" "$R/state" "$R/raw"
  stop_at=$(( $(date +%s) + 6 * 3600 ))
  sudo systemd-run --unit=sniper-rec-e1-guard --uid=moiz --gid=moiz -p WorkingDirectory=/home/moiz \
    -E REC_ROOT=$R -E GUARD_MAX_H=6 -E GUARD_EVERY=180 python3 -I $H/guard.py
  sleep 20   # the guard takes its FRA baseline first
  sudo systemd-run --unit=sniper-rec-e1 --uid=moiz --gid=moiz -p WorkingDirectory=/home/moiz -p Nice=5 \
    -p EnvironmentFile=/etc/sniper-rec/env \
    -E REC_MODE=overlap -E REC_ROOT=$R -E REC_SAMPLE_EVERY=6 -E REC_SAVE_RAW=$R/raw \
    -E REC_EP_TOTAL_RPS=0.95 -E REC_BLOCK_RPS=0.95 -E REC_RPC_RPS=0.95 -E REC_SLOT_EVERY=30 -E REC_FETCH_THREADS=2 \
    -E REC_STOP_AT=$stop_at python3 -I $H/recorder.py
  echo "started; stops by itself at $(TZ=Asia/Karachi date -d @$stop_at '+%F %T PKT')" ;;
stop)
  [ -e "$R/HOLD" ] || python3 -c "import json,time; json.dump(dict(reason='stopped by hand (overlap_e.sh stop)', by='agent', t=time.time()), open('$R/HOLD','w'))"
  sudo systemctl stop sniper-rec-e1.service sniper-rec-e1-guard.service ;;
status)
  systemctl is-active sniper-rec-e1.service sniper-rec-e1-guard.service; tail -3 $R/logs/guard.log 2>/dev/null; tail -3 $R/logs/recorder.log 2>/dev/null
  [ -e "$R/HOLD" ] && echo "HOLD: $(cat $R/HOLD)" ;;
esac
