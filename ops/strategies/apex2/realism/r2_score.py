#!/usr/bin/env python3
"""APEX-REALISM r2: re-score APEX S2 / APEX-3 picks with the live-calibrated landing model.
Landing models (from the 81 live attempts, l4/l5):
  M1  our arrival clock c ~ empirical distribution of our 81 measured chain positions (slots after the create).
      Rows of the tape ahead of us = rows with clock < c.  first-or-revert lands iff no other buy >= 0.05 SOL ahead
      (rule matched 79/81 live outcomes); value = replay with our buy after those rows (P_j).
  M1-slow / M1-fast: our clock x1.25 / x0.75.
  M2  logistic P(land) = s(0.693 + 0.634 ln min(first rival clk, 3)) (best LOO Brier 0.184), value at pos A (optimistic).
  A   sim assumption (always position A) = the old APEX-3 numbers.
Guards: first (only A, else revert), top2 (<=1 relevant buy ahead), none (buy wherever we land), A' (creator-bundle-aware:
  buys within 0.02 slot of the create are treated as bundle; first-or-revert after them).
Costs: landed trip 2.84 mSOL (live measured), revert 0.15 mSOL (live r13/r14: 0.105 nozomi, 0.205 staked)."""
import json, pickle, glob, numpy as np, collections, sys
RD = "/home/it/sniper-data/apex2/realism"
P = json.load(open(f"{RD}/picks.json")); LM = json.load(open(f"{RD}/landing_model.json"))
OC = np.array(LM["our_clk"]); THR = 0.05; INST = 0.02
CT, CR = 0.00284, 0.00015
SZ = {0.2: 0, 0.4: 1, 1.0: 2}; EX = {"h2": 0, "w0.4_6.0": 1, "b0.3": 2}
HRS = P["hrs"]; THQ = {int(k): v for k, v in P["thr"].items()}
PK = {p["mint"]: p for p in P["picks"]}
S = {}
for f in sorted(glob.glob(f"{RD}/sim/run_*.pkl")):
    for r in pickle.load(open(f, "rb")): S[r[0]] = r
# exclude launches our live probes traded (our trades were in the tape)
LIVE = {x["mint"] for x in json.load(open(f"{RD}/live.json"))}
mints = [m for m in S if m in PK and m not in LIVE]
print(f"replayed picks {len(mints)} (excluded live-traded {sum(1 for m in S if m in LIVE)})", file=sys.stderr)

def prep(m):
    riv = [x for x in S[m][4]]
    clk = np.array([x[0] for x in riv]) if riv else np.zeros(0)
    rel = np.array([(x[1] == 1 and x[2] >= THR and x[6] == 0) for x in riv], bool) if riv else np.zeros(0, bool)
    return clk, rel
PRE = {m: prep(m) for m in mints}

def ev_launch(m, zi, hi, xi, model, guard, scale=1.0):
    """expected net SOL for one pick; also P(land)"""
    R = S[m][5]; clk, rel = PRE[m]
    if model == "A":
        v = R[0, zi, hi, xi]; return (v - CT, 1.0) if np.isfinite(v) else (-CR, 0.0)
    if model == "M2":
        rc = clk[rel][0] if rel.any() else 9.0
        p = 1 / (1 + np.exp(-(0.693 + 0.634 * np.log(min(rc, 3.0)))))
        v = R[0, zi, hi, xi]
        if not np.isfinite(v): return -CR, 0.0
        return p * (v - CT) + (1 - p) * (-CR), p
    tot = 0.0; pl = 0.0; cs = OC * scale
    for c in cs:
        j = int(np.searchsorted(clk, c, "left")) if len(clk) else 0   # rows strictly before our clock
        nrel_ahead = int(rel[:j].sum())
        if guard == "first": ok = nrel_ahead == 0
        elif guard == "top2": ok = nrel_ahead <= 1
        elif guard == "none": ok = True
        elif guard == "Ap": ok = int((rel[:j] & (clk[:j] > INST)).sum()) == 0
        v = R[min(j, R.shape[0] - 1), zi, hi, xi] if ok else np.nan
        if ok and np.isfinite(v): tot += v - CT; pl += 1
        else: tot += -CR
    return tot / len(cs), pl / len(cs)

def evaluate(sel_fn, z, e, model, guard, days, scale=1.0, hi=0):
    zi, xi = SZ[z], EX[e]; per = collections.defaultdict(list); pls = []
    for m in mints:
        p = PK[m]
        if p["day"] not in days or not sel_fn(p): continue
        v, pl = ev_launch(m, zi, hi, xi, model, guard, scale); per[p["day"]].append(v); pls.append(pl)
    hrs = sum(HRS[d] for d in days); allv = np.sort(np.concatenate([np.array(per[d]) for d in days if per[d]]))[::-1]
    k = int(np.ceil(len(allv) * .05))
    return dict(n=len(allv) * 24 / hrs, sol=allv.sum() * 24 / hrs, wo5=allv[k:].sum() * 24 / hrs, pland=np.mean(pls),
                land_day=np.sum(pls) * 24 / hrs, perday=[np.sum(per[d]) * 24 / HRS[d] for d in days],
                mean_landed=(allv.sum() + CR * (len(allv) - np.sum(pls))) / max(np.sum(pls), 1e-9))
S2 = lambda p: True
AP3 = lambda p: p["day"] >= 2 and p["score"] is not None and p["score"] >= THQ[p["day"]]
ALLD = [1, 2, 3, 4, 5, 6, 7]; D2 = [2, 3, 4, 5, 6, 7]; HOLD = [5, 6, 7]
HDR = "| config | landing | picks/day | lands/day | P(land) | SOL/day | −20% fol | w/o top5% | days + | per day |\n|---|---|---|---|---|---|---|---|---|---|"
def row(nm, sel, z, e, model, guard, days, scale=1.0):
    a = evaluate(sel, z, e, model, guard, days, scale, 0); b = evaluate(sel, z, e, model, guard, days, scale, 1)
    return (f"| {nm} | {model}{'' if scale == 1 else f' x{scale}'} {guard} | {a['n']:.0f} | {a['land_day']:.0f} | {a['pland']:.2f} | {a['sol']:+.2f} | "
            f"{b['sol']:+.2f} | {a['wo5']:+.2f} | {sum(x > 0 for x in a['perday'])}/{len(days)} | {' '.join(f'{x:+.1f}' for x in a['perday'])} |"), a
if __name__ == "__main__":
    pr = print
    pr("## 1. S2 (watchlist picks, hold 2 s = h2) — days 1..7 (11-27..11-04 partial)\n" + HDR)
    for z in (0.2, 0.4):
        for model, guard, sc in (("A", "first", 1.0), ("M1", "first", 1.0), ("M1", "first", 0.75), ("M1", "first", 1.25), ("M2", "first", 1.0),
                                 ("M1", "top2", 1.0), ("M1", "none", 1.0), ("M1", "Ap", 1.0), ("M1", "Ap", 0.75)):
            pr(row(f"S2 {z} h2", S2, z, "h2", model, guard, ALLD, sc)[0])
    pr("\n## 2. APEX-3 (watchlist + entry q0.5, exit w0.4_6.0) — days 2..7\n" + HDR)
    for z in (0.2, 0.4, 1.0):
        for model, guard, sc in (("A", "top2", 1.0), ("M1", "top2", 1.0), ("M1", "first", 1.0), ("M1", "top2", 0.75), ("M2", "first", 1.0),
                                 ("M1", "none", 1.0), ("M1", "Ap", 1.0), ("M1", "Ap", 0.75)):
            pr(row(f"APEX-3 {z} w0.4_6", AP3, z, "w0.4_6.0", model, guard, D2, sc)[0])
    pr("\n## 3. APEX-3 entry filter with h2 exit (the live engine's exit) — days 2..7\n" + HDR)
    for z in (0.2, 0.4):
        for model, guard in (("A", "first"), ("M1", "first"), ("M2", "first"), ("M1", "Ap")):
            pr(row(f"APEX-3 sel {z} h2", AP3, z, "h2", model, guard, D2)[0])
    pr("\n## 4. HELD-OUT days 5..7 only\n" + HDR)
    for nm, sel, z, e, model, guard in (("S2 0.2 h2", S2, 0.2, "h2", "M1", "first"), ("S2 0.4 h2", S2, 0.4, "h2", "M1", "first"),
                                        ("APEX-3 1.0 w0.4_6", AP3, 1.0, "w0.4_6.0", "A", "top2"), ("APEX-3 1.0 w0.4_6", AP3, 1.0, "w0.4_6.0", "M1", "top2"),
                                        ("APEX-3 0.4 w0.4_6", AP3, 0.4, "w0.4_6.0", "M1", "first"), ("APEX-3 0.4 w0.4_6", AP3, 0.4, "w0.4_6.0", "M2", "first"),
                                        ("APEX-3 0.4 w0.4_6", AP3, 0.4, "w0.4_6.0", "M1", "Ap")):
        pr(row(nm, sel, z, e, model, guard, HOLD)[0])
