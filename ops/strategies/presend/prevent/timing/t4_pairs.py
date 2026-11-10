#!/usr/bin/env python3
"""TIMING step 4 [MEASURED features, ONLINE]: one row per (live fill, visible holder >= 2% just before our buy landed).
Online history of the holder = its positions on OTHER mints whose first buy was before the fill slot; a position whose first sell came
at/after the fill slot is CENSORED at (fill slot - first buy) (no look-ahead).
Features: n past, hold-slot quantiles, timer tightness, empirical timer hazard P(first sell in [h, h+H] | held >= h) for H = 1,2,4 slots
(h = slots this holder has held this mint), sell-multiple quantiles (exec price at first sell / avg buy price), current multiple
(price just before our buy / its avg buy price), share of full first sells, creator flag + creator timer (create -> first sell) history.
Labels: sold inside our hold (our buy landing -> our sell landing), sold within 3 slots after our buy.
Out: /home/it/sniper-data/prevent/timing/pairs.pkl"""
import json, pickle, bisect
import numpy as np
D = "/home/it/sniper-data/prevent/timing"
FC = pickle.load(open(f"{D}/fillctx.pkl", "rb"))
I = json.load(open(f"{D}/hist_ids.json")); Ui = {x: k for k, x in enumerate(I["user"])}; Mi = {x: k for k, x in enumerate(I["mint"])}
P = np.load(f"{D}/pos.npy")
o = np.lexsort((P["b0"], P["u"])); P = P[o]
ub = np.searchsorted(P["u"], np.arange(len(I["user"]) + 1))
SUP = 1e15


def hist(u, S, mint_id):
    a, e = ub[u], ub[u + 1]
    if e <= a: return None
    X = P[a:e]
    k = np.searchsorted(X["b0"], S)          # first buys strictly before S
    X = X[:k]
    X = X[X["m"] != mint_id]
    if len(X) == 0: return None
    done = (X["s1"] >= 0) & (X["s1"] < S)
    dt = np.where(done, X["s1"] - X["b0"], S - X["b0"])
    return X, done, dt


rows = []
for f in FC:
    S = f["slot"]; mid = Mi.get(f["mint"], -1)
    for w, h in f["H"].items():
        u = Ui.get(w)
        r = dict(run=f["run"], ses=f["ses"], kind=f["kind"], w=f["w"], fill_slot=S, mint=f["mint"], wallet=w, pct=h["pct"], creator=h["creator"],
                 whale=h["whale"], clu=h.get("clu", 0), hold=S - h["first"] if h["first"] is not None else None, p696=f["p696"], pnl=f["pnl"],
                 y_hold=(w in f["inhold"]), sell_sol=f["inhold"].get(w, (0, 0, 0))[0] / 1e9, sell_tok=f["inhold"].get(w, (0, 0, 0))[1],
                 y_n3=(w in f["next3"]), n3_sol=f["next3"].get(w, (0, 0, None))[0] / 1e9,
                 n3_slot=(f["next3"][w][2] >> 24) - S if w in f["next3"] else None,
                 hold_slots=f["sell_slot"] - S, cost=h["cost"], bal=h["bal"], p_now=f["p_now"])
        # current multiple: price before our buy / its average buy price (cost basis net of its earlier sells)
        r["mnow"] = (f["p_now"] / (h["cost"] / h["bal"])) if (f["p_now"] and h["cost"] > 0 and h["bal"] > 0) else np.nan
        x = hist(u, S, mid) if u is not None else None
        if x is None:
            r["n"] = 0
        else:
            X, done, dt = x
            hh = r["hold"] if r["hold"] is not None else 0
            r["n"] = int(len(X)); r["n_done"] = int(done.sum())
            d = dt[done]
            if len(d):
                q = np.percentile(d, [10, 25, 50, 75, 90])
                r.update(q10=q[0], q25=q[1], q50=q[2], q75=q[3], q90=q[4], iqr=q[3] - q[1])
                r["le2"] = float((d <= 2).mean()); r["le10"] = float((d <= 10).mean())
                mu = X["mult"][done]; mu = mu[np.isfinite(mu)]
                if len(mu): r.update(m25=float(np.percentile(mu, 25)), m50=float(np.median(mu)), m75=float(np.percentile(mu, 75)))
                r["full"] = float((X["frac"][done] >= 0.95).mean())
                c = X["cre"][done] == 1
                if c.any(): r["cre_n"] = int(c.sum()); r["cre_q50"] = float(np.median(d[c])); r["cre_q25"] = float(np.percentile(d[c], 25)); r["cre_q75"] = float(np.percentile(d[c], 75))
            for H in (1, 2, 4):
                at_risk = (dt >= hh) & (done | (dt >= hh + H))
                ev = done & (dt >= hh) & (dt <= hh + H)
                r[f"hz{H}"] = (ev.sum() + 0.05) / (at_risk.sum() + 1.0)
                r[f"hzn{H}"] = int(at_risk.sum())
        rows.append(r)
pickle.dump(rows, open(f"{D}/pairs.pkl", "wb"))
import collections
print("pairs", len(rows), "with history", sum(1 for r in rows if r["n"] > 0), "sold in hold", sum(r["y_hold"] for r in rows),
      "sold within 3 slots", sum(r["y_n3"] for r in rows))
