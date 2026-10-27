#!/usr/bin/env python3
# POST-MIGRATION STUDY: the winners' own triggers at OUR speed. For each round trip of the chosen scalpers, the trigger
# is the biggest sell (>= 0.3 SOL) in the same pool in the 1 s before their entry. We replay an entry at trigger + LAT
# with their exit time (and with fixed holds), our size and cost. Also: how far behind the trigger they land.
import sys, os, json, pickle
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import pmsim
from pmsim import Run, stats, one_at_a_time, SMS
OUT = pmsim.OUT

def triggers_of(r, tr, u):
    ix = np.nonzero((tr["user"] == u) & (tr["open"] == 0))[0]
    R = r.R; trig = []; rows = []
    for t in ix.tolist():
        fr = int(tr["first_row"][t]); m = R["mint"][fr]; a = R["arr"][fr]
        j = fr - 1; best = -1; bsol = 0.0
        while j >= 0 and R["mint"][j] == m and R["arr"][j] >= a - 1000:
            if R["side"][j] == -1 and R["qtot"][j] >= 0.3e9 and R["qtot"][j] > bsol and R["user"][j] != u: best = j; bsol = R["qtot"][j]
            j -= 1
        if best >= 0: trig.append(best); rows.append(t)
    return np.array(trig, np.int64), np.array(rows, np.int64)

if __name__ == "__main__":
    run = sys.argv[1] if len(sys.argv) > 1 else "R3"
    r = Run(run)
    tr = dict(np.load(f"{OUT}/{run}_trips.npz"))
    gid = {x: j for j, x in enumerate(r.strs)}
    W = json.load(open(f"{OUT}/wallets.json"))
    pick = []
    for w, x in W.items():
        a = x["runs"].get("R2"); b = x["runs"].get("R3")
        if x["insider"] or not a or not b: continue
        if a["n"] >= 300 and b["n"] >= 300 and a["pnl"] > 0 and b["pnl"] > 0 and (b["hold_med"] or 99) < 20: pick.append((a["pnl"] + b["pnl"], w))
    pick.sort(reverse=True)
    allT = []; allR = []
    for _, w in pick[:25]:
        u = gid.get(w)
        if u is None: continue
        trig, rows = triggers_of(r, tr, u)
        if len(trig) == 0: continue
        fr = tr["first_row"][rows].astype(np.int64)
        dtx = np.where(r.R["s"][fr] == r.R["s"][trig], r.R["i"][fr] - r.R["i"][trig], -1)
        dms = r.R["arr"][fr] - r.R["arr"][trig]
        hold = tr["arr_out"][rows] - tr["arr_in"][rows]
        own = (tr["proceeds"][rows] - tr["cost"][rows]) / tr["cost"][rows]
        g = r.rank[trig]; t = r.R["arr"][trig]; pref = r.R["p_post"][trig]
        line = [f"{w[:10]} trips {len(rows)} own {own.mean()*100:+.2f}%  behind trigger: dtx_med {np.median(dtx[dtx>=0]) if (dtx>=0).any() else None} dms_med {np.median(dms):.0f}"]
        for lat in (8.0, 35.0, 50.0):
            # same exit moment as theirs (hold measured from their entry)
            res = r.sim(g, t, pref, size=0.67, lat=lat, guard=None, hold_ms=np.maximum(hold - (lat - dms), 200.0))
            ret = res["ret"]
            line.append(f"lat{lat:.0f}: ret {np.mean(ret)*100:+.2f}% pnl/trip(our cost) {np.mean(res['pnl']):+.4f}")
        print(" | ".join(line), flush=True)
        allT.append(trig); allR.append(rows)
