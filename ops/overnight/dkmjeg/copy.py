#!/usr/bin/env python3
# READ-ONLY, offline replay (no money): can WE use dKMjeG? Our mechanics = 0.5 SOL, land 45 or 75 ms after the create
# (block-order placement with failed-tx anchors, R2 launches with our engine's timeline), 1% price guard vs the
# post-bundle price (fail = 0.005 SOL fee), sell everything at the end of the next slot (allres.json, precomputed with
# rp.py by core/precompute_all.py). R1 rows use the block-position proxy (no timelines) and are shown separately.
#  (a) oracle: its attempted launches;  (b) walk-forward deployer list from its attempts (+ quality gate);
#  (m) walk-forward model of its selection (create-time features, trained on R1 only) -> top-k% of R2 launches.
import sys, json, collections, statistics as S, math
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
import numpy as np
L = rp.load_launches(); AR = json.load(open("/home/moiz/sniper/ops/overnight/core/allres.json"))
C = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/coll.json"))
ATT = {m for m, v in C.items() if "dk" in v}; FIL = {m for m, v in C.items() if "dk" in v and "bslot" in v["dk"]}
def evals(ms, Lm, run="R2", B="0.5"):
    v = sorted([(AR[m]["bt"], (AR[m][Lm].get(B) if AR[m][Lm]["ok"] else -0.005)) for m in ms if m in AR and AR[m]["run"] == run and Lm in AR[m]], key=lambda x: x[0])
    v = [(t, x) for t, x in v if x is not None]
    if not v: return None
    t0, t1 = v[0][0], v[-1][0]; mid = t0 + (t1 - t0) / 2; a = sum(x for t, x in v if t < mid); tot = sum(x for _, x in v)
    nf = sum(1 for _, x in v if x != -0.005)
    return dict(tot=round(tot, 2), h1=round(a, 2), h2=round(tot - a, 2), fills=nf, n=len(v), per_fill=round(sum(x for _, x in v if x != -0.005) / max(1, nf), 4))
def line(name, ms):
    cells = []
    for run in ("R2", "R1"):
        for Lm in ("45", "75"):
            e = evals(ms, Lm, run)
            cells.append(f"{run} L{Lm}: " + (f"{e['tot']:+6.2f} ({e['h1']:+.2f}/{e['h2']:+.2f}) fills {e['fills']}/{e['n']}" if e else "-"))
    print(f"{name:52} " + " | ".join(cells))
    return {f"{run}_{Lm}": evals(ms, Lm, run) for run in ("R2", "R1") for Lm in ("45", "75")}
OUT = {}
print("(a) ORACLE (needs its decision before we land; it is not visible to us in time):")
OUT["oracle_attempts"] = line("its attempted launches (filled or failed)", ATT)
OUT["oracle_fills"] = line("its filled launches", FIL)
OUT["oracle_failed_only"] = line("its failed-only launches", ATT - FIL)
OUT["all_launches"] = line("ALL launches (reference)", set(AR))
# (b) walk-forward deployer list + gate (decision uses only launches before; our own simulated result counted 60 s later)
def wf(Lm, k=2, rate=0.10, gate=None, run_filter=None):
    ev = sorted((c["bt"], m) for m, c in L.items() if c.get("bt"))
    na = collections.Counter(); nl = collections.Counter(); hist = collections.defaultdict(list); pend = []; pick = set()
    for bt, m in ev:
        while pend and pend[0][0] <= bt:
            _, d, v = pend.pop(0); hist[d].append(v)
        d = L[m]["user"]
        listed = na[d] >= k and (nl[d] == 0 or na[d] / nl[d] >= rate)
        ok_gate = True
        if gate:
            h = hist[d]; ok_gate = not (len(h) >= gate[0] and S.mean(h) < gate[1])
        if listed and ok_gate: pick.add(m)
        r = AR.get(m)
        if r and Lm in r and r[Lm]["ok"] and r[Lm].get("0.5") is not None:
            pend.append((bt + 60, d, r[Lm]["0.5"])); pend.sort()
        nl[d] += 1
        if m in ATT: na[d] += 1
    return pick
print("\n(b) WALK-FORWARD deployer list from its attempts (>= 2 attempts and >= 10% of the deployer's launches, counted before each launch):")
for Lm in ("75", "45"):
    p0 = wf(Lm); p1 = wf(Lm, gate=(3, 0.0))
    for nm, p in ((f"list (decided at L{Lm})", p0), (f"list + gate (own fills avg<0 after>=3 -> skip) L{Lm}", p1)):
        cells = []
        for run in ("R2", "R1"):
            e = evals(p, Lm, run)
            cells.append(f"{run} L{Lm}: " + (f"{e['tot']:+6.2f} ({e['h1']:+.2f}/{e['h2']:+.2f}) fills {e['fills']}/{e['n']} per fill {e['per_fill']:+.4f}" if e else "-"))
        print(f"   {nm:56} " + " | ".join(cells))
        OUT[nm] = {run: evals(p, Lm, run) for run in ("R2", "R1")}
# (m) model of its selection trained on R1 only, applied to R2 (top-k% by score)
R = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/sel_rows.json"))
exec(open("/home/moiz/sniper/ops/overnight/dkmjeg/sel2.py").read().split("X = np.array")[0].split("R = json.load")[0])   # imports only
src = open("/home/moiz/sniper/ops/overnight/dkmjeg/sel2.py").read()
g = {}; exec(src[src.index("def f(r):"):src.index("X = np.array")], {"math": math, **g}, g)
exec(src[src.index("def fit("):src.index("tr = run ==")], {"np": np}, g)
X = np.array([g["f"](r) for r in R]); y = np.array([r["att"] for r in R], dtype=float); run = np.array([r["run"] for r in R])
w, mu, sd = g["fit"](X[run == "R1"], y[run == "R1"]); s2 = g["pred"](w, mu, sd, X[run == "R2"])
R2m = [r["m"] for r in R if r["run"] == "R2"]
print("\n(m) MODEL of its picks (create-time features, trained on R1, applied to R2; no copying of its txs):")
for q in (0.01, 0.02, 0.05, 0.10):
    thr = np.quantile(s2, 1 - q); pk = {m for m, sc in zip(R2m, s2) if sc >= thr}
    cells = []
    for Lm in ("45", "75"):
        e = evals(pk, Lm, "R2")
        cells.append(f"R2 L{Lm}: {e['tot']:+6.2f} ({e['h1']:+.2f}/{e['h2']:+.2f}) fills {e['fills']}/{e['n']} per fill {e['per_fill']:+.4f}")
    hit = len(pk & ATT)
    print(f"   top {q:.0%} ({len(pk)} launches, {hit} of them attempted by dK): " + " | ".join(cells))
    OUT[f"model_top{q}"] = {Lm: evals(pk, Lm, "R2") for Lm in ("45", "75")}
json.dump(OUT, open("/home/moiz/sniper/ops/overnight/dkmjeg/copy_ab.json", "w"), indent=1)
