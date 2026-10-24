#!/usr/bin/env python3
# READ-ONLY replay (owner rule 2026-10-23): a strategy may not live off landing just ahead of specific bots. Every set is
# re-scored at our mechanics (0.5 SOL, block-order placement at 45 / 75 ms, 1% guard, sell all at the end of the next slot):
#   base | slip (followers our buy prices out fail: core/slip_args.jsonl) | FAST snipers' buys after our entry removed
#   (fast_snipers.json: >= 5 launches bought within 2 slots of the create and >= 50% of their launches) | slip + FAST |
#   TOP-10 most frequent after-us buyers of this set removed | dKMjeG's buys after us removed;
#   + share of fills with NO outside buy between our buy and our sell.
import sys, json, collections, math, os
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
import numpy as np
from multiprocessing import Pool
W = "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK"; HERE = "/home/moiz/sniper/ops/overnight/dkmjeg"
L = rp.load_launches(); O = rp.load_obs(); AR = json.load(open("/home/moiz/sniper/ops/overnight/core/allres.json"))
C = json.load(open(f"{HERE}/coll.json")); ATT = {m for m, v in C.items() if "dk" in v}
FAST = set(json.load(open(f"{HERE}/fast_snipers.json")))
SLIP = rp.load_slip()
def wf(Lm, k=2, rate=0.10, gate=None):
    ev = sorted((c["bt"], m) for m, c in L.items() if c.get("bt")); na = collections.Counter(); nl = collections.Counter(); hist = collections.defaultdict(list); pend = []; pick = set()
    for bt, m in ev:
        while pend and pend[0][0] <= bt:
            _, d, v = pend.pop(0); hist[d].append(v)
        d = L[m]["user"]; listed = na[d] >= k and (nl[d] == 0 or na[d] / nl[d] >= rate)
        if gate:
            h = hist[d]; listed = listed and not (len(h) >= gate[0] and sum(h) / len(h) < gate[1])
        if listed: pick.add(m)
        r = AR.get(m)
        if r and Lm in r and r[Lm]["ok"] and r[Lm].get("0.5") is not None: pend.append((bt + 60, d, r[Lm]["0.5"])); pend.sort()
        nl[d] += 1
        if m in ATT: na[d] += 1
    return pick
R = json.load(open(f"{HERE}/sel_rows.json")); src = open(f"{HERE}/sel2.py").read(); g = {}
exec(src[src.index("def f(r):"):src.index("X = np.array")], {"math": math}, g); exec(src[src.index("def fit("):src.index("tr = run ==")], {"np": np}, g)
X = np.array([g["f"](r) for r in R]); y = np.array([r["att"] for r in R], dtype=float); run = np.array([r["run"] for r in R])
w, mu, sd = g["fit"](X[run == "R1"], y[run == "R1"]); s2 = g["pred"](w, mu, sd, X[run == "R2"]); R2m = [r["m"] for r in R if r["run"] == "R2"]
SETS = {"(a) oracle: its attempted launches": ATT, "(b) walk-forward deployer list": wf("75"), "(b) list + quality gate": wf("75", gate=(3, 0.0)),
        "(m) model of its picks, top 2%": {m for m, sc in zip(R2m, s2) if sc >= np.quantile(s2, 0.98)},
        "(m) model of its picks, top 5%": {m for m, sc in zip(R2m, s2) if sc >= np.quantile(s2, 0.95)}}
ALLM = {m for s in SETS.values() for m in s if m in L and L[m]["run"] == "R2" and m in O and "InitializeMayhemState" not in (L[m].get("ixn") or [])}
byb = collections.defaultdict(set)
for m in ALLM: byb[rp.bucket(m)].add(m)
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5)]
TOP = {}
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = {}
        for Lm in (45, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1.01: r[Lm] = dict(fail=1); continue
            bs = max(c["slot"], tr[ib - 1]["s"])
            between = [t for t in tr[ib:] if t["s"] <= bs + 1]
            buyers = sorted({t["user"] for t in between if t["buy"] and t["user"] not in st["insiders"]})
            d = dict(fail=0, no_out_buy=int(not buyers), buyers=buyers)
            for nm, kw in (("base", {}), ("slip", dict(slip=SLIP)), ("noFAST", dict(drop_after=FAST)), ("slip+noFAST", dict(slip=SLIP, drop_after=FAST)),
                           ("no_dK", dict(drop_after={W})), ("noTOP10", dict(drop_after=TOP.get(Lm, set())))):
                if nm == "noTOP10" and not TOP: continue
                o = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015, **kw); d[nm] = o["eos1"]["pnl"] if o else None
            r[Lm] = d
        out[m] = (c["bt"], r)
    return out
def run_all():
    res = {}
    with Pool(12) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    return res
if __name__ == "__main__":
    res = run_all()
    # top-10 after-us buyers over ALL fills of all sets (per landing), then a second pass with them removed
    for Lm in (45, 75):
        cnt = collections.Counter(u for _, r in res.values() if Lm in r and not r[Lm]["fail"] for u in r[Lm]["buyers"])
        TOP[Lm] = {u for u, _ in cnt.most_common(10)}
    res = run_all()
    OUT = {"slip_file_lines": len(SLIP), "fast_snipers": len(FAST), "top10": {Lm: sorted(v) for Lm, v in TOP.items()}}
    print(f"slip limits loaded: {len(SLIP)} follower buys | FAST snipers: {len(FAST)} | top-10 after-us buyers (L75): {[u[:6] for u in sorted(TOP[75])]} | dK among them: {W in TOP[75]}")
    for nm, sset in SETS.items():
        for Lm in (45, 75):
            v = sorted([res[m] for m in sset if m in res and Lm in res[m][1]], key=lambda x: x[0])
            if not v: continue
            t0, t1 = v[0][0], v[-1][0]; mid = t0 + (t1 - t0) / 2
            fills = [(bt, r[Lm]) for bt, r in v if not r[Lm]["fail"]]; nfail = len(v) - len(fills)
            cell = {}
            for k in ("base", "slip", "noFAST", "slip+noFAST", "noTOP10", "no_dK"):
                xs = [(bt, d[k]) for bt, d in fills if d.get(k) is not None]
                tot = sum(x for _, x in xs) - 0.005 * nfail; h1 = sum(x for bt, x in xs if bt < mid) - 0.005 * sum(1 for bt, r in v if r[Lm]["fail"] and bt < mid)
                cell[k] = (round(tot, 2), round(h1, 2), round(tot - h1, 2))
            noout = sum(d["no_out_buy"] for _, d in fills) / max(1, len(fills))
            print(f"{nm:38} L{Lm}: fills {len(fills)}/{len(v)} | " + " | ".join(f"{k} {a:+.2f} ({b:+.2f}/{c:+.2f})" for k, (a, b, c) in cell.items()) + f" | fills with NO outside buy before our sell {noout:.0%}")
            OUT[f"{nm} L{Lm}"] = dict(fills=len(fills), n=len(v), no_out_buy=round(noout, 3), **{k: v_ for k, v_ in cell.items()})
    json.dump(OUT, open(f"{HERE}/rescore.json", "w"), indent=1)
