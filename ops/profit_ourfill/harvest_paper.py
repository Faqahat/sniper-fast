#!/usr/bin/env python3
"""Harvest bonding-curve price paths for the 258 paper-window mints = a TRUE temporal OOS set
(paper slots 456878173-456911074 are disjoint from and later than the backtest window)."""
import sys, os, json, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, "/root/profit_backtest")
import common as C

rows = {}
for ln in open("/root/profit_ourfill/paper_launches.txt"):
    slot, mint, dev, van = ln.split()
    rows[mint] = {"mint": mint, "create_slot": int(slot), "dev_buy_wire_lamports": int(dev), "vanilla": van=="true"}
rows = list(rows.values())
OUT = "/root/profit_ourfill/paper_traj.json"
done = {}
if os.path.exists(OUT):
    try: done = {t["mint"]: t for t in json.load(open(OUT))}
    except Exception: done = {}
todo = [r for r in rows if r["mint"] not in done]
print(f"paper mints {len(rows)} done {len(done)} todo {len(todo)}", flush=True)
lock = threading.Lock(); results = list(done.values()); cnt = 0
def work(r):
    tr = C.trajectory(r["mint"], r["create_slot"])
    ser = tr["series"]
    epx = ser[0][2] if ser else None   # first observed trade px = floor proxy
    return {**r, "entry_px": epx, "cosnipers": tr["cosnipers_slot0"], "n": len(ser),
            "series": [[s, round(p,18)] for (s,_,p) in ser]}
with ThreadPoolExecutor(max_workers=24) as ex:
    futs = {ex.submit(work, r): r for r in todo}
    for fu in as_completed(futs):
        try: res = fu.result()
        except Exception: continue
        with lock:
            results.append(res); cnt += 1
            if cnt % 50 == 0:
                json.dump(results, open(OUT,"w")); print(f"  {cnt}/{len(todo)}", flush=True)
json.dump(results, open(OUT,"w"))
nn = sum(1 for r in results if r["n"]>0)
print(f"DONE {len(results)} with_trades {nn} -> {OUT}", flush=True)
