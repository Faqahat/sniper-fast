#!/usr/bin/env python3
"""Freshly harvest a NEW window disjoint from BOTH mined (456604917-456820114) and paper
(456878173-456911074): creates in [456911075 .. finalized-400]. Parse create features + build
forward trajectory (common.trajectory). Output paper_traj-compatible rows -> fresh_traj.json."""
import sys, os, json, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0,"/root/profit_backtest"); import common as C

LO=456911075
s0=C.rpc("getSlot",[{"commitment":"finalized"}])
HI=s0-400
print(f"finalized {s0}  fresh window [{LO}..{HI}]",flush=True)
sigs=[]; before=None; pages=0
while pages<80:
    pr=[C.MINT_AUTHORITY,{"limit":1000}]
    if before: pr[1]["before"]=before
    ch=C.rpc("getSignaturesForAddress",pr)
    if not ch: break
    sigs+=ch; before=ch[-1]["signature"]; pages+=1
    if pages%5==0: print(f"  page {pages}: total {len(sigs)} oldest {ch[-1]['slot']}",flush=True)
    if len(ch)<1000 or ch[-1]["slot"]<=LO: break
cand=sorted([s for s in sigs if not s["err"] and LO<=s["slot"]<=HI],key=lambda s:s["slot"])
print(f"creates in fresh window: {len(cand)}",flush=True)
TARGET=500
if len(cand)>TARGET:
    step=len(cand)/TARGET; cand=[cand[int(i*step)] for i in range(TARGET)]
print(f"subsampled to {len(cand)}",flush=True)

OUT="/root/create_cu_reval/fresh_traj.json"
done={}
if os.path.exists(OUT):
    try: done={t["mint"]:t for t in json.load(open(OUT))}
    except: done={}

def work(s):
    tx=C.gettx(s["signature"])
    f=C.parse_create(tx)
    if not f or not f.get("entry_px"): return None
    # base filter early: creator_fee==0 and sized dev
    if f["creator_fee_bps"]!=0: return None
    devw = 1e18 if f["dev_buy_wire"]>=1e17 else f["dev_buy_wire"]
    if devw<2.0: return None
    tr=C.trajectory(f["mint"], f["create_slot"])
    ser=tr["series"]
    epx=ser[0][2] if ser else None
    return {"mint":f["mint"],"create_slot":f["create_slot"],
            "dev_buy_wire_lamports":int(min(devw,1e9)*1e9) if devw<1e9 else 2_000_000_000,
            "dev_buy_wire_sol":devw,"creator_fee_bps":f["creator_fee_bps"],
            "vanilla":(f["creator_fee_bps"]==0 and not f["mayhem"] and not f["holder_reward"] and not f["cashback"]),
            "entry_px":epx,"cosnipers":tr["cosnipers_slot0"],"n":len(ser),
            "series":[[s2,round(p,18)] for (s2,_,p) in ser],"sig":s["signature"]}

results=list(done.values()); seen={r["mint"] for r in results}; cnt=0; t0=time.time()
todo=[s for s in cand if True]
with ThreadPoolExecutor(max_workers=24) as ex:
    futs={ex.submit(work,s):s for s in todo}
    for fu in as_completed(futs):
        try: r=fu.result()
        except: r=None
        cnt+=1
        if r and r["mint"] not in seen:
            results.append(r); seen.add(r["mint"])
        if cnt%50==0:
            json.dump(results,open(OUT,"w")); print(f"  {cnt}/{len(todo)} kept {len(results)} {time.time()-t0:.0f}s",flush=True)
json.dump(results,open(OUT,"w"))
nn=sum(1 for r in results if r["n"]>0)
print(f"FRESH DONE kept {len(results)} with_trades {nn} -> {OUT}",flush=True)
if results:
    ss=[r["create_slot"] for r in results]; print(f"slot range {min(ss)}..{max(ss)}")
