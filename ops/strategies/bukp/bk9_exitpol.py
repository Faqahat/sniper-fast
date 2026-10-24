#!/usr/bin/env python3
# Exit POLICIES on BUkpShoE's own entries re-timed to our landing (read-only): "hold at least H slots, then sell into the
# first buy burst (other-wallet buys >= X SOL within 3 slots) [and price >= entry], else the 1,417-slot timeout"; our sell
# lands 35 ms after the burst trade. Size 0.6 SOL; curve < 50 entries (where its money is) and all. Chosen on R2.
import sys, json, zlib, itertools
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/bukp")
import p4_eval as E
import bk8_replica as B8
OUT = "/home/moiz/sniper-data/strategies/bukp"
POL = [dict(H=h, X=x, need_up=u) for h in (0, 50, 100, 160, 300) for x in (0.5, 1.0, 2.0) for u in (False, True)]
def run(run_, lat=35, size_mode="0.6"):
    d = E.DAYS[run_]; T = [t for t in json.load(open(f"{OUT}/trips_{run_}.json")) if t["closed"] and t["sells"]]
    ents = [(B8.entry(d, t, lat, size_mode), t) for t in T]
    res = {}
    for pi, P in enumerate(POL):
        pa = []; ps = []
        for e, t in ents:
            if e is None: continue
            if e["fail"]: pa.append(e["pnl"]); continue
            path, Vs, Ts, rows = e["path"], e["Vs"], e["Ts"], e["rows"]
            if not path: continue
            hit = None; win = []
            for n, m in enumerate(path):
                held = rows[n][3]
                # buy SOL by others in the last 3 slots (incl. this trade)
                win = [x for x in win if d["s"][x] >= d["s"][m] - 3] + ([m] if d["buy"][m] else [])
                if held >= P["H"] and sum(d["sol"][x] for x in win) / 1e9 >= P["X"] and (not P["need_up"] or rows[n][1] >= 1.0): hit = n; break
                if held > B8.TOUT: break
            if hit is not None:
                ta2 = d["arr"][path[hit]] + lat; nn = hit
                while nn + 1 < len(path) and d["arr"][path[nn + 1]] < ta2: nn += 1
            else:
                nn = len(path) - 1
                while nn > 0 and d["s"][path[nn]] > e["s_land"] + B8.TOUT: nn -= 1
            got = Vs[nn] * e["qt"] / (Ts[nn] + e["qt"]) * (1 - e["fr"]) / 1e9; pnl = got - e["B"] - B8.FIX
            pa.append(pnl)
            if t["buys"][0]["sol"] < 1.0: ps.append(pnl)
        res[pi] = (len(pa), round(sum(pa), 2), round(float(np.mean(pa)), 4), len(ps), round(sum(ps), 2), round(float(np.mean(ps)), 4) if ps else 0)
    return res
if __name__ == "__main__":
    E.load(["R2", "R3", "R1"])
    R = {r: run(r) for r in ("R2", "R3", "R1")}
    best = sorted(range(len(POL)), key=lambda i: -R["R2"][i][4])[:8]
    print("exit policies on its own entries at 35 ms, 0.6 SOL; columns: all n/pnl/mean | curve<50 n/pnl/mean   (ranked by R2 curve<50 P&L)")
    for i in best:
        print(f"  {POL[i]} | R2 {R['R2'][i]} | R3 {R['R3'][i]} | R1 {R['R1'][i]}")
    json.dump(dict(pol=POL, res=R), open(f"{OUT}/exit_policies.json", "w"))
