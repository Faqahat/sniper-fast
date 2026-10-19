#!/usr/bin/env python3
"""For each harvested create, reconstruct the create-slot-anchored bonding-curve price series.
Threaded, resumable (caches each mint's result to trajectories.json). Heavy RPC step."""
import sys, os, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

CRE = "/root/profit_backtest/creates.json"
OUT = "/root/profit_backtest/trajectories.json"
creates = json.load(open(CRE))
done = {}
if os.path.exists(OUT):
    try: done = {t["mint"]: t for t in json.load(open(OUT))}
    except Exception: done = {}
todo = [c for c in creates if c["mint"] not in done]
print(f"creates {len(creates)}  already done {len(done)}  todo {len(todo)}", flush=True)

lock = __import__("threading").Lock()
results = list(done.values())
def work(c):
    tr = C.trajectory(c["mint"], c["create_slot"])
    ser = tr["series"]
    epx = c.get("entry_px")
    src = "dev_buy"
    if not epx or not tr["reached_floor"]:
        if ser: epx = ser[0][2]; src = "first_trade"
        else: epx = None
    return {"mint": c["mint"], "create_slot": c["create_slot"], "blockTime": c.get("blockTime"),
            "entry_px": epx, "entry_src": src, "reached_floor": tr["reached_floor"],
            "cosnipers": tr["cosnipers_slot0"], "n": len(ser),
            "series": [[s, round(p, 18)] for (s, _, p) in ser]}

cnt = 0
with ThreadPoolExecutor(max_workers=28) as ex:
    futs = {ex.submit(work, c): c for c in todo}
    for fu in as_completed(futs):
        r = fu.result()
        with lock:
            results.append(r); cnt += 1
            if cnt % 100 == 0:
                json.dump(results, open(OUT, "w"))
                print(f"  {cnt}/{len(todo)}  (saved {len(results)})", flush=True)
json.dump(results, open(OUT, "w"))
nn = sum(1 for r in results if r["n"] > 0)
nfloor = sum(1 for r in results if r["reached_floor"])
print(f"DONE trajectories {len(results)}  with_trades {nn}  reached_floor {nfloor}  -> {OUT}", flush=True)
