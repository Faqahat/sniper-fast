#!/usr/bin/env python3
"""APEX-REALISM r5: tables from sim3 (live-calibrated landing).  -> stdout markdown
Costs: landed trip CT = 2.62 mSOL (mean of 37 live landed trips), revert CR = 0.16 mSOL (r13/r14 recipe: 0.105 nozomi /
0.205 staked).  Execution-gap row: extra -1.15% of size per landed trip (live: real minus replay-at-our-real-clock on the
landed trips excluding the one guard leak = -2.3 mSOL/trip at 0.2 SOL)."""
import json, pickle, glob, collections, numpy as np
RD = "/home/it/sniper-data/apex2/realism"
CT, CR, XG = 0.00262, 0.00016, 0.0115
P = json.load(open(f"{RD}/picks.json")); HRS = P["hrs"]; THQ = {int(k): v for k, v in P["thr"].items()}
A = json.load(open(f"{RD}/all_launches.json")); INFO = {x["mint"]: x for x in A}
PK = {p["mint"]: p for p in P["picks"]}
LIVE = {x["mint"] for x in json.load(open(f"{RD}/live.json"))}
S = {}
for f in sorted(glob.glob(f"{RD}/sim3/run_*.pkl")):
    for r in pickle.load(open(f, "rb")): S[r[0]] = r
SC = {0.75: 0, 1.0: 1, 1.25: 2}; GU = {"first": 0, "top2": 1, "none": 2, "Ap": 3}; XI = {"h2": 0, "w0.4_6.0": 1, "b0.3": 2}
def zi_of(m, z):
    sz = (0.2, 0.4, 1.0) if INFO[m]["sel"] else (0.4,)
    return sz.index(z) if z in sz else None

def net(m, z, e, model, guard, hi=0, scale=1.0, xg=False):
    r = S[m]; zi = zi_of(m, z); xi = XI[e]
    if zi is None or (hi > 0 and not INFO[m]["sel"]) or (xi > 0 and not INFO[m]["sel"]): return None
    feat, Aref, EV, PL = r[1], r[2], r[3], r[4]
    if model == "A":
        v = Aref[zi, hi, xi]; return ((v - CT - (XG * z if xg else 0)), 1.0) if np.isfinite(v) else (-CR, 0.0)
    si, gi = SC[scale], GU[guard]; pl = float(PL[si, gi, zi]); ev = float(EV[si, gi, zi, hi, xi])
    if model == "M1":
        return ev - pl * (CT + (XG * z if xg else 0)) - (1 - pl) * CR, pl
    if model == "M2":   # logistic landing on first-rival clock; value = M1 conditional landed value (or sim-A if M1 never lands)
        p = 1 / (1 + np.exp(-(0.693 + 0.634 * np.log(min(feat["rc"], 3.0)))))
        v = ev / pl if pl > 0 else Aref[zi, hi, xi]
        if not np.isfinite(v): return -CR, 0.0
        return p * (v - CT) - (1 - p) * CR, p

def evaluate(mints, z, e, model, guard, days, scale=1.0, xg=False):
    out = {}
    for hi in (0, 1):
        per = collections.defaultdict(list); pls = []
        for m in mints:
            d = INFO[m]["day"]
            if d not in days: continue
            r = net(m, z, e, model, guard, hi, scale, xg)
            if r is None: continue
            per[d].append(r[0]); pls.append(r[1])
        hrs = sum(HRS[d] for d in days)
        v = np.sort(np.concatenate([np.array(per[d]) for d in days if per[d]] or [np.zeros(0)]))[::-1]; k = int(np.ceil(len(v) * .05))
        out[hi] = dict(n=len(v) * 24 / hrs, sol=v.sum() * 24 / hrs, wo5=v[k:].sum() * 24 / hrs, pl=np.mean(pls) if pls else 0,
                       lands=np.sum(pls) * 24 / hrs, perday=[np.sum(per[d]) * 24 / HRS[d] for d in days], pertrip=v.sum() / max(np.sum(pls), 1e-9))
    return out
HDR = ("| config | landing | picks/d | lands/d | P(land) | SOL/day | per landed trip mSOL | −20% fol | w/o top5% | days + | per day |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|")
def row(nm, mints, z, e, model, guard, days, scale=1.0, xg=False):
    o = evaluate(mints, z, e, model, guard, days, scale, xg); a, b = o[0], o[1]
    lab = {"A": "old sim (always A)", "M1": "M1 live clock", "M2": "M2 logistic"}[model] + ("" if scale == 1 else f" x{scale}") + (" +exec gap" if xg else "")
    return (f"| {nm} | {lab} / {guard} | {a['n']:.0f} | {a['lands']:.0f} | {a['pl']:.2f} | **{a['sol']:+.2f}** | {a['pertrip']*1e3:+.2f} | "
            f"{b['sol']:+.2f} | {a['wo5']:+.2f} | {sum(x > 0 for x in a['perday'])}/{len(days)} | {' '.join(f'{x:+.1f}' for x in a['perday'])} |")

base = [m for m in S if m not in LIVE]
S2 = [m for m in base if INFO[m]["sel"]]
AP3 = [m for m in S2 if m in PK and PK[m]["day"] >= 2 and PK[m]["score"] is not None and PK[m]["score"] >= THQ[PK[m]["day"]]]
ALLD, D2, HOLD = [1, 2, 3, 4, 5, 6, 7], [2, 3, 4, 5, 6, 7], [5, 6, 7]

if __name__ == "__main__":
    pr = print
    pr(f"launches with replay: {len(S)} (excl. {len(LIVE & set(S))} live-traded); S2 picks {len(S2)}; APEX-3 picks {len(AP3)}\n")
    pr("## 1. S2 = watchlist picks, hold 2 s (h2), days 1..7\n" + HDR)
    for z in (0.2, 0.4):
        for model, guard, sc, xg in (("A", "first", 1.0, False), ("M1", "first", 1.0, False), ("M1", "first", 1.0, True), ("M1", "first", 0.75, False),
                                     ("M1", "first", 1.25, False), ("M2", "first", 1.0, False), ("M1", "top2", 1.0, False), ("M1", "none", 1.0, False),
                                     ("M1", "Ap", 1.0, False)):
            pr(row(f"S2 {z} h2", S2, z, "h2", model, guard, ALLD, sc, xg))
    pr("\n## 2. APEX-3 = watchlist + entry q0.5, days 2..7\n" + HDR)
    for e in ("w0.4_6.0", "h2"):
        for z in (0.2, 0.4, 1.0):
            for model, guard, sc, xg in (("A", "top2", 1.0, False), ("M1", "top2", 1.0, False), ("M1", "first", 1.0, False), ("M1", "first", 1.0, True),
                                         ("M1", "first", 0.75, False), ("M1", "first", 1.25, False), ("M2", "first", 1.0, False), ("M1", "none", 1.0, False),
                                         ("M1", "Ap", 1.0, False)):
                if e == "h2" and (sc != 1.0 or guard in ("none",)): continue
                pr(row(f"APEX-3 {z} {e}", AP3, z, e, model, guard, D2, sc, xg))
    pr("\n## 3. HELD-OUT days 5..7 (APEX-3 config was frozen on days 2..4)\n" + HDR)
    for nm, ms, z, e, model, guard, xg in (("S2 0.4 h2", S2, 0.4, "h2", "M1", "first", False), ("APEX-3 1.0 w0.4_6", AP3, 1.0, "w0.4_6.0", "A", "top2", False),
                                           ("APEX-3 1.0 w0.4_6", AP3, 1.0, "w0.4_6.0", "M1", "top2", False), ("APEX-3 1.0 w0.4_6", AP3, 1.0, "w0.4_6.0", "M1", "first", True),
                                           ("APEX-3 0.4 w0.4_6", AP3, 0.4, "w0.4_6.0", "M1", "first", False), ("APEX-3 0.4 w0.4_6", AP3, 0.4, "w0.4_6.0", "M1", "first", True),
                                           ("APEX-3 0.2 w0.4_6", AP3, 0.2, "w0.4_6.0", "M1", "first", True), ("APEX-3 0.4 h2", AP3, 0.4, "h2", "M1", "first", True)):
        pr(row(nm, ms, z, e, model, guard, HOLD, 1.0, xg))
