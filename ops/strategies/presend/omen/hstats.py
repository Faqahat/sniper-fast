import pickle, collections, numpy as np
W = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/omen"
Z = pickle.load(open(f"{W}/hab.pkl", "rb")); P = Z["P"]; DU = Z["DU"]
def elig(p): return (not p["creator"]) and (not p["insider"]) and p["age"] > 0 and p["vsol"] < 100e9
EP = [p for p in P if p["D"] >= 2 and elig(p)]
print("positions D2-D6 all", sum(p["D"] >= 2 for p in P), "eligible (non-creator, non-insider, not create slot, curve<100)", len(EP))
for lo, hi in ((2, 3), (3, 4), (4, 6), (6, 100)):
    S = [p for p in EP if lo <= p["pct"] < hi]
    h = np.array([p["hold"] for p in S]); b = np.array([p["big"] for p in S])
    print(f"pct {lo}-{hi}: n {len(S)} per day {len(S)/5:.0f}; first sell <=10 slots {np.mean(h<=10):.2f} <=30 {np.mean(h<=30):.2f}; big(>=50%) first sell <=10 {np.mean((h<=10)&b):.2f} <=30 {np.mean((h<=30)&b):.2f}; wallet has >=10 prior {np.mean([p['f']['n']>=10 for p in S]):.2f}")
# per-wallet descriptive over all days (eligible positions)
byw = collections.defaultdict(list)
for p in P:
    if elig(p): byw[p["w"]].append(p)
ws = {w: v for w, v in byw.items() if len(v) >= 10}
iq = []; p30 = []
for w, v in ws.items():
    h = np.array([x["hold"] for x in v]); a, m, c = np.percentile(h, [25, 50, 75]); iq.append(c - a); p30.append(np.mean(h <= 30))
iq = np.array(iq); p30 = np.array(p30)
print("wallets with >=2% positions:", len(byw), " with >=10:", len(ws), f" IQR<=5: {np.sum(iq<=5)} ({np.mean(iq<=5):.2f}); IQR<=2: {np.sum(iq<=2)}; p30>=0.8: {np.sum(p30>=0.8)}; IQR<=5 & p30>=0.8: {np.sum((iq<=5)&(p30>=0.8))}")
print("positions held by >=10-pos wallets:", sum(len(v) for v in ws.values()), "of", sum(len(v) for v in byw.values()))
# causal habit at the open
def hab(f, n=10, iqr=5): return f["n"] >= n and f["iqr"] <= iqr and f["med"] <= 150
H = [p for p in EP if hab(p["f"])]
print(f"causal habitual at open (>=10 prior, IQR<=5): {len(H)} of {len(EP)} ({len(H)/len(EP):.3f}); per day {len(H)/5:.0f}")
for mg in (1, 2, 3, 5):
    ok = np.mean([abs(p["hold"] - p["f"]["med"]) <= mg for p in H]); print(f"  first sell within med +-{mg}: {ok:.2f}")
print("  of these, med <= 10:", np.mean([p['f']['med'] <= 10 for p in H]), " med<=30", np.mean([p['f']['med'] <= 30 for p in H]))
# >=6% engine-like (whale) positions: habitual share
for lo in (2, 3, 4, 6):
    S = [p for p in EP if p["pct"] >= lo]; h = [p for p in S if hab(p["f"])]
    print(f"pct>={lo}: {len(S)/5:.0f}/day, habitual {len(h)/5:.0f}/day ({len(h)/max(len(S),1):.2f}); habitual w/ big first sell in med+-3: {np.mean([abs(p['hold']-p['f']['med'])<=3 and p['big'] for p in h]) if h else 0:.2f}")
# dumps
ED = [d for d in DU if d["D"] >= 2 and d["vsol"] < 100e9]
print("\ndumps >=1 SOL >=12% (D2-D6, curve<100 before):", len(ED), "per day", len(ED)/5)
c = collections.Counter()
for d in ED:
    f = d["f"]; habit = hab(f)
    c["pos2"] += d["pos_s"] is not None; c["first"] += bool(d["first_sell"]); c["creator"] += d["creator"]
    c["hab"] += habit
    c["hab_pos"] += habit and d["pos_s"] is not None
    if habit and d["pos_s"] is not None:
        c["hab_pos_pred3"] += abs((d["s"] - d["pos_s"]) - f["med"]) <= 3
    c["n10"] += f["n"] >= 10
    c["n5"] += f["n"] >= 5
for k, v in c.items(): print(f"  {k}: {v} ({v/len(ED):.3f})")
# SOL-weighted
tot = sum(d["sol"] for d in ED)
print("  SOL share habitual:", sum(d["sol"] for d in ED if hab(d["f"])) / tot, " from >=2% holder:", sum(d["sol"] for d in ED if d["pos_s"] is not None) / tot)
