#!/bin/bash
# Live run on the encrypted-keystore wallet. Asks the passphrase ONCE (hidden), checks it unlocks the wallet, then
# runs in the background: segments back to back until <hours> are up, one shared fee budget, each segment handed the
# passphrase over a pipe (never a file, never argv or the environment; it lives only in this script's memory).
# Closing the SSH session does not stop it. Stop early: touch runs/<name>.stop (or kill the segment process).
# usage (from your own machine): ssh -t root@84.32.59.15 'cd ~/arb-lab && ./run-w.sh <name> <hours> <segment min> <fee budget lamports> <config>'
cd /root/arb-lab || exit 1
NAME=$1; HOURS=$2; SEG=$3; BUDGET=$4; CONF=$5
[ -n "$CONF" ] && [ -f "$CONF" ] || { echo "usage: run-w.sh <name> <hours> <segment min> <fee budget lamports> <config>"; exit 2; }
if pgrep -f "arb-lab-w run" >/dev/null; then echo "an arb-lab-w run is already going"; exit 1; fi
read -rs -p "keystore passphrase (hidden): " PASS; echo
if ! printf '%s\n' "$PASS" | ./arb-lab-w wallet --config "$CONF"; then echo "the passphrase does not unlock the wallet: not starting"; exit 1; fi
LOG=runs/$NAME.supervisor.log
(
  trap '' HUP
  exec </dev/null >>"$LOG" 2>&1
  say() { echo "$(date -u +%FT%TZ) $*"; }
  END=$(( $(date +%s) + HOURS * 3600 ))
  say "start: $HOURS h in $SEG-min segments, fee budget $BUDGET lamports, config $CONF"
  i=0; crashes=()
  while [ "$(date +%s)" -lt "$END" ]; do
    [ -f "runs/$NAME.stop" ] && { say "stop file"; break; }
    i=$((i + 1))
    spent=$(python3 -c "
import json,glob
t=0
for f in glob.glob('runs/$NAME-p*/status.jsonl'):
    try: t+=json.loads(open(f).readlines()[-1])['exec']['sending']['failed_fees_lamports']
    except Exception: pass
print(t)")
    left=$((BUDGET - spent))
    live="--live"; [ "$left" -lt 1000000 ] && { live=""; say "fee budget spent ($spent): segment $i records only"; }
    free=$(df --output=avail -BG / | tail -1 | tr -dc 0-9); [ "$free" -lt 25 ] && { say "disk low (${free}G): stop"; break; }
    mins=$(( (END - $(date +%s)) / 60 )); [ "$mins" -gt "$SEG" ] && mins=$SEG; [ "$mins" -lt 2 ] && break
    seg="${CONF%.toml}-p$i.toml"
    sed "s/^max_failed_fees_lamports = .*/max_failed_fees_lamports = $left   # what is left of the run budget/" "$CONF" > "$seg"
    say "segment $i: $mins min, budget left $left, disk ${free}G, $live"
    t0=$(date +%s)
    printf '%s\n' "$PASS" | ./arb-lab-w run --config "$seg" --minutes "$mins" --name "$NAME-p$i" $live > "runs/$NAME-p$i.out" 2>&1
    rc=$?; dur=$(( $(date +%s) - t0 ))
    say "segment $i exit $rc after ${dur}s: $(tail -1 runs/$NAME-p$i/status.jsonl 2>/dev/null | python3 -c 'import json,sys; s=json.load(sys.stdin)["exec"]["sending"]; print({k:s[k] for k in ("sent","landed","wins","failed_fees_lamports","profit_lamports")})' 2>/dev/null)"
    ( cd "runs/$NAME-p$i" && nice zstd -q --rm -3 exec.jsonl rivals.jsonl txarr.log poh.log moves.log 2>/dev/null ) &
    if [ "$dur" -lt $(( mins * 60 - 30 )) ]; then
      now=$(date +%s); crashes+=("$now"); recent=0
      for c in "${crashes[@]}"; do [ $((now - c)) -lt 900 ] && recent=$((recent + 1)); done
      say "segment $i ended early ($recent in 15 min): $(grep -iE 'panic|error' runs/$NAME-p$i.out | tail -2 | cut -c1-200)"
      [ "$recent" -gt 6 ] && { say "too many early ends: stop"; break; }
      sleep 10
    fi
  done
  wait
  PASS=""
  say "done"
) &
disown
echo "started $NAME in the background; log: runs/$NAME.supervisor.log (stop early: touch runs/$NAME.stop)"
