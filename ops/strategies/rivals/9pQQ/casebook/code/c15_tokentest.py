#!/usr/bin/env python3
"""Automatic per-token verdicts for the standard hypotheses (support s / contradict c / untested u) + one-line trip summary.
usage: c15_tokentest.py RUN MINT8 [--mark]   (marks the ledger when --mark)"""
import sys, json, gzip, glob, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/rivals/9pQQ/casebook/code")
D = "/home/moiz/sniper-data/rivals/9pQQ/casebook"
run, m8 = sys.argv[1], sys.argv[2]
R = [json.loads(l) for l in gzip.open(glob.glob(f"{D}/tapes/{run}/{m8}*.ev.jsonl.gz")[0], "rt")]
own = [k for k, r in enumerate(R) if r["own"]]
trips = list(zip(own[::2], own[1::2]))
E = [r for r in R if not r["own"] and not r["hold"] and r["age"] >= 8 and (r["since_sell"] is None or r["since_sell"] >= 2)]
tk = [r for r in E if r.get("trig") == "B"]; sk = [r for r in E if r.get("trig") != "B"]
H = [r for r in R if not r["own"] and r["hold"]]
hs = [r for r in H if r.get("trig") == "S"]; hn = [r for r in H if r.get("trig") != "S"]
def med(xs): xs = [x for x in xs if x is not None]; return float(np.median(xs)) if xs else None
def share(xs, f): return (sum(1 for x in xs if f(x)) / len(xs)) if xs else None
V = {}
def cmp(h, a, b, thr, inv=False):
    if a is None or b is None or len(tk) < 2: V[h] = ("u", None); return
    d = (a - b) * (-1 if inv else 1)
    V[h] = ("s" if d > thr else ("c" if d < -thr else "u"), f"{a:.3g} vs {b:.3g}")
cmp("HB04", med([r["sol"] for r in tk]), med([r["sol"] for r in sk]), 0.05)
cmp("HB05", share(tk, lambda r: r["buy"]), share(sk, lambda r: r["buy"]), 0.1)
cmp("HB14", share(tk, lambda r: (r["ch10"] or 0) <= -3 and r["buy"]), share(sk, lambda r: (r["ch10"] or 0) <= -3 and r["buy"]), 0.1)
cmp("HB17", med([r["dd450"] for r in tk]), med([r["dd450"] for r in sk]), 3, inv=True)
cmp("HB19", med([abs(r["ch10"] or 0) for r in tk]), med([abs(r["ch10"] or 0) for r in sk]), 2)
cmp("HB20", share(tk, lambda r: (r["ch10"] or 0) >= 3 and r["nf10"] >= 1 and r["ns10"] == 0), share(sk, lambda r: (r["ch10"] or 0) >= 3 and r["nf10"] >= 1 and r["ns10"] == 0), 0.1)
cmp("HB15", med([r["ucnt"] for r in tk]), med([r["ucnt"] for r in sk]), 2)
V["HB23"] = ("s", "wake entries %d" % sum(1 for r in tk if r["n75"] <= 1)) if any(r["n75"] <= 1 for r in tk) else ("u", None)
cmp("HS03", med([r.get("since_ob") for r in hs]), med([r.get("since_ob") for r in hn]), 3) if hs else None
cmp("HS04", share(hs, lambda r: not r["buy"]), share(hn, lambda r: not r["buy"]), 0.15) if hs else None
cmp("HS09", med([r.get("dd_peak") for r in hs]), med([r.get("dd_peak") for r in hn]), 1.5) if hs else None
caps = sum(1 for a, b in trips if R[b]["bt"] - R[a]["bt"] >= 295)
V["HS01"] = ("s", f"{caps} cap exits")
# burst exits: outside buy SOL in the 3 slots before the sell >= 2 and in profit
nb = 0
for a, b in trips:
    if R[b]["bt"] - R[a]["bt"] >= 295: continue
    b3 = sum(r["sol"] for r in R[a + 1:b] if not r["own"] and r["buy"] and r["s"] >= R[b]["s"] - 3)
    if b3 >= 2 and R[b]["mc"] > R[a]["mc"]: nb += 1
V["HS10"] = ("s" if nb >= 1 else "u", f"{nb} burst exits")
st_ = sum(1 for r in hs if (r.get("since_ob") or 0) >= 15)
V["HS11"] = ("s" if hs and st_ / len(hs) >= 0.3 else ("c" if hs and st_ == 0 and len(hs) >= 4 else "u"), f"{st_}/{len(hs)} stale(>=15) exits")
if trips:
    ls = R[trips[-1][1]]
    aft = [r for r in R if r["s"] > ls["s"] and not r["own"]]
    nbig = sum(1 for r in aft if r["buy"] and r["sol"] >= 0.5)
    V["HB07"] = ("s" if nbig < 3 else "c", f"{nbig} outside buys>=0.5 after last exit")
    mxb = max(R[a]["mc"] for a, b in trips); mxa = max([r["mc"] for r in aft] or [0])
    V["HK03"] = ("s", f"quit; after-exit peak mc {mxa:.0f} > max entry mc {mxb:.0f}") if nbig >= 5 and mxa > mxb * 1.1 else ("u", None)
V["HB01"] = ("s", None); V["HB02"] = ("s", None) if min(R[a]["age"] for a, b in trips) >= 8 else ("c", "age<8"); V["HB03"] = ("s", None)
V["HK01"] = ("s", f"take {100*len(tk)/max(1,len(E)):.1f}%")
net = 0
for a, b in trips: net += (R[b]["sol"] - R[a]["sol"])
era = "V3" if R[own[0]]["bt"] >= 1793388600 else ("V2" if R[own[0]]["bt"] >= 1793268000 else "V1")
print(f"{m8} {era} trips {len(trips)} gross~{net:+.2f} first-age {R[own[0]]['age']} | " + " ".join(f"{h}:{v[0]}" for h, v in sorted(V.items())))
print("   " + "; ".join(f"{h} {v[1]}" for h, v in sorted(V.items()) if v[1]))
if "--mark" in sys.argv:
    from ledger import load, save, mark
    L = load()
    if m8 not in L["tokens"]: L["tokens"].append(m8)
    for h, (v, n) in V.items():
        if h in L["H"]: mark(L, h, m8, v, ("auto: " + n) if n and v != "u" else None)
    L["meta"].setdefault("eras", {})[m8] = era
    save(L)
