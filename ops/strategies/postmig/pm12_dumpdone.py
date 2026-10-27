#!/usr/bin/env python3
# POST-MIGRATION STUDY: "the dumper is done" trigger. For each PumpSwap sell, the seller's token balance left after the
# sell (curve inventory at migration + post-migration buys - sells; transfers are not seen). Trigger: a sell of >= X SOL
# that drops the price >= Y and leaves the seller with <= 2% of its peak balance (it sold out). Entry at +35/50 ms,
# exit after a timer. Chosen on R2, tested on R3, checked on R4 (same harness as pm10).
import sys, os, json, itertools, collections, time
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import pmsim
import pm10_search as S

def done_flags(c):
    r = c.r; R = r.R
    BC = np.load(f"{pmsim.OUT}/{r.run}_bc.npz")
    mig = {}
    for t in r.toks:
        if t["grp"] is not None: mig[int(R["mint"][r.gstart[t["grp"]]])] = (t["mig_s"], t["mig_i"])
    inv = collections.defaultdict(int)
    for m, u, s, i, b, tok in zip(BC["mint"].tolist(), BC["user"].tolist(), BC["s"].tolist(), BC["i"].tolist(), BC["isbuy"].tolist(), BC["tok"].tolist()):
        ms = mig.get(m)
        if ms is None or (s, i) > ms: continue
        inv[(u, m)] += tok if b else -tok
    n = len(R["s"]); flag = np.zeros(n, bool)
    U = R["user"].tolist(); M = R["mint"].tolist(); SD = R["side"].tolist(); BA = R["base"].tolist()
    h = {}; pk = {}
    for j in range(n):
        key = (U[j], M[j])
        if key not in h:
            v = max(0, inv.get(key, 0)); h[key] = v; pk[key] = v
        if SD[j] == 1:
            h[key] += BA[j]; pk[key] = max(pk[key], h[key])
        else:
            h[key] -= BA[j]
            if pk[key] > 0 and h[key] <= 0.02 * pk[key]: flag[j] = True
    return flag

def grid():
    for x, y, (a0, a1), ty, h in itertools.product([0.5, 1, 3], [0.03, 0.08, 0.15], [(0, 60), (0, 600), (60, 7200)],
                                                    ["instant", "organic", "all"], [3, 10, 30, 120]):
        yield dict(fam="DONE", x=x, y=y, a0=a0, a1=a1, types=ty, hold=h, guard=1.03)

def trig(c, P):
    R = c.r.R
    m = c.done & (R["side"] == -1) & (c.sol >= P["x"]) & (c.drop <= -P["y"]) & (c.age >= P["a0"]) & (c.age <= P["a1"]) & np.isin(c.gtype[c.r.rank], S.TYPES[P["types"]])
    idx = c.dedupe(np.nonzero(m)[0], P["hold"] * 1000 + 500)
    return c.r.rank[idx], R["arr"][idx], R["p_post"][idx]

if __name__ == "__main__":
    t0 = time.time()
    c2 = S.Ctx("R2"); c2.done = done_flags(c2); print("R2 ready", int(c2.done.sum()), "sell-outs", f"{time.time()-t0:.0f}s", flush=True)
    res = []; nv = 0
    for P in grid():
        nv += 1
        g, t, p = trig(c2, P)
        e = S.evaluate(c2, g, t, p, P, 35.0)
        if e: res.append(dict(P=P, R2_35=e))
    ok = [x for x in res if x["R2_35"]["one"]["n"] >= 30 and x["R2_35"]["one"]["ex_top1pct"] > 0 and x["R2_35"]["one"]["pnl"] > 0]
    ok.sort(key=lambda x: -x["R2_35"]["one"]["pnl"]); top = ok[:10]
    print(f"DONE: {nv} variants, {len(ok)} positive on R2", flush=True)
    del c2
    for run in ("R3", "R4"):
        c = S.Ctx(run); c.done = done_flags(c)
        for x in top:
            g, t, p = trig(c, x["P"]); x[f"{run}_35"] = S.evaluate(c, g, t, p, x["P"], 35.0); x[f"{run}_50"] = S.evaluate(c, g, t, p, x["P"], 50.0)
        del c
    json.dump(dict(nvar=nv, n_pos=len(ok), top=top), open(f"{pmsim.OUT}/search_DONE.json", "w"))
    f = lambda e: {k: e["one"][k] for k in ("n", "pnl", "mean", "win", "ex_top1pct", "per_day") if k in e["one"]} if e else None
    for x in top:
        print(json.dumps(x["P"]), "\n   R2:", f(x["R2_35"]), "\n   R3@35:", f(x.get("R3_35")), " R3@50:", f(x.get("R3_50")), "\n   R4@35:", f(x.get("R4_35")), flush=True)
