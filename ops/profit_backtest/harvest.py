#!/usr/bin/env python3
"""Unbiased create_v2 harvest. Paginate getSignaturesForAddress(MINT_AUTHORITY) -> pure create stream,
fetch each create tx (threaded), extract features. Skips the newest SKIP_SLOTS so trajectories are final."""
import sys, os, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

TARGET = int(os.environ.get("TARGET", "1500"))          # creates to actually fetch+sim
SKIP_SLOTS = int(os.environ.get("SKIP_SLOTS", "400"))   # leave recent slots so create+win is finalized
WINDOW_SLOTS = int(os.environ.get("WINDOW_SLOTS", "216000"))  # ~24h (2.5 slots/s)
OUT = "/root/profit_backtest/creates.json"

s0 = C.rpc("getSlot", [{"commitment": "finalized"}])
cutoff_new = s0 - SKIP_SLOTS
cutoff_old = s0 - WINDOW_SLOTS
print(f"finalized slot {s0}  window [{cutoff_old}..{cutoff_new}]  target {TARGET}", flush=True)

# cheap: paginate sig-list only, back to cutoff_old
sigs = []; before = None; pages = 0
while pages < 60:
    pr = [C.MINT_AUTHORITY, {"limit": 1000}]
    if before: pr[1]["before"] = before
    ch = C.rpc("getSignaturesForAddress", pr)
    if not ch: break
    sigs += ch; before = ch[-1]["signature"]; pages += 1
    if pages % 5 == 0: print(f"  page {pages}: total {len(sigs)} oldest slot {ch[-1]['slot']}", flush=True)
    if len(ch) < 1000 or ch[-1]["slot"] <= cutoff_old: break
# non-error creates inside the window, oldest->newest
cand = sorted([s for s in sigs if not s["err"] and cutoff_old <= s["slot"] <= cutoff_new], key=lambda s: s["slot"])
print(f"creates in window: {len(cand)} (slots {cand[0]['slot']}..{cand[-1]['slot']})", flush=True)
# stratified even subsample to TARGET (preserve time coverage for train/val split)
if len(cand) > TARGET:
    step = len(cand)/TARGET
    cand = [cand[int(i*step)] for i in range(TARGET)]
print(f"subsampled to {len(cand)} creates for fetch+sim", flush=True)

def work(s):
    tx = C.gettx(s["signature"])
    f = C.parse_create(tx)
    if f: f["sig"] = s["signature"]
    return f

out = []
with ThreadPoolExecutor(max_workers=24) as ex:
    futs = [ex.submit(work, s) for s in cand]
    done = 0
    for fu in as_completed(futs):
        r = fu.result(); done += 1
        if r and r.get("entry_px"): out.append(r)
        if done % 200 == 0: print(f"  parsed {done}/{len(cand)}  kept {len(out)}", flush=True)
out.sort(key=lambda x: x["create_slot"])
json.dump(out, open(OUT, "w"))
import statistics as st
db = [x["dev_buy"] for x in out]
print(f"\nHARVEST DONE: {len(out)} creates with entry px")
print(f"  slot span {out[0]['create_slot']}..{out[-1]['create_slot']}  ({(out[-1]['blockTime']-out[0]['blockTime'])/3600:.1f} h)")
print(f"  dev_buy(curve) SOL: p25={st.quantiles(db,n=4)[0]:.3f} med={st.median(db):.3f} p75={st.quantiles(db,n=4)[2]:.3f}  max={max(db):.2f}")
van = sum(1 for x in out if x['creator_fee_bps']==0 and not x['mayhem'] and not x['holder_reward'] and not x['cashback'])
snip = sum(1 for x in out if x['creator_fee_bps']==0)
print(f"  vanilla {van}/{len(out)}  is_snipeable(fee==0) {snip}/{len(out)}")
print(f"  saved -> {OUT}")
