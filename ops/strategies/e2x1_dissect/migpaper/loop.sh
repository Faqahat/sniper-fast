#!/bin/bash
# migpaper paper loop (PAPER ONLY, local only). Every 2 h: score the next 2-h window once its look-ahead is recorded,
# append out/results.jsonl + out/trades.jsonl, rebuild RUNNING.md, prune decoded chunk caches older than the look-back.
# Stop: touch STOP (same folder). Runs HOURS from START. Log: out/loop.log. Pid: out/loop.pid.
C=/home/moiz/sniper/ops/strategies/e2x1_dissect/migpaper
D=/home/moiz/sniper-data/e2x1_dissect/migpaper
START=${START:-1793214000}          # 10-29 00:00 PKT
HOURS=${HOURS:-72}
END=$((START + HOURS * 3600))
W=7200
LOOK=$((900 + 300 + 300))           # look-ahead + one chunk + keeper copy lag
LOOKBACK=$((3 * 3600))
cd "$C" || exit 1
mkdir -p "$D/out" "$D/cache"
echo $$ > "$D/out/loop.pid"
log() { echo "$(date -u +%FT%TZ) $*" >> "$D/out/loop.log"; }
next_start() { python3 -c "import json,os; f='$D/out/state.json'; print(json.load(open(f)).get('last_end', $START) if os.path.exists(f) else $START)"; }
log "loop start pid $$ START=$START END=$END"
while :; do
  [ -f STOP ] && { log "STOP file seen, exiting"; break; }
  ns=$(next_start)
  [ "$ns" -ge "$END" ] && { log "done: scored through $ns"; break; }
  now=$(date +%s)
  if [ "$now" -lt $((ns + W + LOOK)) ]; then sleep 300; continue; fi
  free=$(df --output=avail -B1G /home/moiz | tail -1 | tr -d ' ')
  if [ "$free" -lt 15 ]; then log "disk guard: ${free} GB free < 15, not scoring; sleeping 30 min"; sleep 1800; continue; fi
  fetch=""
  [ "$free" -lt 20 ] && { fetch="--no-fetch"; log "disk ${free} GB free < 20: no server fetch (local keeper copies only)"; }
  log "scoring window $ns..$((ns + W)) (free ${free} GB)"
  nice -n 10 python3 "$C/mp_score.py" --start "$ns" --end $((ns + W)) --procs 2 $fetch --label loop >> "$D/out/loop.log" 2>&1 || { log "mp_score failed for $ns (retry in 10 min)"; sleep 600; continue; }
  python3 "$C/mp_table.py" > /dev/null 2>>"$D/out/loop.log" || log "mp_table failed"
  nxt=$(next_start)
  for f in "$D"/cache/*.npz; do
    [ -e "$f" ] || continue
    t=${f##*txs_}; t=${t%.npz}
    [ "$t" -lt $((nxt - LOOKBACK - 600)) ] && rm -f "$f"
  done
  log "cache $(du -sh "$D/cache" | cut -f1), data $(du -sh "$D" | cut -f1)"
done
rm -f "$D/out/loop.pid"
