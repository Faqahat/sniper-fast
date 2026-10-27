#!/bin/bash
# Container side of the raw recording (owner OK 10-24 06:50 PKT: record everything raw, daily replays while tuning).
# One pass (keeper_loop.sh runs it every 10 min):
#  (a) COPY every server collector run (/root/sniper-collect/run_*) to /home/moiz/sniper-data/collect/<run>/: every file whose
#      size differs (new chunks, the chunk being written, launches / enrich / run / status / final / gaps), size-checked;
#  (b) PRUNE a server run once it is not the current run, its collector says DONE (or it is > 12 h past its tail), its tail
#      ended > 2 h ago, and EVERY server file is
#      here with the same size (server disk 77 GB, ~17 GB per day). Never deletes anything in the container.
# Stops copying when the container has < 30 GB free (logged). Log: /home/moiz/sniper-data/collect/keeper.log
set -u
D=/home/moiz/sniper-data/collect; SRV=/root/sniper-collect
ssh_() { ssh -p 1996 -o ConnectTimeout=20 -o ServerAliveInterval=15 it@84.32.100.36 "$@"; }
log() { echo "$(date -u +%FT%TZ) $*" >> $D/keeper.log; }
free=$(df --output=avail -B1G /home/moiz | tail -1 | tr -d ' ')
used=$(df --output=pcent /home/moiz | tail -1 | tr -dc '0-9')
# owner 10-26: cap at 95% used (was: < 30 GB free); the recordings then wait on the server (nothing is lost, nothing pruned)
if [ "$used" -ge 95 ]; then log "container disk ${used}% used (${free} GB free): not copying (and so not pruning the server)"; exit 1; fi
info=$(ssh_ "sudo bash -c 'cd $SRV && echo CUR=\$(cat current_run) && find . -maxdepth 1 -type d -name \"run_*\" -printf \"%f\n\"'") || { log "ssh failed"; exit 1; }
cur=$(echo "$info" | sed -n 's/^CUR=//p')
now=$(date +%s)
for R in $(echo "$info" | grep '^run_' | sort); do
  mkdir -p "$D/$R/txs"
  list=$(ssh_ "sudo find $SRV/$R -type f -printf '%s %P\n'") || { log "$R: list failed"; continue; }
  need=$(echo "$list" | while read -r sz p; do [ -n "$p" ] || continue; [ -f "$D/$R/$p" ] && [ "$(stat -c %s "$D/$R/$p")" = "$sz" ] || echo "$p"; done)
  n=$(echo "$need" | grep -c . || true)
  if [ "$n" -gt 0 ]; then
    # in batches (a long argument list over ssh)
    echo "$need" | xargs -n 40 | while read -r batch; do
      ssh_ "sudo tar -C $SRV/$R -cf - $batch" | tar -xf - -C "$D/$R" || log "$R: copy batch failed"
    done
    log "$R: copied $n file(s)"
  fi
  # prune (b): not current, tail ended > 2 h ago, every file here with the same size (re-listed after the copy)
  [ "$R" = "$cur" ] && continue
  case "$R" in run_20[0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9]) ;; *) continue;; esac   # only well-formed run dirs
  tend=$(python3 -c "import json,sys; print(int(json.load(open(sys.argv[1]))['tail_end_time']))" "$D/$R/run.json" 2>/dev/null || echo 0)
  [ "$tend" -gt 0 ] && [ "$now" -gt $(( tend + 7200 )) ] || continue
  # the collector's final pass (enrich drain + curve / holder snapshot of every mint) can run for hours after the tail:
  # prune only when the server's status.json says DONE (10-24: a prune at tail + 2 h cut R3's final pass short), or when
  # the run is > 12 h past its tail (a stuck / crashed final pass)
  phase=$(ssh_ "sudo grep -o '\"phase\": \"[^\"]*\"' $SRV/$R/status.json 2>/dev/null" | sed 's/.*: "//; s/"$//')
  if [ "$phase" != "DONE" ] && [ "$now" -le $(( tend + 43200 )) ]; then log "$R: not pruned yet (collector phase '${phase:-?}', not DONE)"; continue; fi
  list2=$(ssh_ "sudo find $SRV/$R -type f -printf '%s %P\n'") || continue
  miss=$(echo "$list2" | while read -r sz p; do [ -n "$p" ] || continue; [ -f "$D/$R/$p" ] && [ "$(stat -c %s "$D/$R/$p")" = "$sz" ] || echo "$p"; done | grep -c . || true)
  nfiles=$(echo "$list2" | grep -c . || true)
  if [ "$miss" -eq 0 ] && [ "$nfiles" -gt 0 ]; then
    bytes=$(echo "$list2" | awk '{s += $1} END {printf "%.1f", s / 1e9}')
    ssh_ "sudo rm -rf $SRV/$R" && log "$R: PRUNED on the server ($nfiles files, $bytes GB, all here with the same sizes)" || log "$R: prune failed"
  else
    log "$R: not pruned yet ($miss of $nfiles files differ)"
  fi
done
