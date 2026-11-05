#!/usr/bin/env python3
"""e1: event exits on the hold tapes. For every single-round position: if a trigger trade by ANOTHER wallet arrives after our fill
was seen and before our real exit decision, we decide to sell at its arrival + REACT ms; the sell lands after this position's own
measured decision->landing delay (tlib). Change in P&L = change in gross proceeds x (1 - sell fee). Other positions unchanged.
Reports DEV / VAL: n fired, wins/losses of the change, SOL, SOL/day, win rate after, w/o top 5 trades."""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/obsstrat")
import tlib
HRS = {"DEV": 74.35, "VAL": 20.61}
REACT = 3e6

def drop_of(p, x, i):
    """price drop % of a sell at tape index i (pre-state = previous trade's post)"""
    if i == 0: return 0.0
    pv = p.tr[i - 1]; pre = pv[8] / pv[9]; post = x[8] / x[9]
    return 100 * (1 - post / pre)

def rules():
    R = {}
    for X in (0.3, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0):
        R[f"sell>={X}"] = (lambda X: lambda p, x, i, st: x[5] == 0 and x[6] >= X * 1e9)(X)
    for Y in (2, 3, 5, 8):
        R[f"selldrop>={Y}%"] = (lambda Y: lambda p, x, i, st: x[5] == 0 and drop_of(p, x, i) >= Y)(Y)
    for X in (1.0, 2.0, 3.0):
        R[f"cumsell>={X}"] = (lambda X: lambda p, x, i, st: x[5] == 0 and st["cs"] >= X * 1e9)(X)
    R["sell_by_B"] = lambda p, x, i, st: x[5] == 0 and "B" in x[10]
    R["sell_by_W"] = lambda p, x, i, st: x[5] == 0 and "W" in x[10]
    R["sell>=1&B"] = lambda p, x, i, st: x[5] == 0 and "B" in x[10] and x[6] >= 1e9
    for X in (0.5, 1.0, 2.0):
        R[f"BUY>={X}(sell into)"] = (lambda X: lambda p, x, i, st: x[5] == 1 and x[6] >= X * 1e9)(X)
    R["netflow<-1"] = lambda p, x, i, st: st["nf"] <= -1e9
    return R

def run(R, react=REACT, Lfix=None, only=None):
    out = {}
    for name, f in R.items():
        out[name] = collections.defaultdict(lambda: dict(n=0, fired=0, d=0.0, dpos=0, dneg=0, base=0.0, new=0.0, wins_b=0, wins_n=0, rows=[]))
    for d in tlib.load():
        p = tlib.Pos(d); per = d["per"]
        if only and not only(d): continue
        for name, f in R.items():
            o = out[name][per]; o["n"] += 1; o["base"] += d["pnl"]; o["wins_b"] += d["pnl"] > 0
            dn = 0.0
            if p.ok:
                st = dict(cs=0, nf=0)
                for i, x in enumerate(p.tr):
                    if "O" in x[10] or x[3] <= p.tfill: continue
                    if x[3] + react >= p.T: break
                    if x[5] == 0: st["cs"] += x[6]; st["nf"] -= x[6]
                    else: st["nf"] += x[6]
                    if f(p, x, i, st):
                        cf, _ = p.proceeds_at(x[3] + react, Lfix)
                        dn = (cf - p.act) * (1 - tlib.FEE_SELL) / 1e9
                        o["fired"] += 1; o["dpos"] += dn > 0; o["dneg"] += dn < 0
                        o["rows"].append((dn, d["run"], d["kind"], d["mint"][:8], d["pnl"]))
                        break
            o["d"] += dn; o["new"] += d["pnl"] + dn; o["wins_n"] += (d["pnl"] + dn) > 0
    return out

def wo5(rows):
    r = sorted([x[0] for x in rows], reverse=True)
    return sum(r[5:])

if __name__ == "__main__":
    R = rules()
    for react, Lfix, lab in ((3e6, None, "react 3 ms, own landing delay"), (3e6, 120e6, "react 3 ms, landing delay fixed 120 ms (slow)")):
        print("==", lab)
        out = run(R, react, Lfix)
        print(f"{'rule':22s} | {'DEV fired':>9s} {'+/-':>9s} {'dSOL':>7s} {'/day':>6s} {'w/o5':>7s} | {'VAL fired':>9s} {'+/-':>9s} {'dSOL':>7s} {'/day':>6s} {'w/o5':>7s}")
        for name in R:
            s = []
            for per in ("DEV", "VAL"):
                o = out[name][per]
                s.append(f"{o['fired']:9d} {o['dpos']:4d}/{o['dneg']:<4d} {o['d']:+7.3f} {o['d']/HRS[per]*24:+6.2f} {wo5(o['rows']):+7.3f}")
            print(f"{name:22s} | " + " | ".join(s))
