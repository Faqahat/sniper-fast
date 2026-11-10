#!/usr/bin/env python3
"""WHO step 8 [POST-HOC, added after seeing PICK/TEST results of the pre-registered 145 rules; counted and labelled post-hoc]:
 G   bias-fixed wallet list: per wallet, running P&L@0.696 of ALL our past live fills where it held >= 3% at arm (any role, sold or not);
     skip if a holder >= 3% at arm has n >= m and sum <= -S.  m {2,3,5} x S {0.05,0.1,0.2}; G-cr = same but only the creator  (18)
 H   cascade dumper (market tape): event = a sell >= 3% supply within 0-2 slots after ANOTHER wallet's sell >= 3% (drop >= 10%) on the same
     mint; skip if a holder >= Y% at arm has >= K events on distinct other mints in the past 24 h.  Y {3,6} x K {1,2,3,5} x trig {incl,excl} (16)
 C0  skip T2 if the whale made 0 big dumps on other tokens in the past 24 h  (1)
Out: rules_posthoc.pkl (same format as rules.pkl)"""
import pickle, json, bisect, collections, itertools, sys
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/prevent/who")
from w5_rules import load, prep, Online, LAG

D = "/home/it/sniper-data/prevent/who"


def main():
    W, F, C, DU, bots = load()
    R = prep(W, F)
    X = pickle.load(open(f"{D}/rules.pkl", "rb")); meta = X["meta"]
    assert len(meta) == len(R) and all(m["mint"] == r["w"]["mint"] and m["t"] == r["t"] for m, r in zip(meta, R))
    live_fills = [r for r in R if r["mode"] == "live" and r["filled"]]
    # G: fair per-wallet running P&L when holding >= 3% at arm
    g_all, g_n, g_cr, g_crn = Online(), Online(), Online(), Online()
    for r in live_fills:
        t = r["w"]["fill_t"] + LAG
        for u, p in r["f"]["hold"].items():
            if p >= 3:
                g_all.add(u, t, r["pnl_s"]); g_n.add(u, t)
        c = r["f"].get("creator")
        if c and r["f"]["hold"].get(c, 0) >= 3: g_cr.add(c, t, r["pnl_s"]); g_crn.add(c, t)
    for o in (g_all, g_n, g_cr, g_crn): o.done()
    # H: cascade events from the market big-sell table
    o = np.lexsort((DU["slot"], DU["mint"]))
    mi, sl, us, dr = DU["mint"][o], DU["slot"][o], DU["user"][o], DU["drop"][o]
    bt = DU["bt"][o]
    ev = collections.defaultdict(list)
    n = len(mi)
    for k in range(1, n):
        j = k - 1
        while j >= 0 and mi[j] == mi[k] and sl[k] - sl[j] <= 2:
            if us[j] != us[k] and dr[j] >= 0.10:
                ev[us[k]].append((int(bt[k]), mi[k])); break
            j -= 1
    for u in ev: ev[u].sort(key=lambda z: z[0])
    evt = {u: [z[0] for z in v] for u, v in ev.items()}
    print("cascade wallets", len(ev), "events", sum(len(v) for v in ev.values()), flush=True)

    def ncas(u, t, mint, N=24):
        ts = evt.get(u)
        if not ts: return 0
        a = bisect.bisect_left(ts, t - N * 3600); b = bisect.bisect_left(ts, t - 1)
        return len({z[1] for z in ev[u][a:b] if z[1] != mint})
    for r in R:
        t = r["t"]; h = r["f"]["hold"]
        r["G"] = [(g_n.n(u, t), g_all.s(u, t)) for u, p in h.items() if p >= 3]
        c = r["f"].get("creator")
        r["Gc"] = (g_crn.n(c, t), g_cr.s(c, t)) if c and h.get(c, 0) >= 3 else (0, 0.0)
        r["H"] = {u: (p, ncas(u, t, r["w"]["mint"])) for u, p in h.items() if p >= 3}
    rules = {}
    for m, S in itertools.product((2, 3, 5), (0.05, 0.1, 0.2)):
        rules[f"G fair-list m{m} S{S}"] = ("G", lambda r, m=m, S=S: any(nn >= m and ss <= -S for nn, ss in r["G"]))
        rules[f"G-cr fair-list creator m{m} S{S}"] = ("G", lambda r, m=m, S=S: r["Gc"][0] >= m and r["Gc"][1] <= -S)
    for Y, K, inc in itertools.product((3.0, 6.0), (1, 2, 3, 5), (True, False)):
        rules[f"H cascade Y{Y} K{K} {'incl' if inc else 'excl'}-trig"] = ("H", lambda r, Y=Y, K=K, inc=inc: any(p >= Y and k >= K for u, (p, k) in r["H"].items() if inc or u != r["w"]["wallet"]))
    rules["C0 whale no dumps 24h (T2)"] = ("C0", lambda r: r["w"]["kind"] == "t2" and r["mode"] in ("live", "paper") and meta_c1[id(r)] == 0)
    meta_c1 = {id(r): m["C1"] for r, m in zip(R, meta)}
    res = {name: (fam, np.array([bool(fn(r)) for r in R])) for name, (fam, fn) in rules.items()}
    pickle.dump({"meta": meta, "res": res}, open(f"{D}/rules_posthoc.pkl", "wb"))
    print("post-hoc rules", len(res))


if __name__ == "__main__":
    main()
