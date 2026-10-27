#!/usr/bin/env python3
# haqq SELL study, step 15: how much of its P&L is the EXIT vs the ENTRY. Same lots (clean closed dip lots, profiles A-E + probe),
# value of each lot under other exits, from the impact-free replay curves (curves.pkl, one sell tx 0.000325 SOL):
#   REAL      its real proceeds (both halves if split) - cost
#   SHUFFLE   expected value if its exit slot were drawn from the same profile's hold distribution (TRAIN lots) = no timing info
#   FIX-H     sell H slots after the trigger slot (H = 6 is our 1.3 s exit)
#   ORACLE    best single exit slot in 1..210 (upper bound)
# exit skill = REAL - SHUFFLE; entry value = SHUFFLE. Per run and per profile.
import sys, json, pickle, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
lots = json.load(open(f"{H.OUT}/lots.json")); C = pickle.load(open(f"{H.OUT}/curves.pkl", "rb"))
PROF = {0.25: "A.25", 0.27: "B.27", 0.3: "C.30", 0.4: "D.40", 0.49: "E.49", 0.01: "P.01"}
prof = lambda sz: PROF.get(round(sz, 2), "BIG" if sz >= 0.6 else "other")
DM = 210
rows = []
for li, c in C.items():
    l = lots[li]; b = l["buy"]
    pf = prof(b["sol"])
    if pf in ("BIG", "other"): continue
    act = l["sells"][0]["s"] - c["ref"]
    v = c["v0"]
    rows.append(dict(li=li, pf=pf, run=l["run"], dip=b["dip"], act=act, last=l["sells"][-1]["s"] - c["ref"], real=l["got"] - l["cost"], cost=c["cost"], v=v, v35=c["v35"], v50=c["v50"], v75=c["v75"], bslot=c["bslot"]))
# hold distribution per profile from TRAIN (R1+R2) dip lots, first-sell slot (capped at DM)
HD = {}
for pf in set(r["pf"] for r in rows):
    a = [min(r["act"], DM) for r in rows if r["pf"] == pf and r["run"] in ("R1", "R2") and r["dip"]]
    if not a: a = [min(r["act"], DM) for r in rows if r["pf"] == pf and r["dip"]]
    h = np.bincount(np.clip(a, 0, DM), minlength=DM + 1).astype(float); HD[pf] = h / h.sum()
def ev_shuffle(r):
    v = r["v"]; h = HD[r["pf"]].copy(); h[:r["bslot"] + 1] = 0           # cannot sell before the buy has landed
    if h.sum() == 0: return np.nan
    h /= h.sum(); ok = ~np.isnan(v)
    return float(np.nansum(h[ok] * v[ok]) / h[ok].sum()) - r["cost"]
def fix(r, Hh, key="v"):
    v = r[key]; d = max(Hh, r["bslot"] + 1)
    return float(v[min(d, DM)]) - r["cost"] if not np.isnan(v[min(d, DM)]) else np.nan
for r in rows:
    r["shuf"] = ev_shuffle(r)
    r["oracle"] = float(np.nanmax(r["v"][r["bslot"] + 1:])) - r["cost"]
    r["replay_at_real"] = float(r["v"][min(r["act"], DM)]) - r["cost"] if r["act"] <= DM else np.nan
    for Hh in (6, 10, 15, 20, 30, 45, 65):
        r[f"fix{Hh}"] = fix(r, Hh)
    for L in (35, 50, 75): r[f"fix6_{L}"] = fix(r, 6, f"v{L}")
pickle.dump(rows, open(f"{H.OUT}/pnl_rows.pkl", "wb"))
def tot(sel, k): 
    x = np.array([r[k] for r in sel], float); return np.nansum(x)
cols = ["real", "replay_at_real", "shuf", "fix6", "fix10", "fix15", "fix20", "fix30", "fix45", "fix65", "oracle"]
print("dip lots, SOL totals (exit skill = real - shuffle):")
print(f"{'group':18s} {'n':>6s} " + " ".join(f"{c:>9s}" for c in cols) + "   skill")
for lab, sel in [("ALL dip", [r for r in rows if r["dip"]])] + [(f"run {k}", [r for r in rows if r["dip"] and r["run"] == k]) for k in ("R1", "R2", "R3", "R4")] + \
                 [(f"prof {k}", [r for r in rows if r["dip"] and r["pf"] == k]) for k in ("A.25", "B.27", "C.30", "D.40", "E.49", "P.01")] + \
                 [("non-dip (ref=prev)", [r for r in rows if not r["dip"]])]:
    print(f"{lab:18s} {len(sel):6d} " + " ".join(f"{tot(sel, c):+9.2f}" for c in cols) + f"   {tot(sel, 'real') - tot(sel, 'shuf'):+7.2f}")
print("\nour 1.3 s exit on its dip entries at sell latency 0/35/50/75 ms (SOL):", " / ".join(f"{tot([r for r in rows if r['dip']], k):+.2f}" for k in ("fix6", "fix6_35", "fix6_50", "fix6_75")))
