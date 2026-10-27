#!/usr/bin/env python3
# haqq SELL study, step 20: CAUSAL exit rules only (decide at each slot from information up to that slot; no look-ahead).
# FULL / TIMER hazard models from h13b: sell at the first slot whose hazard >= tau (tau chosen on TRAIN by the +-1 match).
# Match rates TRAIN / TEST / FWD, splits (size profile, token age, PKT hour band), and the P&L of the simulated exits vs its real
# exits on the same lots (impact-free replay curves, one sell tx 0.000325 SOL).
import sys, json, pickle, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H, h_gbdt as G
MOD = pickle.load(open(f"{H.OUT}/h13b_models.pkl", "rb")); F = json.load(open(f"{H.OUT}/ds_meta.json"))["feats"]; FI = {k: i for i, k in enumerate(F)}
E = np.load(f"{H.OUT}/ds_eval.npz"); XE, yE, LE, DE, RUNE = E["X"], E["y"], E["L"], E["d"], E["run"]
lots = json.load(open(f"{H.OUT}/lots.json")); C = pickle.load(open(f"{H.OUT}/curves.pkl", "rb"))
o = np.lexsort((DE, LE)); LE_, DE_, XE_ = LE[o], DE[o], XE[o]
starts = np.flatnonzero(np.r_[True, LE_[1:] != LE_[:-1]]); ends = np.r_[starts[1:], len(LE_)]
LOT = [(int(LE_[a]), a, b) for a, b in zip(starts, ends)]
ACT = {li: lots[li]["sells"][0]["s"] - (lots[li]["buy"]["s"] - lots[li]["buy"]["trig_ds"]) for li, _, _ in LOT}
RUNL = {li: lots[li]["run"] for li, _, _ in LOT}
SETS = {"TRAIN": [li for li, _, _ in LOT if RUNL[li] in ("R1", "R2")], "TEST": [li for li, _, _ in LOT if RUNL[li] == "R3"], "FWD": [li for li, _, _ in LOT if RUNL[li] == "R4"]}
def rates(preds, sel):
    c = np.zeros(4); n = 0
    for li in sel:
        pr = preds.get(li); n += 1
        if pr is None: continue
        e = abs(pr - ACT[li]); c += [e == 0, e <= 1, e <= 2, e <= 5]
    return c / max(n, 1), n
P = {}
for name in ("TIMER", "FULL"):
    m = MOD[name]; idx = [FI[c] for c in m["cols"]]
    p = G.predict(m["trees"], m["F0"], G.apply_edges(XE_[:, idx], m["edges"]), m["lr"])
    best = None
    for tau in (0.05, 0.08, 0.1, 0.12, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5):
        preds = {}
        for li, a, b in LOT:
            j = np.flatnonzero(p[a:b] >= tau); preds[li] = int(DE_[a + j[0]]) if len(j) else None
        r, _ = rates(preds, SETS["TRAIN"])
        if best is None or r[1] > best[0]: best = (r[1], tau, preds)
    _, tau, preds = best; P[name] = (tau, preds)
    print(f"{name} causal rule: sell at the first slot with hazard >= {tau}  (exact / +-1 / +-2 / +-5)")
    for k in ("TRAIN", "TEST", "FWD"):
        r, n = rates(preds, SETS[k]); print(f"   {k:5s} n {n:5d}: {' / '.join(f'{x:.0%}' for x in r)}")
pickle.dump({k: v[0] for k, v in P.items()}, open(f"{H.OUT}/h20_tau.pkl", "wb"))
tau, preds = P["FULL"]
# splits on TEST + FWD
def split(lab, keyf):
    groups = collections.defaultdict(list)
    for li in SETS["TEST"] + SETS["FWD"]: groups[keyf(lots[li])].append(li)
    print(f"\nFULL causal rule by {lab} (TEST+FWD): exact / +-1 / +-2")
    for g in sorted(groups):
        r, n = rates(preds, groups[g])
        if n >= 50: print(f"   {str(g):12s} n {n:5d}: {r[0]:.0%} / {r[1]:.0%} / {r[2]:.0%}")
split("size", lambda l: round(l["buy"]["sol"], 2))
split("token age at buy", lambda l: "<2 s" if l["buy"]["age"] < 2000 else ("2-5 s" if l["buy"]["age"] < 5000 else ("5-30 s" if l["buy"]["age"] < 30000 else ">=30 s")))
_led = json.load(open(f"{H.OUT}/ledger.json")); _a = np.polyfit([r["s"] for r in _led], [r["bt"] for r in _led], 1)
split("PKT hour band", lambda l: f"{(H.pkth(float(np.polyval(_a, l['buy']['s']))) // 4) * 4:02d}-{(H.pkth(float(np.polyval(_a, l['buy']['s']))) // 4) * 4 + 3:02d}h")
split("lot index (first lot vs add)", lambda l: "first" if l["bi"] == 0 else "add")
# P&L of simulated exits vs real, same lots
print("\nP&L on the same dip lots (SOL): real | FULL causal rule | TIMER rule | real-replay-at-its-slot (impact-free)")
for k in ("TRAIN", "TEST", "FWD"):
    real = sim_f = sim_t = rr = 0.0; n = 0
    for li in SETS[k]:
        c = C.get(li)
        if c is None: continue
        v = c["v0"]; n += 1
        real += lots[li]["got"] - lots[li]["cost"]
        for nm, acc in (("FULL", "f"), ("TIMER", "t")):
            pr = P[nm][1].get(li)
            d = min(pr if pr is not None else 210, 210)
            val = float(v[d]) - c["cost"] if not np.isnan(v[d]) else 0.0
            if acc == "f": sim_f += val
            else: sim_t += val
        a = min(ACT[li], 210); rr += (float(v[a]) - c["cost"]) if not np.isnan(v[a]) else 0.0
    print(f"   {k:5s} n {n:5d}: real {real:+8.2f} | FULL rule {sim_f:+8.2f} | TIMER rule {sim_t:+8.2f} | replay at real slot {rr:+8.2f}")
