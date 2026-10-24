#!/usr/bin/env python3
# How many wallets would pass the screen by luck? (read-only) For every wallet with >= 15 snipes: demean its per-token
# PnL (so its true edge is zero, same spread / tails), bootstrap within each run-half, re-apply the exact screen
# (both runs or both halves positive, total > 0, total without the best 2 tokens > 0). Sum of pass probabilities =
# expected number of lucky passes. Also a per-wallet bootstrap P(mean <= 0) on the real (not demeaned) values.
# usage: python3 -I w5_null.py <out dir of w2_wallets.py> [iters]
import sys, os, json, gzip, random, statistics
OUTD = sys.argv[1]; IT = int(sys.argv[2]) if len(sys.argv) > 2 else 300
R = json.load(open(os.path.join(OUTD, "wallets_all.json"))); PP = json.load(gzip.open(os.path.join(OUTD, "pairs_cands.json.gz"), "rt"))
random.seed(7)
def screen(vals, fails):
    # vals: list of (run, half, pnl); fails: list of (run, half, cost<0)
    tot = sum(v for _, _, v in vals) + sum(f for _, _, f in fails)
    if tot <= 0: return False
    top2 = sorted((v for _, _, v in vals), reverse=True)[:2]
    if tot - sum(top2) <= 0: return False
    n1 = sum(1 for r, _, _ in vals if r == "R1"); n2 = len(vals) - n1
    if n1 >= 6 and n2 >= 6:
        return all(sum(v for r, _, v in vals if r == R_) + sum(f for r, _, f in fails if r == R_) > 0 for R_ in ("R1", "R2"))
    big = "R1" if n1 >= n2 else "R2"
    ok = True
    for h in (0, 1):
        vs = [v for r, hh, v in vals if r == big and hh == h]
        if len(vs) < 3: return False
        ok = ok and sum(vs) + sum(f for r, hh, f in fails if r == big and hh == h) > 0
    return ok
exp = 0.0; rows = []
for w, s in R.items():
    if s.get("n", 0) < 15 or s.get("insider_like"): continue
    vals = [(p[0], p[1], p[2]) for p in PP.get(w, [])]; fails = [(f[0], f[1], f[2]) for f in PP.get(w + "|fail", [])]
    if len(vals) < 15: continue
    mu = (sum(v for _, _, v in vals) + sum(f for _, _, f in fails)) / len(vals)
    groups = {}
    for r, h, v in vals: groups.setdefault((r, h), []).append(v - mu)
    hits = 0; le0 = 0
    groups_real = {}
    for r, h, v in vals: groups_real.setdefault((r, h), []).append(v)
    for _ in range(IT):
        bs = [(r, h, random.choice(g)) for (r, h), g in groups.items() for _ in g]
        hits += screen(bs, fails)
        br = [random.choice(g) for g in groups_real.values() for _ in g]
        le0 += (sum(br) + sum(f for _, _, f in fails)) <= 0
    p = hits / IT; exp += p
    rows.append((w, s.get("pass"), p, le0 / IT, s["n"], s["all"]["pnl"]))
npass = sum(1 for r in rows if r[1])
print(f"wallets screened {len(rows)}; observed passes {npass}; expected lucky passes if no wallet had an edge = {exp:.1f}")
out = {w: dict(p_pass_if_no_edge=round(p, 3), p_mean_le0=round(q, 3)) for w, ok, p, q, n, pn in rows}
json.dump(out, open(os.path.join(OUTD, "null.json"), "w"), indent=0)
for w, ok, p, q, n, pn in sorted(rows, key=lambda r: r[3]):
    if ok: print(f"  {w[:8]} n={n} pnl={pn:+.2f} P(pass|no edge)={p:.2f} bootstrap P(mean<=0)={q:.3f}")
