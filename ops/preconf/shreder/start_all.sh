#!/bin/bash
# HOST: START EVERYTHING ON FRA for the Shreder trial hour:
#   1. preflight (binary sha, disk, memory, collector lag, endpoint TCP reachability — no gRPC call)
#   2. Shreder recorder (unfiltered preconf + Binary streams, dataset + pump views)   -> FRA /root/shreder/data/<RUN>
#   3. Constant-K feed race next to it (ck/ck_start.sh)                                -> FRA /root/shreder/ck/out
#   4. clock probe (FRA/AMS chrony + host-hub bracket + FRA->AMS ping)               -> host <run>/fra/clock_start.json
#   5. first status after ~15 s
# usage: start_all.sh [MINUTES=75] [RUN=trial_<PKT yyyymmdd>]
# env:   FILTER=all|broad  MODE=two|both  EXCLUDE_VOTES=0|1  PUMP_PAIR=0|1  NO_CK=1
set -uo pipefail
H=$(dirname "$(readlink -f "$0")")
MIN=${1:-75}; RUN=${2:-trial_$(TZ=Asia/Karachi date +%Y%m%d)}
DATE=${RUN#trial_}; HD=/home/moiz/sniper-data/preconf/$DATE
mkdir -p "$HD/fra" "$HD/ck" "$HD/engine"
echo "$RUN" > /home/moiz/sniper-data/preconf/CURRENT_RUN
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -p 1996 it@84.32.100.36)
want=$(cut -d' ' -f1 "$H/dist/shreder_rec.sha256")
bash "$H/preflight.sh" "$RUN" "$MIN"
echo "== start Shreder recorder"
"${SSH[@]}" "sudo env FILTER=${FILTER:-all} MODE=${MODE:-two} EXCLUDE_VOTES=${EXCLUDE_VOTES:-0} PUMP_PAIR=${PUMP_PAIR:-0} EXTRA='${EXTRA:-}' /root/shreder/run_rec.sh $RUN $MIN" || { echo "RECORDER START FAILED"; exit 1; }
if [ "${NO_CK:-0}" != 1 ] && [ -x "$H/ck/ck_start.sh" ]; then
  echo "== start Constant-K feed race"
  bash "$H/ck/ck_start.sh" "$MIN" || echo "CK RACE START FAILED (recorder keeps running)"
else
  echo "== Constant-K feed race skipped"
fi
echo "== clock probe (start)"
python3 -I "$H/clock_probe.py" "$HD/fra/clock_start.json" --n 40 || echo "clock probe failed (non-fatal)"
sleep 12
echo "== status"
bash "$H/status.sh" "$RUN"
