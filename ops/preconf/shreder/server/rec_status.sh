#!/bin/bash
# FRA (root): one-screen status of the recorder run + host health.
# usage: sudo /root/shreder/rec_status.sh RUN
RUN=${1:?RUN name}; OUT=${SHREDER_BASE:-/root/shreder}/data/$RUN
P=$(cat "$OUT/rec.pid" 2>/dev/null)
if [ -n "$P" ] && [ "$P" -gt 1 ] 2>/dev/null && grep -q shreder_rec "/proc/$P/cmdline" 2>/dev/null; then ps -o pid=,pcpu=,rss=,etime=,ni= -p "$P" | awk '{printf "recorder: RUNNING pid %s cpu(avg) %s%% rss %.0f MB elapsed %s nice %s\n",$1,$2,$3/1024,$4,$5}'; else echo "recorder: NOT running"; fi
L=$(grep -v 'subscribed\|first message' "$OUT/rec.log" 2>/dev/null | grep ' | cpu ' | tail -1)
[ -n "$L" ] && echo "$L" | sed 's/ | /\n  /g'
grep -E 'refused|error|FALLBACK|PAUSED|stall|ended' "$OUT/rec.log" 2>/dev/null | tail -3 | cut -c1-220 | sed 's/^/  last issue: /'
du -sh "$OUT" 2>/dev/null | awk '{print "data: "$1}'
df -h / | awk 'NR==2{print "disk: "$5" used, "$4" free"}'
python3 - <<'PY' 2>/dev/null
import json,time
try:
    r=open('/root/sniper-collect/current_run').read().strip(); s=json.load(open(f'/root/sniper-collect/{r}/status.json'))
    print(f"collector: lag_slots {s.get('lag_slots')} block_age {s.get('now',0)-s.get('last_block_time',0):.0f} s status_age {time.time()-s.get('now',0):.0f} s")
except Exception as e: print('collector: status unreadable', type(e).__name__)
PY
uptime | sed 's/.*load average/load average/'
