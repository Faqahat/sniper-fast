#!/usr/bin/env python3
"""REPLAY4 step 1 [MEASURED]: chain tape for the newer runs from the launch collector's tx chunks.
The collect records carry slot `s`, tx index `i` and the pump.fun TradeEvent (`ev`) -> trade amounts, side and user.
The event's own reserve fields do not match the curve, so reserves are NOT taken from it: the replay anchors
(vsol, vtok) on the engine's own presend_attempt records and rolls the curve forward with these amounts.
Each trade also carries the curve's own token reserve, taken from the tx's post token balance:
vtok = (the mint's largest post balance in `tb`) + VOFF, an offset MEASURED as exactly 73e12 against 515 engine ptape rows.
That makes every row's reserve independent, so a trade the collector missed cannot corrupt the rows after it.
Out: /home/moiz/sniper-data/replay4/tape_<run>.pkl {"trades": {mint: [(slot, idx, buy, sol, tok, user, vtok)]}, "maxi": {slot: max idx}}
usage: build_tape.py r38 r39 r40
"""
import json, gzip, glob, sys, os, pickle, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ev import decode

OUT = "/home/moiz/sniper-data/replay4"
RUNS = {"r38": "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r38.jsonl",
        "r39": "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r39.jsonl",
        "r40": "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r40.jsonl"}
COLLECT = "/home/moiz/sniper-data/collect/run_20261029_1400/txs"
VOFF = 73_000_000_000_000      # virtual - real token reserve (MEASURED, constant)

os.makedirs(OUT, exist_ok=True)
runs = sys.argv[1:] or list(RUNS)

want = {}                      # mint -> set(runs)
span = collections.defaultdict(lambda: [1 << 62, 0])   # run -> [min slot, max slot]
for r in runs:
    for line in open(RUNS[r], errors="replace"):
        if '"presend_attempt"' not in line and '"presend_live_arm"' not in line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        m, s = d.get("mint"), d.get("slot")
        if not m:
            continue
        want.setdefault(m, set()).add(r)
        if s:
            span[r][0] = min(span[r][0], s); span[r][1] = max(span[r][1], s)
print("mints wanted:", len(want), {r: tuple(v) for r, v in span.items()}, flush=True)

trades = collections.defaultdict(list)
maxi = {}
files = sorted(glob.glob(f"{COLLECT}/*.gz"))
for n, f in enumerate(files):
    try:
        for line in gzip.open(f, "rt", errors="replace"):
            try:
                d = json.loads(line)
            except Exception:
                continue
            s, i = d.get("s"), d.get("i")
            if s is None:
                continue
            if i is not None and (s not in maxi or i > maxi[s]):
                maxi[s] = i
            ms = d.get("mints") or []
            if not any(m in want for m in ms):
                continue
            post = {}
            for row in (d.get("tb") or []):
                if len(row) >= 4 and isinstance(row[3], (int, float)):
                    if row[0] not in post or row[3] > post[row[0]]:
                        post[row[0]] = row[3]
            for e in (d.get("ev") or []):
                t = decode(e)
                if t and t["mint"] in want:
                    vt = post.get(t["mint"])
                    trades[t["mint"]].append((s, i, t["buy"], t["sol"], t["tok"], t["user"],
                                              (vt + VOFF) if vt is not None else None))
    except EOFError:
        print("  truncated chunk", f, flush=True)
    if n % 25 == 0:
        print(f"  {n}/{len(files)} mints_hit={len(trades)}", flush=True)

for m in trades:
    trades[m].sort(key=lambda x: (x[0], x[1]))
for r in runs:
    sub = {m: trades[m] for m in want if r in want[m] and m in trades}
    lo, hi = span[r]
    mi = {s: v for s, v in maxi.items() if lo - 10 <= s <= hi + 200}
    pickle.dump({"trades": sub, "maxi": mi}, open(f"{OUT}/tape_{r}.pkl", "wb"))
    nw = sum(1 for m in want if r in want[m])
    print(f"{r}: {len(sub)}/{nw} mints with trades, {sum(len(v) for v in sub.values())} trades, {len(mi)} slots", flush=True)
