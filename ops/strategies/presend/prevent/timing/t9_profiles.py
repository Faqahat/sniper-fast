#!/usr/bin/env python3
"""TIMING step 9 [MEASURED, descriptive]: exit-rule PROFILE of the wallets that matter, from their whole recorded history
(10-24 19:25 -> 10-30 03:55 PKT, all tokens): timer (tight first-sell hold), TP (tight sell multiple above 1), stop-loss (first sells
below 0.85x), ladder (>= 3 sells, partial first sell), full-dump share, creators' dev timer (create -> first sell) and curve SOL at it.
Groups: main in-hold seller of the 146 big losses; every visible holder (>= 2%) at our fills; the r38 six.
Also: the r38 six losses with the online flags (signing-time hazard, landing-time hazard) of each seller."""
import pickle, json, collections, sys
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/prevent/timing")
import tlib as T
D = "/home/it/sniper-data/prevent/timing"
FC = pickle.load(open(f"{D}/fillctx.pkl", "rb")); R = pickle.load(open(f"{D}/pairs.pkl", "rb"))
P = T.P; Sx = np.load(f"{D}/sells.npy")
o = np.argsort(Sx["u"], kind="stable"); Sx = Sx[o]; SB = np.searchsorted(Sx["u"], np.arange(len(T.I["user"]) + 1))


def profile(w):
    u = T.Ui.get(w)
    if u is None: return None
    X = P[T.UB[u]:T.UB[u + 1]]; X = X[X["s1"] >= 0]
    if len(X) < 3: return dict(n=int(len(X)), cls="few")
    d = (X["s1"] - X["b0"]).astype(float); mu = X["mult"][np.isfinite(X["mult"])]
    q = np.percentile(d, [25, 50, 75]); mq = np.percentile(mu, [25, 50, 75]) if len(mu) else [np.nan] * 3
    ss = Sx[SB[u]:SB[u + 1]]
    ns = collections.Counter(zip(ss["m"].tolist()))
    multi = np.mean([c >= 3 for c in ns.values()]) if ns else 0
    pr = dict(n=int(len(X)), h25=q[0], h50=q[1], h75=q[2], iqr=q[2] - q[0], m25=mq[0], m50=mq[1], m75=mq[2], miqr=mq[2] - mq[0],
              full=float((X["frac"] >= 0.95).mean()), sl=float((mu < 0.85).mean()) if len(mu) else np.nan, ladder=float(multi),
              le2=float((d <= 2).mean()), ncre=int(X["cre"].sum()))
    if pr["ncre"]:
        C = X[X["cre"] == 1]; dc = (C["s1"] - C["b0"]).astype(float)
        pr.update(cre_h50=float(np.median(dc)), cre_h25=float(np.percentile(dc, 25)), cre_h75=float(np.percentile(dc, 75)),
                  cre_v50=float(np.median(C["vpre"]) / 1e9))
    timer = pr["iqr"] <= max(2.0, 0.25 * pr["h50"])
    tp = pr["miqr"] <= 0.10 and pr["m50"] > 1.05
    cls = []
    if timer: cls.append("TIMER")
    if tp: cls.append("TP")
    if pr["sl"] >= 0.5: cls.append("SL-ish")
    if pr["ladder"] >= 0.5: cls.append("LADDER")
    pr["cls"] = "+".join(cls) if cls else "none"
    return pr


big = [f for f in FC if f["pnl"] is not None and f["pnl"] <= -0.05 and f["inhold"]]
mains = []
for f in big:
    w, v = max(f["inhold"].items(), key=lambda kv: kv[1][0]); mains.append((f, w, v))
PR = {}
for _, w, _ in mains: PR.setdefault(w, profile(w))
vis = sorted({r["wallet"] for r in R})
for w in vis: PR.setdefault(w, profile(w))
def table(ws, title):
    c = collections.Counter(); n = 0
    for w in ws:
        p = PR.get(w)
        if not p: c["no history"] += 1; continue
        n += 1
        for k in p["cls"].split("+"): c[k] += 1
    print(f"{title}: wallets {len(ws)}", dict(c.most_common()))
table([w for _, w, _ in mains], "BIG-LOSS main sellers (one per loss)")
table(sorted({w for _, w, _ in mains}), "BIG-LOSS main sellers (unique)")
table(vis, "visible holders at our fills (unique)")
sold = sorted({r["wallet"] for r in R if r["y_hold"]}); table(sold, "visible holders that sold in our hold (unique)")
# median hold of timer sellers in big losses
print("\nbig-loss main sellers: hold-clock IQR (slots) quantiles", np.nanpercentile([PR[w]["iqr"] for _, w, _ in mains if PR.get(w) and "iqr" in PR[w]], [10, 25, 50, 75, 90]).round(1))
print("big-loss main sellers: median first-sell hold (slots) quantiles", np.nanpercentile([PR[w]["h50"] for _, w, _ in mains if PR.get(w) and "h50" in PR[w]], [10, 25, 50, 75, 90]).round(1))
print("big-loss main sellers: median sell multiple quantiles", np.nanpercentile([PR[w]["m50"] for _, w, _ in mains if PR.get(w) and "m50" in PR[w]], [10, 25, 50, 75, 90]).round(2))
# creators
cr = sorted({f["creator"] for f, w, v in mains if w == f["creator"]})
print("\nbig-loss creators who dumped on us:", len(cr))
for w in cr:
    p = PR.get(w) or {}
    print(f"  {w[:8]} n={p.get('n')} created={p.get('ncre')} dev-timer q25/50/75 slots={p.get('cre_h25')}/{p.get('cre_h50')}/{p.get('cre_h75')} curveSOL@sell={p.get('cre_v50')} cls={p.get('cls')}")
json.dump({w: p for w, p in PR.items() if p}, open(f"{D}/profiles.json", "w"), default=float)
# r38 six
print("\nr38 SIX LOSSES: sellers into our hold, their profile and the online timer flags")
idx = {(r["run"], r["ses"], r["kind"], r["w"], r["wallet"]): r for r in R}
F2 = pickle.load(open(f"{D}/direct2_flags.pkl", "rb"))
six = [f for f in FC if f["run"] == "A38" and f["pnl"] is not None and f["pnl"] <= -0.04]
for f in sorted(six, key=lambda f: f["pnl"]):
    k = (f["run"], f["ses"], f["kind"], f["w"])
    print(f"{f['mint'][:8]} {f['kind']:5s} pnl {f['pnl']:+.3f}  a2_X6_t0.3 {'BLOCK' if F2['a2_X6_t0.3_open'][k][0] else 'pass'}  "
          f"b2_t0.5 {'BLOCK' if F2['b2_whale_t0.5_open'][k][0] else 'pass'}  a2_X3_t0.3 {'BLOCK' if F2['a2_X3_t0.3_open'][k][0] else 'pass'}")
    for w, v in sorted(f["inhold"].items(), key=lambda kv: -kv[1][0])[:4]:
        r = idx.get(k + (w,)); p = PR.get(w) or {}
        hs = None
        if f["Hs"] and w in f["Hs"] and f["Hs"][w][1] is not None:
            S = f["sign_slot"]; hs = T.hz(w, S, f["mint"], S - f["Hs"][w][1], 3)
        print(f"    {w[:8]} sold {v[0]/1e9:5.2f} SOL | visible {'%.1f%%' % r['pct'] if r else 'no'} hold {r['hold'] if r else '-'} slots | "
              f"hz2@fill {r.get('hz2', float('nan')) if r else float('nan'):.2f} (n {r.get('hzn2') if r else '-'}) | hz3@sign {hs[0] if hs and hs[0] is not None else float('nan'):.2f} | "
              f"past n={p.get('n')} hold q25/50/75={p.get('h25')}/{p.get('h50')}/{p.get('h75')} mult50={p.get('m50', float('nan')):.2f} cls={p.get('cls')}")
