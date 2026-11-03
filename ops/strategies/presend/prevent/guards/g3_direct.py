#!/usr/bin/env python3
"""GUARDS step 3 [MEASURED: live fills + chain tapes; the 0.39 close probability is MEASURED on 4,020 big sells of 10 recorder chunks]:
(1) precursor classification of every live fill; (2) DIRECT effect of every guard variant (the live fills it would have blocked at
their real landing position and their realized P&L), per run.  No replacement fills here (that is g4, the replay).
Out: direct.json, direct.txt, classes.txt in /home/moiz/sniper-data/prevent/guards
usage: g3_direct.py"""
import pickle, json, collections, math, sys
import numpy as np
OUT = "/home/moiz/sniper-data/prevent/guards"
SUP = 1e15; PCLOSE = 0.39; FIXC = 0.003524
R = pickle.load(open(f"{OUT}/feats.pkl", "rb"))
ORDER = ["F21", "F22", "F23", "F24", "F26", "F27", "F28", "A16", "A17", "A19", "A20", "A24", "A25", "A26", "A27", "A34", "A35", "A36", "A37", "A38"]
PICK = set(ORDER) - {"A37", "A38"}


def scaled(o): return (o["pnl"] + FIXC) * 0.696 / (o["spend"] / 1e9) - FIXC


def whale_ratio(o):
    tb = o.get("trig_bal") or o.get("wh_T") or 0
    return (o["wh_L"] / tb) if tb > 0 else None


def guardA(o, Z):
    """-> (P(blocked) OPEN, P(blocked) NAIVE)"""
    if o["kind"] != "t2": return 0.0, 0.0
    r = whale_ratio(o)
    if r is None: return 0.0, 0.0
    if r > Z: return 1.0, 1.0
    if o["wh_L"] <= 0 and o["wh_S"] > 0: return 0.0, PCLOSE    # sold out between signing and landing: its account may be closed
    return 0.0, 0.0


def guardB(o, X, M, K, kinds=("t2", "rearm")):
    if o["kind"] not in kinds: return 0.0, 0.0
    HS = o[f"H{X}_S"]; HL = o[f"H{X}_L"]
    hs = sorted(HS.items(), key=lambda kv: -kv[1])[:K]
    blocked = False; zeroed = 0
    for u, bS in hs:
        bL = HL[u]
        bar = (bL >= X / 100 * SUP) if M == "abs" else (bL > 0.5 * bS)
        if bar: blocked = True
        elif bL <= 0: zeroed += 1
    if blocked: return 1.0, 1.0
    return 0.0, 1.0 - (1 - PCLOSE) ** zeroed


VARS = {}
for Z in (0.25, 0.5, 0.75): VARS[f"A_{Z}"] = lambda o, Z=Z: guardA(o, Z)
for X in (3, 6):
    for M in ("abs", "rel"):
        for K in (1, 2, 6): VARS[f"B_{X}_{M}_{K}"] = lambda o, X=X, M=M, K=K: guardB(o, X, M, K)
for X, M in ((6, "abs"), (3, "abs"), (6, "rel")):
    VARS[f"B_{X}_{M}_6_rearm"] = lambda o, X=X, M=M: guardB(o, X, M, 6, ("rearm",))


def classify(o):
    if o["kind"] == "t2":
        r = whale_ratio(o)
        if r is None: return "t2_unknown"
        if r <= 0.5: return "t2_after_whale_dump"
        if o["aft_whale_sol"] >= 0.1: return "t2_PRECURSOR_whale_dumped_after_us"
        oth = o["aft_H3_sol"] - o["aft_whale_sol"]
        if oth >= 0.1: return "t2_PRECURSOR_other_holder_dumped_after_us"
        return "t2_precursor_no_big_dump_after"
    still = [u for u, b in o["H6_L"].items() if b >= 0.06 * SUP]
    if not o["H6_S"]: return "re_no_6pct_holder_at_sign"
    if not still: return "re_6pct_holders_gone_before_us"
    if o["aft_H6_sol"] >= 0.1: return "re_PRECURSOR_holder_dumped_after_us"
    return "re_holder_still_there_no_dump_after"


lines = []
def P(*a):
    s = " ".join(str(x) for x in a); lines.append(s); print(s)

# ---------------- classes
cl = collections.defaultdict(list)
for o in R: cl[classify(o)].append(o)
P("== PRECURSOR CLASSES (all 20 runs; P&L = realized SOL, raw | scaled to 0.696)")
P(f"{'class':45s} {'n':>5s} {'sum':>8s} {'mean mSOL':>9s} {'sum@0.696':>9s} {'win%':>5s} {'<=-0.05':>7s}")
for k in sorted(cl):
    v = cl[k]; s = sum(o["pnl"] for o in v); ss = sum(scaled(o) for o in v)
    P(f"{k:45s} {len(v):5d} {s:+8.3f} {1e3*s/len(v):+9.1f} {ss:+9.3f} {100*np.mean([o['pnl']>0 for o in v]):5.0f} {sum(o['pnl']<=-0.05 for o in v):7d}")
# per-run class split
P("\n== per run: T2 after-whale-dump vs T2 precursor (n / SOL @0.696); re-arm: holders gone vs still there")
P(f"{'run':4s} | {'T2 after':>14s} | {'T2 precursor':>14s} | {'  of it whale dumped on us':>16s} | {'RE gone':>14s} | {'RE still':>14s}")
for run in ORDER:
    v = [o for o in R if o["run"] == run]
    def g(f): x = [o for o in v if f(classify(o))]; return f"{len(x):3d} {sum(scaled(o) for o in x):+8.3f}"
    P(f"{run:4s} | {g(lambda c: c=='t2_after_whale_dump'):>14s} | {g(lambda c: 'PRECURSOR' in c and c.startswith('t2') or c=='t2_precursor_no_big_dump_after'):>14s} | "
      f"{g(lambda c: c=='t2_PRECURSOR_whale_dumped_after_us'):>16s} | {g(lambda c: c in ('re_6pct_holders_gone_before_us','re_no_6pct_holder_at_sign')):>14s} | "
      f"{g(lambda c: c in ('re_PRECURSOR_holder_dumped_after_us','re_holder_still_there_no_dump_after')):>14s}")

# ---------------- direct effect of the guards
res = {}
P("\n== DIRECT effect per guard (gain = minus the realized P&L of the blocked live fills; expected values; SOL scaled to 0.696)")
P(f"{'variant':16s} {'trt':5s} | {'PICK blk':>8s} {'PICK gain':>9s} {'r37 blk':>7s} {'r37 gain':>8s} {'r38 blk':>7s} {'r38 gain':>8s} | {'PICK runs +/-':>13s} | {'blocked winners/losers SOL (all)':>32s}")
for name, fn in VARS.items():
    for trt, ix in (("OPEN", 0), ("NAIVE", 1)):
        per = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
        bw = bl = 0.0
        for o in R:
            p = fn(o)[ix]
            if p <= 0: continue
            s = scaled(o)
            per[o["run"]][0] += p; per[o["run"]][1] += -p * s; per[o["run"]][2] += -p * o["pnl"]
            if s > 0: bw += p * s
            else: bl += p * s
        pk = sum(per[r][1] for r in PICK); pkn = sum(per[r][0] for r in PICK)
        plus = sum(1 for r in PICK if per[r][1] > 1e-9); minus = sum(1 for r in PICK if per[r][1] < -1e-9)
        res[f"{name}|{trt}"] = {"per_run": {r: {"blocked": round(per[r][0], 2), "gain_scaled": round(per[r][1], 4), "gain_raw": round(per[r][2], 4)} for r in ORDER},
                               "pick_gain": pk, "pick_blocked": pkn, "pick_plus": plus, "pick_minus": minus, "blocked_winners": bw, "blocked_losers": bl}
        P(f"{name:16s} {trt:5s} | {pkn:8.1f} {pk:+9.3f} {per['A37'][0]:7.1f} {per['A37'][1]:+8.3f} {per['A38'][0]:7.1f} {per['A38'][1]:+8.3f} | {plus:6d} / {minus:<5d} | {bw:+.3f} / {bl:+.3f}")
json.dump(res, open(f"{OUT}/direct.json", "w"), indent=1)
open(f"{OUT}/direct.txt", "w").write("\n".join(lines) + "\n")
