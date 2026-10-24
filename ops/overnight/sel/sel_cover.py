#!/usr/bin/env python3
# Selection study, step 4 (local only): widen the config as an OR-list of narrow AND-rules (sequential covering). Each rule is
# found by beam search on TRAIN hours among dumps no earlier rule took; a rule must keep win% >= WINMIN at 35 AND 75 ms on
# train and >= MINPH picks/h. Objective = train P&L at 35 + 50 + 75 ms. Extra causal features: the three wallets' earlier dip
# buys on the same token (count, seconds since the last one; a buy counts only if it happened before this dump).
# Prints every rule's TRAIN and TEST numbers, then the union.   env: SPLIT, H, WINMIN, MINPH, NRULES, DEPTH
import os, sys, json, collections
import numpy as np
sys.argv = [sys.argv[0], "profit"]
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import sel_search as S
EV, X = S.EV, S.X
# earlier dip buys of the three wallets on the same token
order = sorted(range(len(EV)), key=lambda i: (EV[i]["m"], EV[i]["age"]))
tn = np.zeros(len(EV)); ts = np.full(len(EV), 1e9)
prev_m = None; buys = []
for i in order:
    r = EV[i]
    if r["m"] != prev_m: prev_m = r["m"]; buys = []
    t0 = r["age"] * 1000.0
    past = [b for b in buys if b < t0]
    tn[i] = len(past); ts[i] = (t0 - max(past)) / 1000.0 if past else 1e9
    for w, d in r["lab"].items(): buys.append(t0 + d)
S.FEATS += ["tgt_n", "tgt_since"]; S.X = X = np.column_stack([X, tn, ts])
S.GR["tgt_n"] = [0.0, 1.0, 2.0, 3.0, 5.0, 8.0]; S.GR["tgt_since"] = [0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
WINMIN = float(os.environ.get("WINMIN", "0.62")); MINPH = float(os.environ.get("MINPH", "3")); NR = int(os.environ.get("NRULES", "5")); DEPTH = int(os.environ.get("DEPTH", "5"))
tr, te = S.tr, S.te
def winrate(m, L):
    p, f = S.P[L]; fl = m & f
    return (p[fl] > 0).mean() if fl.any() else 0.0
def obj(cfg, free):
    m = S.mask(cfg) & tr & free; n = m.sum()
    if n / S.HTR < MINPH: return -1e9
    w35, w75 = winrate(m, 35), winrate(m, 75)
    pen = max(0, WINMIN - w35) * 300 + max(0, WINMIN - w75) * 300
    return float(sum(S.P[L][0][m].sum() for L in (35, 50, 75))) - pen
def beam(free, depth=DEPTH, width=6):
    B = [(-1e9, [])]; best = (-1e9, [])
    for d in range(depth):
        cand = []
        for sc, cfg in B:
            used = {(k, op) for k, op, _ in cfg}
            for k in S.FEATS:
                for op in (">=", "<="):
                    if (k, op) in used: continue
                    for v in S.GR[k]:
                        c = cfg + [(k, op, v)]; cand.append((obj(c, free), c))
        cand.sort(key=lambda x: -x[0]); B = []; seen = set()
        for sc, c in cand:
            key = tuple(sorted((k, op, round(v, 6)) for k, op, v in c))
            if key in seen: continue
            seen.add(key); B.append((sc, c))
            if len(B) >= width: break
        if not B or B[0][0] <= best[0] + 1e-6: break
        best = B[0]
    return best
def line(m, part, hrs):
    mm = m & part; n = int(mm.sum()); out = f"{n:5d} ({n / hrs:5.1f}/h)"
    for L in (35, 50, 75):
        p, f = S.P[L]; fl = mm & f
        out += f" | {L} ms {p[mm].sum():+6.2f} win {((p[fl] > 0).mean() if fl.any() else 0):.0%}"
    return out
free = np.ones(len(EV), bool); rules = []; union = np.zeros(len(EV), bool)
for i in range(NR):
    sc, cfg = beam(free)
    if sc <= 0 or not cfg: break
    m = S.mask(cfg) & free
    rules.append(cfg); union |= S.mask(cfg); free &= ~S.mask(cfg)
    print(f"RULE {i + 1}: " + " AND ".join(f"{k} {op} {v:.4g}" for k, op, v in cfg), flush=True)
    print(f"   TRAIN {line(m, tr, S.HTR)}\n   TEST  {line(m, te, S.HTE)}", flush=True)
print("UNION of rules:")
print(f"   TRAIN {line(union, tr, S.HTR)}\n   TEST  {line(union, te, S.HTE)}")
json.dump(rules, open(os.environ.get("RULES_OUT", "/home/moiz/sniper/ops/overnight/sel/rules_cover.json"), "w"))
