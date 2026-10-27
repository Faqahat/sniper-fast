#!/bin/bash
# PRE-SEND V2: build a fresh tape key "R5" from a collector run and run the V2 replay on it.
#  - default: the fresh hours after this analysis (10-25 09:56 PKT -> the recording's end - 30 min) of run_20261024_1425;
#  - a later probe: bash r5_fresh.sh /home/moiz/sniper-data/collect/run_<date>_<time> "MM-DD HH:MM" (window start, PKT).
# The tape is always built from the run's start, so tokens keep their history. Read-only on the recording.
set -e
RUN=${1:-/home/moiz/sniper-data/collect/run_20261024_1425}
FROM=${2:-"10-25 09:56"}
cd /home/moiz/sniper/ops/strategies/presend/v2
D=/home/moiz/sniper-data/presend_v2
rm -rf $D/tape_R5
nice -n 15 python3 b1_tape.py --run $RUN --work $D/tape_R5 --procs 5 | tail -2
FROM="$FROM" python3 - << 'PY'
import numpy as np, json, time, os
z = np.load("/home/moiz/sniper-data/presend_v2/tape_R5/day_PS.npz"); bt = z["bt"]; end = int(bt[bt > 0].max())
to = time.strftime("%m-%d %H:%M", time.gmtime(end - 1800 + 18000))
json.dump([os.environ["FROM"], to], open("/home/moiz/sniper-data/presend_v2/tape_R5/win.json", "w")); print("R5 window", os.environ["FROM"], "->", to)
PY
nice -n 15 python3 b2_crehist.py | tail -1
nice -n 15 python3 v2lib.py R5 6 | tail -1
