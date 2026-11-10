#!/usr/bin/env python3
"""EXITPICK step 0 (coordinator request 11-03): exit decision models beside exit125's "own delay" one.
 clock : the timer fires exactly at fill + X (+1 ms engine), a true clock (what a timer thread would do)
 tokev : the timer fires at the token's own first trade at/after fill + X (+1 ms), cap X + 500 ms (the loop's 500 ms timeout)
 (the real engine: tick() runs on every executed pump.fun arrival (any token) or after 500 ms of feed silence -> own/rs in cf.json)
Silent-token rules (decision point fill + 125 ms, the engine sees tape trades with t <= fill + 125 - D):
 not silent -> t125 (the same model's)
 R3a: silent -> wait for the token's next trade (any side), sell at it (+1 ms + D)
 R3b: silent -> wait for the next trade; a buy -> sell at it; a sell -> keep holding, sell at the next BUY seen (cap 2000 ms)
 R3c: silent -> wait for the next trade; a buy -> sell at it; a sell -> sell at once too, but if it is a >= 6% holder sell (fl B) we already lost: same
      (R3c = R3a with the cap 2000)  [kept for the record only]
 R3d: silent -> next trade; buy -> sell; sell -> hold to 1000 ms (clock)
TP/SL marks stay active everywhere. Landing = decision + the fill's own decision->land lag. Followers -20% variant too.
Out: /home/it/sniper-data/filters3/exitpick/alt.json  {sig: {...}}"""
import json, sys, os
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/exit125")
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "x4_head.py")).read())   # x4_cf.py's set-up + functions (unchanged copy)
OUT = "/home/it/sniper-data/filters3/exitpick/alt.json"
CAP = 2000.0

def decide_at(x, P, d, lag, fc, marks):
    why = "time"
    for t, v, i in marks:
        if t >= d: break
        if v >= 1.2 or v <= 0.8:
            d, why = t, ("tp" if v >= 1.2 else "sl"); break
    land = d + lag * 1e6
    return why, d, land, price(x, P, land, fc)

res = {}
for x in F:
    P = X.prep(x)
    if not P or not x["exit"]: continue
    s = x["sells"][0]; ex = x["exit"]
    P["cov_ms"], _ = extend(x, P)
    lag = (s["t"] - ex["t"]) / 1e6
    real = ((x["realized"] or {}).get("pnl", 0) + ((x["ata"] or {}).get("delta", 0) if (x["ata"] or {}).get("ok") else 0)) / 1e9
    g0 = s["sol"]
    own = {x["sig"], s["sig"]}
    others = sorted((a for i, a in enumerate(P["tr"]) if i > P["fi"] and a["sig"] not in own and not a.get("raw")), key=lambda a: a["t"])
    o = dict(run=x["run"])
    for fc in (0.0, 0.2):
        sfx = "_fc" if fc else ""
        marks = sorted(X.value_path(P, x["spend"], follow_cut=fc))
        pn = lambda r: None if r[3] is None else real + (r[3] - g0) * (1 - FEE) / 1e9
        # early exits for the risk-flag rows: 'first chance' (clock, fill + 1 ms) and 50 / 75 ms (own delay and clock)
        if ex["why"] == "time-ms": dly = (ex["t"] - x["t"]) / 1e6 - x["timer"]
        else:
            dmin = (ex["t"] - x["t"]) / 1e6 - x["timer"]
            cand = sorted(p[0] for p in allp if p[0] > dmin); dly = cand[len(cand) // 2] if cand else dmin + 1.0
        for val in (1, 50, 75):
            o[f"clock{val}{sfx}"] = pn(decide_at(x, P, x["t"] + (val + 1) * 1e6, lag, fc, marks))
            if val > 1: o[f"own{val}{sfx}"] = pn(decide_at(x, P, x["t"] + (val + dly) * 1e6, lag, fc, marks))
        for val in TIMERS:
            T = x["t"] + val * 1e6
            o[f"clock{val}{sfx}"] = pn(decide_at(x, P, T + 1e6, lag, fc, marks))
            nx = next((a["t"] for a in others if a["t"] >= T), None)
            d = min(nx + 1e6, T + 500e6) if nx is not None else T + 500e6
            o[f"tokev{val}{sfx}"] = pn(decide_at(x, P, d, lag, fc, marks))
        for D in (0, 15, 30):
            C = x["t"] + (125 - D) * 1e6
            silent = not any(x["t"] < a["t"] <= C for a in others)
            o[f"silent{D}"] = silent
            if not silent: continue
            after = [a for a in others if a["t"] > C]
            cap = x["t"] + CAP * 1e6
            first = after[0] if after else None
            # R3a: sell at the next trade
            d = min(first["t"] + (1 + D) * 1e6, cap) if first else cap
            o[f"r3a_{D}{sfx}"] = pn(decide_at(x, P, max(d, x["t"] + 125e6), lag, fc, marks))
            # R3b: sell at the next BUY
            nb = next((a for a in after if a["buy"]), None)
            d = min(nb["t"] + (1 + D) * 1e6, cap) if nb else cap
            o[f"r3b_{D}{sfx}"] = pn(decide_at(x, P, max(d, x["t"] + 125e6), lag, fc, marks))
            # R3d: next trade buy -> sell; sell -> hold to 1000 ms
            if first and first["buy"]: d = min(first["t"] + (1 + D) * 1e6, cap)
            else: d = x["t"] + 1000e6
            o[f"r3d_{D}{sfx}"] = pn(decide_at(x, P, max(d, x["t"] + 125e6), lag, fc, marks))
            if not fc:
                o[f"next_{D}"] = None if not first else dict(ms=(first["t"] - x["t"]) / 1e6, buy=first["buy"], sol=first["sol"] / 1e9, fl=first.get("fl", ""))
    res[x["sig"]] = o
json.dump(res, open(OUT, "w"))
print("fills", len(res))
