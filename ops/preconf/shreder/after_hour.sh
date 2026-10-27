#!/bin/bash
# HOST: ONE command after the trial hour: verified fetch -> catalog -> analyze.py -> ck_compare.py.
# usage: after_hour.sh [RUN] [--analyze-only]
# env:   ENGINE_HOST=ams|fra  ENGINE_LOG=<path on that host>   (passed to fetch.sh; default: the newest /root/prod/runs/dip_<host>_r*.jsonl on that host)
set -uo pipefail
H=$(dirname "$(readlink -f "$0")")
RUN=$(cat /home/moiz/sniper-data/preconf/CURRENT_RUN 2>/dev/null); ONLY=0
for a in "$@"; do case "$a" in --analyze-only) ONLY=1;; *) RUN=$a;; esac; done
DATE=${RUN#trial_}; HD=/home/moiz/sniper-data/preconf/$DATE
echo "== $(TZ=Asia/Karachi date +%H:%M:%S) PKT after-hour pipeline for $RUN -> $HD"
[ "$ONLY" = 1 ] || bash "$H/fetch.sh" "$RUN" || echo "!! fetch reported a problem (see above); continuing with what is on the host"
# chain-recording coverage (FRA collector copies arrive every ~10 min)
python3 -I - "$HD" <<'PY'
import glob, json, os, re, sys, time
hd = sys.argv[1]
last = 0
for p in glob.glob("/home/moiz/sniper-data/collect/run_*/txs/txs_*.jsonl.gz"):
    m = re.search(r"txs_(\d+)\.jsonl\.gz$", p)
    if m: last = max(last, int(m.group(1)))
end = 0
for p in glob.glob(os.path.join(hd, "fra", "*.idx.jsonl")):
    for l in open(p):
        try: end = max(end, json.loads(l)["t1"] // 10**9)
        except Exception: pass
f = lambda s: time.strftime("%H:%M:%S", time.gmtime(s + 5 * 3600)) + " PKT"
if end:
    print(f"chain recording newest file starts {f(last)} (files are 5-min chunks); recorder data ends {f(end)}"
          + ("  -> OK" if last + 300 >= end else "  -> NOT YET COVERED: re-run with --analyze-only in ~10-15 min for full accuracy"))
PY
EH=$(cat "$HD/engine/ENGINE_HOST" 2>/dev/null || echo "${ENGINE_HOST:-ams}")
if [ -f "$H/analyze.py" ]; then
  echo "== analyze.py (engine on $EH)"
  EF=$(cat "$HD/engine/ENGINE_LOG" 2>/dev/null)
  timeout 2400 python3 -I "$H/analyze.py" --run-dir "$HD" --engine-host "$EH" --leaders-rpc ${EF:+--engine "$HD/engine/$EF"} 2>&1 | tail -60
fi
if [ -f "$H/ck_compare.py" ]; then
  echo "== ck_compare.py"
  timeout 2400 python3 -I "$H/ck_compare.py" --run-dir "$HD" 2>&1 | tail -60
fi
echo "== outputs: $HD/analysis/ ; dataset catalog: $HD/catalog.json"
