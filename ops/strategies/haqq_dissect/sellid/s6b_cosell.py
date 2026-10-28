#!/usr/bin/env python3
"""SELLID step 6b (read-only): 'co-seller' exits. Wallets whose SELLS preceded 247/248 sells above chance (s4 walk-forward lists
SELLS_<code>_<d>_<N>, learned on days < d). Policies: WS(list, cap) = sell at the first SELL by a list wallet after the entry (reactive,
MEASURED delays), else timer at cap; WSW(list) = the earlier of that and the wave exit (ps RIDE(150,150,1000) / reg and his lots
RIDE(150,300,2000)); on his lots also vs RIDE(424,1000,20000). Same replay as s6. Out: sellid/s6b.txt"""
import pickle, sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
from xsim import Pos
from x7_ourexits import delays
from x12_wave import ev as ev12
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/sellid")
from s6_rules import ride_time
OUT = "/home/moiz/sniper-data/haqq_dissect/sellid"
DAYS = (2, 3, 4, 5, 6)
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)
ids = json.load(open("/home/moiz/sniper-data/dv8/tab/ids.json")); idm = {k: i for i, k in enumerate(ids)}
L4 = json.load(open(f"{OUT}/s4_lists.json"))
LST = {(c, N, d): set(idm[w] for w in L4.get(f"SELLS_{c}_{d}_{N}", []) if w in idm) for c in (0, 247, 248) for N in (25, 50, 100) for d in DAYS}
DR, DT, _ = delays()
def val(S, pol, kind, d):
    if S.n == 0: return S.v_pre
    k = pol[0]
    if k == "RIDE": return ev12(S, pol, DR, DT)
    _, c, N, cap = pol; lst = LST[(c, N, d)]
    m = (~S.bu) & np.isin(S.p["us"], list(lst)); j = S.first(m)
    if k == "WS":
        if j is not None and S.dcc[j] < S.slot_start(cap): return S.land_val(S.dcc[j], DR)
        return S.timer_val(cap, DT[kind])
    tw = ride_time(S, *((150, 150, 1000) if cap == "ps" else (150, 300, 2000) if cap == "reg" else (424, 1000, 20000)))
    if j is not None and S.dcc[j] < tw: return S.land_val(S.dcc[j], DR)
    return S.land_val(tw, DR)
Z = pickle.load(open(f"{OUT}/s1.pkl", "rb")); LOTS = [l for l in Z["lots"] if l["first_sell_k"] is not None and l["day"] in DAYS and len(l["p_dcc"])]
P("# Co-seller exits (walk-forward lists), curve P&L SOL, MEASURED delays")
for code in (247, 248):
    V = [l for l in LOTS if l["code"] == code]
    pols = [("RIDE", 424, 1000, 20000), ("RIDE", 150, 300, 2000)] + [("WS", c, N, cap) for c in (0, code) for N in (25, 100) for cap in (5, 10)] + [("WSW", c, N, "his") for c in (0, code) for N in (25, 50, 100)]
    tot = {p: np.zeros(len(DAYS)) for p in pols}; tot9 = {p: 0.0 for p in pols}
    for l in V:
        p = dict(dcc=l["p_dcc"].astype(np.float64), bu=l["p_bu"], so=l["p_so"], tk=l["p_tk"], us=l["p_us"], V0=l["V0"], T0=l["T0"], sin=l["sin"], cost=l["cost"], fee=l["fee"], off_in_slot=l["off_in_slot"], kind="reg")
        for fol in (1.0, 0.9):
            S = Pos(p, fol)
            for pol in pols:
                v = (val(S, pol, "reg", l["day"]) - 1) * S.cost
                if fol == 1.0: tot[pol][DAYS.index(l["day"])] += v
                else: tot9[pol] += v
    P(f"\n## bot {code} own lots D2-D6 ({len(V):,}); his realized {sum(l['net'] for l in V):+.2f}")
    for pol in pols: P(f"- {pol}: {tot[pol].sum():+.2f} (0.9 fol {tot9[pol]:+.2f}); per day " + " ".join(f"{x:+.2f}" for x in tot[pol]))
O = pickle.load(open(f"{OUT}/ourpaths_us.pkl", "rb"))
for kind in ("ps", "reg"):
    V = [p for p in O if p["kind"] == kind and p["day"] in DAYS]
    dl = sorted(set(p["day"] for p in V))
    base = ("RIDE", 150, 150, 1000) if kind == "ps" else ("RIDE", 150, 300, 2000)
    pols = [base] + [("WS", c, N, cap) for c in (0, 248) for N in (25, 100) for cap in (2, 5)] + [("WSW", c, N, kind) for c in (0, 247, 248) for N in (25, 50, 100)]
    tot = {p: {d: 0.0 for d in dl} for p in pols}; tot9 = {p: 0.0 for p in pols}
    for p in V:
        for fol in (1.0, 0.9):
            S = Pos(p, fol)
            for pol in pols:
                v = (val(S, pol, kind, p["day"]) - 1) * S.cost
                if fol == 1.0: tot[pol][p["day"]] += v
                else: tot9[pol] += v
    P(f"\n## OUR {kind} fills ({len(V)}); wave baseline {base}")
    for pol in pols: P(f"- {pol}: {sum(tot[pol].values()):+.3f} (0.9 fol {tot9[pol]:+.3f}); per day " + " ".join(f"D{d} {tot[pol][d]:+.3f}" for d in dl) + "; vs wave " + " ".join(f"{tot[pol][d] - tot[base][d]:+.3f}" for d in dl))
open(f"{OUT}/s6b.txt", "w").write("\n".join(out) + "\n")
