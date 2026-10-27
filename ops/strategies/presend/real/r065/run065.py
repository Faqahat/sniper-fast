#!/usr/bin/env python3
"""REPLAY_065 main: every live fill of AMS runs 24 and 25 replayed on the real chain sequence at other sizes.
  validation : the live sizes (0.34 pre-send, 0.35 regular) -> must reproduce the chain, trade by trade
  main       : 0.65 SOL (both types), 0.50 as a midpoint
  effects    : own price impact only (followers forced to fill, live exits) -> + followers' own limits -> + the engine's exit rule
  stress     : 20% of later buys dropped at random (N draws, both sizes); CPI followers never fail
Outputs /home/moiz/sniper-data/replay065/results.json (+ per-trade rows). Replay numbers are INFERRED; live ones MEASURED."""
import sys, json, pickle, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import core, positions as PO, pmath as PM

BASE = core.BASE
S65, S50, S100 = 650_000_000, 500_000_000, 1_000_000_000
SIZES = {"s50": S50, "s65": S65, "s100": S100}


def run_set(D, P, size_fn, delays, **kw):
    out = []
    for p in P:
        r = PO.replay(D, p, size_fn(p), delays, **kw)
        out.append(r)
    return out


def summ(P, R):
    """fills, wins, P&L SOL (realized as the engine books it)"""
    f = [(p, r) for p, r in zip(P, R) if r["filled"]]
    pn = [r["pnl"] for _, r in f]
    return dict(fills=len(f), wins=sum(1 for x in pn if x > 0), pnl=sum(pn) / 1e9, lost=len(P) - len(f))


def main(draws=200):
    t0 = time.time()
    D = core.Data()
    PS, RG, RF = pickle.load(open(f"{BASE}/pos_cal.pkl", "rb"))
    delays = json.load(open(f"{BASE}/delays.json"))["median"]
    live_size = lambda p: p.spend
    s65 = lambda p: S65
    s50 = lambda p: S50
    groups = {}
    for run in ("r24", "r25"):
        groups[(run, "ps")] = [p for p in PS if p.run == run]
        groups[(run, "reg")] = [p for p in RG if p.run == run]
    res = dict(groups={}, trades=[])
    for key, P in groups.items():
        run, kind = key
        g = {}
        live = dict(fills=len(P), wins=sum(1 for p in P if p.realized > 0), pnl=sum(p.realized for p in P) / 1e9)
        g["live"] = live
        RL = run_set(D, P, live_size, delays)
        g["val"] = summ(P, RL)
        err = np.array([r["pnl"] - p.realized for p, r in zip(P, RL)])
        g["val_err"] = dict(exact=int((err == 0).sum()), n=len(err), med_abs=float(np.median(abs(err))) / 1e9, max_abs=float(abs(err).max()) / 1e9,
                            exits_match=sum(1 for p, r in zip(P, RL) if r.get("why") == p.exit_why), sells_live=sum(1 for r in RL if r.get("sell_src") == "live"))
        R65 = run_set(D, P, s65, delays); R50 = run_set(D, P, s50, delays)
        g["s65"] = summ(P, R65); g["s50"] = summ(P, R50)
        # effects at 0.65: own impact only (followers never fail, live exit) -> + follower limits (live exit) -> + exit rule (= main)
        R65a = [PO.replay(D, p, S65, delays, force_live_exit=True, nolim=True) for p in P]
        R65b = [PO.replay(D, p, S65, delays, force_live_exit=True) for p in P]
        R65bf = [PO.replay(D, p, S65, delays, force_live_exit=True, fmode="fixed") for p in P]
        g["eff"] = dict(impact_only=summ(P, R65a), followers=summ(P, R65b), followers_fixed=summ(P, R65bf), full=g["s65"],
                        naive_scale=live["pnl"] * (S65 / P[0].spend) if P else 0.0)
        # followers priced out before our sell at 0.65 / exits that changed
        g["dropped"] = dict(n=sum(sum(1 for k, why in r.get("dropped_all", []) if why == "slip" and (p.rows[k]["s"], p.rows[k]["i"]) < r["sell_pos"]) for p, r in zip(P, R65) if r["filled"]),
                            pos=sum(1 for p, r in zip(P, R65) if r["filled"] and any(why == "slip" and (p.rows[k]["s"], p.rows[k]["i"]) < r["sell_pos"] for k, why in r.get("dropped_all", []))),
                            sol=sum(p.rows[k]["tr"]["sol"] for p, r in zip(P, R65) if r["filled"] for k, why in r.get("dropped_all", []) if why == "slip" and p.rows[k]["kind"] == "trade" and p.rows[k]["tr"]["buy"] and (p.rows[k]["s"], p.rows[k]["i"]) < r["sell_pos"]) / 1e9,
                            resurrected=sum(r.get("resurrected", 0) for r in R65 if r["filled"]))
        g["exit_matrix"] = dict(collections.Counter(f"{p.exit_why}->{r.get('why')}" for p, r in zip(P, R65) if r["filled"]))
        # price impact numbers (MEASURED live entry vs INFERRED 0.65 entry): SOL per token paid, relative
        prem = [((S65 / r["q"]) / (p.spend / p.tokens) - 1.0) for p, r in zip(P, R65) if r["filled"]]
        g["entry_premium_pct"] = [float(np.percentile(prem, q)) * 100 for q in (10, 50, 90)] if prem else None
        # stress: 20% fewer later buyers (N draws), at the live size and at 0.65; CPI followers never fail
        rng = np.random.default_rng(65)
        cut_live = []; cut65 = []
        for d in range(draws):
            sd = int(rng.integers(1 << 31))
            r1 = np.random.default_rng(sd); r2 = np.random.default_rng(sd)
            cut_live.append(sum(PO.replay(D, p, p.spend, delays, cut=0.2, rng=r1)["pnl"] for p in P) / 1e9)
            cut65.append(sum((lambda r: r["pnl"] if r["filled"] else 0)(PO.replay(D, p, S65, delays, cut=0.2, rng=r2)) for p in P) / 1e9)
        band = lambda x: dict(mean=float(np.mean(x)), p5=float(np.percentile(x, 5)), p95=float(np.percentile(x, 95))) if len(x) else None
        g["cut20_live"] = band(cut_live); g["cut20_65"] = band(cut65)
        g["cpi_free_65"] = summ(P, run_set(D, P, s65, delays, cpi_free=True))
        R65f = run_set(D, P, s65, delays, fmode="fixed")
        g["fixed65"] = summ(P, R65f)
        g["fixed50"] = summ(P, run_set(D, P, s50, delays, fmode="fixed"))
        g["dropped_fixed"] = sum(sum(1 for k, why in r.get("dropped_all", []) if why == "slip" and (p.rows[k]["s"], p.rows[k]["i"]) < r["sell_pos"]) for p, r in zip(P, R65f) if r["filled"])
        g["requote_rows"] = sum(1 for p in P for r in p.rows if r.get("requote") and (r["s"], r["i"]) < p.sell_pos)
        g["follower_rows"] = sum(1 for p in P for r in p.rows if r["kind"] == "trade" and (r["s"], r["i"]) < p.sell_pos)
        g["sizes"] = {}
        for nm, SZ in SIZES.items():
            Rm = run_set(D, P, lambda p: SZ, delays)
            gs = dict(main=summ(P, Rm), fixed=summ(P, run_set(D, P, lambda p: SZ, delays, fmode="fixed")),
                      adaptive=summ(P, run_set(D, P, lambda p: SZ, delays, fmode="adaptive")),
                      dropped=sum(sum(1 for k, why in r.get("dropped_all", []) if why == "slip" and (p.rows[k]["s"], p.rows[k]["i"]) < r["sell_pos"]) for p, r in zip(P, Rm) if r["filled"]),
                      exits=dict(collections.Counter(f"{p.exit_why}->{r.get('why')}" for p, r in zip(P, Rm) if r["filled"])),
                      pertrade=[(r["pnl"] / 1e9 if r["filled"] else None) for r in Rm])
            cc = []
            rngs = np.random.default_rng(1000 + SZ // 10_000_000)
            for d in range(draws):
                r1 = np.random.default_rng(int(rngs.integers(1 << 31)))
                cc.append(sum((lambda r: r["pnl"] if r["filled"] else 0)(PO.replay(D, p, SZ, delays, cut=0.2, rng=r1)) for p in P) / 1e9)
            gs["cut20"] = band(cc)
            g["sizes"][nm] = gs
        res["groups"][f"{run}:{kind}"] = g
        for p, rl, r5, r6 in zip(P, RL, R50, R65):
            res["trades"].append(dict(run=run, kind=kind, seg=p.seg, mint=p.mint, t=p.t, live=p.realized / 1e9, val=rl["pnl"] / 1e9, s50=(r5["pnl"] / 1e9 if r5["filled"] else None),
                                      s65=(r6["pnl"] / 1e9 if r6["filled"] else None), why_live=p.exit_why, why65=r6.get("why"), sell65=r6.get("sell_src"),
                                      drop65=sum(1 for k, why in r6.get("dropped_all", []) if why == "slip" and (p.rows[k]["s"], p.rows[k]["i"]) < r6["sell_pos"]) if r6["filled"] else None,
                                      n_between=sum(1 for r in p.rows if r["kind"] == "trade" and (r["s"], r["i"]) < p.sell_pos),
                                      s100=g["sizes"]["s100"]["pertrade"][P.index(p)],
                                      buy_pos=list(p.buy_pos), sell_pos=list(p.sell_pos), costs=p.costs / 1e9, spend=p.spend / 1e9, tokens=p.tokens, q65=r6.get("q")))
        print(key, "live %+.4f val %+.4f 0.65 %+.4f 0.50 %+.4f | cut20 live %+.4f 0.65 %+.4f | %.0fs" % (live["pnl"], g["val"]["pnl"], g["s65"]["pnl"], g["s50"]["pnl"],
              g["cut20_live"]["mean"] if g["cut20_live"] else 0, g["cut20_65"]["mean"] if g["cut20_65"] else 0, time.time() - t0), flush=True)
    json.dump(res, open(f"{BASE}/results.json", "w"), indent=1, default=float)
    print("wrote results.json", f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
