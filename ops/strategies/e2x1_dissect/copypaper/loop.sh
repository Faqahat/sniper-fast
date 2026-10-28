#!/bin/bash
# copypaper paper loop (PAPER ONLY, local only). Every 2 h: score the next 2-h window once its 1800 s look-ahead is recorded,
# append out/results.jsonl + out/trades.jsonl, rebuild RUNNING.md, prune decoded chunk caches no longer needed.
# Stop: touch STOP (same folder). Runs 48 h from START. Log: out/loop.log. Pid: out/loop.pid.
C=/home/moiz/sniper/ops/strategies/e2x1_dissect/copypaper
D=/home/moiz/sniper-data/e2x1_dissect/copypaper
START=${START:-1793210400}          # 10-28 23:00 PKT
HOURS=${HOURS:-48}
END=$((START + HOURS * 3600))
W=7200
LOOK=$((1800 + 300 + 300))          # timeout + one chunk + keeper copy lag
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
  if [ "$now" -lt $((ns + W + LOOK)) ]; then
    sleep 300; continue
  fi
  free=$(df --output=avail -B1G /home/moiz | tail -1 | tr -d ' ')
  if [ "$free" -lt 15 ]; then log "disk guard: ${free} GB free < 15, not scoring (keeper territory); sleeping"; sleep 1800; continue; fi
  fetch=""
  [ "$free" -lt 20 ] && { fetch="--no-fetch"; log "disk ${free} GB free < 20: lean mode (no server fetch, local keeper copies only)"; }
  log "scoring window $ns..$((ns + W)) (free ${free} GB)"
  nice -n 10 python3 "$C/cp_score.py" --start "$ns" --end $((ns + W)) --procs 2 $fetch --label loop >> "$D/out/loop.log" 2>&1 || { log "cp_score failed for $ns (retry in 10 min)"; sleep 600; continue; }
  python3 "$C/cp_table.py" > /dev/null 2>>"$D/out/loop.log" || log "cp_table failed"
  # prune caches older than the next window's look-back (chunk start < next_start - 600)
  nxt=$(next_start)
  for f in "$D"/cache/*.npz; do
    [ -e "$f" ] || continue
    t=${f##*txs_}; t=${t%.npz}
    [ "$t" -lt $((nxt - 600)) ] && rm -f "$f"
  done
  log "cache $(du -sh "$D/cache" | cut -f1), out $(du -sh "$D/out" | cut -f1)"
done
rm -f "$D/out/loop.pid"
