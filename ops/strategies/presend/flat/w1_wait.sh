#!/bin/bash
# FLAT study: background waiter (read-only). Exits when AMS r28 has ended (both "END CHECK" lines in its log, read with
# `sudo grep -c`) AND the local copy of FRA's chain recording has caught up (status.json last_block_time >= end + 900 s), then
# waits 150 s more (so the last chunk copies are > 2 min old). Hard stop at 10-28 09:00 PKT. Log: presend_flat/w1_wait.log
LOG=/home/moiz/sniper-data/presend_flat/w1_wait.log
ST=/home/moiz/sniper-data/collect/run_20261027_1410/status.json
DEADLINE=1793160000            # 10-28 09:00 PKT
END=""
while true; do
  now=$(date +%s)
  n=$(timeout 60 ssh -p 1996 -o ConnectTimeout=20 -o BatchMode=yes it@84.32.104.202 'sudo grep -c "END CHECK" /root/prod/runs/dip_ams_r28.log' 2>/dev/null)
  lbt=$(python3 -c "import json,sys; print(int(json.load(open(sys.argv[1])).get('last_block_time') or 0))" "$ST" 2>/dev/null || echo 0)
  if [ "${n:-0}" -ge 2 ] && [ -z "$END" ]; then END=$now; echo "$(date -u +%FT%TZ) END CHECK seen (count $n); end ~ $END" >> $LOG; fi
  echo "$(date -u +%FT%TZ) endcheck=${n:-?} last_block_time=$lbt end=${END:-none}" >> $LOG
  if [ -n "$END" ] && [ "$lbt" -ge $((END + 900)) ]; then
    sleep 150
    echo "READY end=$END last_block_time=$lbt hi=$((END + 300))" | tee -a $LOG
    exit 0
  fi
  if [ "$now" -ge "$DEADLINE" ]; then echo "TIMEOUT (no END CHECK / recording behind) end=${END:-none} lbt=$lbt" | tee -a $LOG; exit 2; fi
  sleep 300
done
