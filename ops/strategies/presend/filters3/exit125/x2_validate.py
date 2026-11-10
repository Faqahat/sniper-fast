#!/usr/bin/env python3
"""EXIT-125v200 step 2: validate the pricing model on every real exit before any counterfactual.
 A exact tape position (state = the trade just before our sell by slot/idx) vs the real sell's gross SOL
 B time placement (state = every other trade that reached us before our sell's rx time) vs the same  <- the counterfactual method
 C net: real realized P&L vs model (gross x (1 - fee) - sell tx costs); implied fee rate
 D engine marks: TP/SL exits re-found from the tape marks; time exits with no earlier TP/SL crossing
 E timer delay (decision - fill - N), F decision->land lag, G tape continuity (vtok chain)"""
import json, statistics as st, collections, sys
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/exit125")
import xlib as X
D = "/home/it/sniper-data/filters3/exit125"
F = json.load(open(f"{D}/fills.json"))["fills"]

def q(a, ps=(0, .05, .25, .5, .75, .95, 1)):
    a = sorted(a)
    return [round(a[int(p * (len(a) - 1))], 4) for p in ps] if a else []

A, B, Bsol, C, fee_rate, Ed, Fl, Fsl, Dm = [], [], [], [], [], collections.defaultdict(list), [], collections.Counter(), collections.Counter()
gaps = collections.Counter(); badk = 0
rows = []
for x in F:
    P = X.prep(x)
    if not P: continue
    tr, fi, si, qq = P["tr"], P["fi"], P["si"], P["q"]
    s = x["sells"][0]
    # A
    pre = tr[si - 1]
    ga = X.gross_out(qq, pre["vsol"], pre["vtok"])
    A.append((ga - s["sol"]) / s["sol"] * 100 if s["sol"] else 0)
    # B
    vsol, vtok, ri, _ = X.state_at(P, s["t"])
    gb = X.gross_out(qq, vsol, vtok)
    B.append((gb - s["sol"]) / s["sol"] * 100); Bsol.append((gb - s["sol"]) / 1e9)
    # C: implied sell-side cost (fee% of gross + fixed)
    r = x["realized"]
    sell_delta = r["pnl"] - r["buy_delta"]
    fixed = (s.get("fee") or 0)
    ss = (x["close"] or {}).get("sell_sigs") or []
    tipish = ss[0][2] if ss and len(ss[0]) > 2 and isinstance(ss[0][2], (int, float)) else 0
    fr = (s["sol"] - sell_delta - fixed - tipish) / s["sol"] * 100 if s["sol"] else None
    if fr is not None: fee_rate.append(fr)
    model_net = s["sol"] * (1 - 0.0125) - fixed - tipish
    C.append((model_net - sell_delta) / 1e9)
    # D marks
    ex = x["exit"]
    vp = X.value_path(P, x["spend"], upto_t=ex["t"] + 1)
    cross = next(((t, v) for t, v, i in vp if v >= 1.2 or v <= 0.8), None)
    if ex["why"] in ("take-profit", "stop-loss"):
        Dm[("tpsl", "found_same_t" if cross and abs(cross[0] - ex["t"]) < 2e6 else ("found_other_t" if cross else "not_found"))] += 1
        if ex.get("value") and cross: Dm[("tpsl_value_err<1%", abs(cross[1] - ex["value"]) < 0.01)] += 1
    elif ex["why"] == "time-ms":
        Dm[("time", "no_cross_before" if not cross else "cross_before")] += 1
        Ed[x["timer"]].append((ex["t"] - x["t"]) / 1e6 - x["timer"])
    # F lag
    Fl.append((s["t"] - ex["t"]) / 1e6); Fsl[s["slot"] - ex["slot"]] += 1
    # G continuity in the first 3 s after the fill
    for i in range(fi + 1, len(tr)):
        a, b = tr[i - 1], tr[i]
        exp = b["vtok"] - (-b["tok"] if b["buy"] else b["tok"])
        if exp != a["vtok"]: gaps["gap"] += 1
        else: gaps["ok"] += 1
    rows.append(dict(run=x["run"], mint=x["mint"], A=A[-1], B=B[-1], Bsol=Bsol[-1], C=C[-1], lag=Fl[-1]))

print(f"fills priced: {len(rows)} of {len(F)}")
print("A exact position, error % of real gross:", q(A), " |err|<0.01%:", sum(abs(a) < 0.01 for a in A))
print("B time placement, error %:", q(B), " |err|<0.1%:", sum(abs(a) < 0.1 for a in B), " |err|<1%:", sum(abs(a) < 1 for a in B))
print("B error SOL: sum %+.4f  mean abs %.5f  p95 abs %.5f" % (sum(Bsol), st.mean(abs(a) for a in Bsol), q([abs(a) for a in Bsol], (.95,))[0]))
print("C model net - real sell delta (SOL):", q(C), "sum %+.4f" % sum(C))
print("implied fee % of gross (after fixed costs):", q(fee_rate))
print("D engine marks:", dict(Dm))
for k, v in Ed.items(): print(f"E timer {k}: decision - fill - N (ms):", q(v))
print("F decision->land lag ms:", q(Fl), " slots:", dict(sorted(Fsl.items())))
print("G vtok chain after fill:", dict(gaps))
json.dump(rows, open(f"{D}/validate_rows.json", "w"))
