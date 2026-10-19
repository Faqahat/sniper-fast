#!/usr/bin/env python3
"""Definitive graduation scan: getAccountInfo on each bonding curve, read the `complete` flag and
real_sol_reserves. pump BondingCurve layout: disc(8) vtok(8) vsol(8) rtok(8) rsol(8) supply(8) complete(1) creator(32)."""
import sys, os, json, base64, struct
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, "/root/profit_backtest")
import common as C

creates = json.load(open("/root/profit_backtest/creates.json"))
OUT = "/root/edge_hunt/grad_state.json"

def one(m):
    bc = m["bonding_curve"] if m.get("bonding_curve") else C.bonding_curve_of(m["mint"])
    r = C.rpc("getAccountInfo", [bc, {"encoding":"base64"}])
    val = r.get("value") if isinstance(r, dict) else None
    rec = {"mint":m["mint"], "bc":bc, "create_slot":m["create_slot"],
           "exists": val is not None, "complete":None, "real_sol":None, "lamports":None}
    if val:
        rec["lamports"] = val.get("lamports")
        try:
            data = base64.b64decode(val["data"][0])
            if len(data) >= 49:
                vtok, vsol, rtok, rsol, supply = struct.unpack_from("<QQQQQ", data, 8)
                complete = data[48]
                rec["complete"] = int(complete)
                rec["real_sol"] = rsol/1e9
                rec["virt_sol"] = vsol/1e9
        except Exception as e:
            rec["err"] = str(e)
    return rec

out=[]
with ThreadPoolExecutor(max_workers=24) as ex:
    futs=[ex.submit(one,m) for m in creates]
    done=0
    for fu in as_completed(futs):
        try: out.append(fu.result())
        except Exception: pass
        done+=1
        if done%200==0: print(f"  {done}/{len(creates)}", flush=True)
json.dump(out, open(OUT,"w"))
comp = sum(1 for r in out if r.get("complete")==1)
ne  = sum(1 for r in out if not r["exists"])
print(f"total={len(out)} complete(graduated)={comp} missing_acct={ne} not_complete={sum(1 for r in out if r.get('complete')==0)}")
# of missing accounts, these likely graduated+closed; show real_sol dist of graduated
import statistics as st
rs=[r['real_sol'] for r in out if r.get('real_sol') is not None]
if rs: print(f"real_sol dist: p50={st.median(rs):.2f} max={max(rs):.2f}")
