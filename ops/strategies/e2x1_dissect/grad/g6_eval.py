#!/usr/bin/env python3
"""grad agent, step 6: evaluate the strategy universe (sim.pkl): pick on TRAIN (10-24..10-26 PKT), report TEST (10-27, 10-28).
Nothing is chosen on test. Prints universe stats, train grid, test per-day tables, selection variant, oracle (graduated-only) split."""
import pickle, collections, sys
import numpy as np

G = "/home/moiz/sniper-data/e2x1_dissect/grad"
D = pickle.load(open(G + "/sim.pkl", "rb")); R = D["R"]; EX = D["EXITS"]
TRAIN = ["10-24", "10-25", "10-26"]; TEST = ["10-27", "10-28"]
ename = lambda e: f"mig+{e[0]} | SL {'none' if e[1] is None else f'-{int(e[1] * 100)}%'} | TO {e[2]}s"
ok = [r for r in R if r.get("res") is not None and not r["edge"] and not (r["grad"] and not r["has_mig"])]
print(f"rows {len(R)}, usable {len(ok)} (dropped: crossing trade completes the curve {sum(1 for r in R if r.get('cross_completes'))}, "
      f"recording edge {sum(1 for r in R if r['edge'])}, completed but no migration recorded {sum(1 for r in R if r['grad'] and not r['has_mig'] and not r['edge'])})")

print("\n== universe per V (size 1.0; all days) ==")
print("V    tokens/day  graduate%  enter%  late%  guard%  median t(cross->complete) s (graduated)")
days_all = sorted({r["day"] for r in ok if r["day"] in TRAIN + TEST})
for V in sorted({r["V"] for r in R}):
    a = [r for r in R if r["V"] == V and r["S"] == 1.0 and not r["edge"] and r["day"] in TRAIN + TEST]
    u = [r for r in a if r.get("res") is not None]
    late = np.mean([r["why"].get("late", 0) / 10 for r in u]); gd = np.mean([r["why"].get("guard", 0) / 10 for r in u])
    tc = [r["t_complete_s"] for r in a if r["grad"] and "t_complete_s" in r]
    print(f"{V:4d}  {len(a) / len(days_all):8.1f}  {np.mean([r['grad'] for r in a]):8.1%}  {np.mean([r['fill'] for r in u]):6.1%}  {late:5.1%}  {gd:5.1%}  {np.median(tc):8.1f}"
          f"   (crossing trade itself completes: {np.mean([r['cross_completes'] for r in a]):.1%})")

def agg(rows, xi, days):
    """per-day totals for exit xi"""
    by = collections.defaultdict(list)
    for r in rows: by[r["day"]].append(r)
    return {d: by.get(d, []) for d in days}

def score(rows, xi, days):
    return sum(r["res"][xi] for r in rows if r["day"] in days) / len(days)

print("\n== TRAIN grid: best exit per (V, size), SOL/day on train ==")
best = None; table = []
for V in sorted({r["V"] for r in ok}):
    for S in sorted({r["S"] for r in ok}):
        rows = [r for r in ok if r["V"] == V and r["S"] == S]
        sc = [score(rows, xi, TRAIN) for xi in range(len(EX))]
        xi = int(np.argmax(sc)); te = score(rows, xi, TEST)
        table.append((V, S, xi, sc[xi], te))
        print(f"V {V:3d} S {S}: best on train {ename(EX[xi]):34s} train {sc[xi]:+7.2f}/day  (test, same rule: {te:+7.2f}/day)  | worst exit on train {min(sc):+.2f}")
        if best is None or sc[xi] > best[3]: best = (V, S, xi, sc[xi])
V, S, xi, _ = best
print(f"\nCHOSEN ON TRAIN: V={V} size={S} exit={ename(EX[xi])}")

def report(rows, xi, days, title):
    print(f"\n== {title} ==")
    print("day    tokens  entries  grad%(entered)  P&L grad  P&L failed   net SOL  per-entry  90% CI (day)       top5% share")
    tot = []
    for d in days:
        a = [r for r in rows if r["day"] == d]
        if not a: print(d, "no data"); continue
        p = np.array([r["res"][xi] for r in a]); fl = np.array([r["fill"] for r in a]); g = np.array([r["grad"] for r in a])
        ent = fl.sum()
        rng = np.random.default_rng(1); bs = [p[rng.integers(0, len(p), len(p))].sum() for _ in range(2000)]
        lo, hi = np.percentile(bs, [5, 95])
        pos = np.sort(p[p > 0])[::-1]; k5 = max(1, int(np.ceil(0.05 * len(p))))
        top = pos[:k5].sum() / p.sum() if p.sum() > 0 else float("nan")
        print(f"{d}  {len(a):6d}  {ent:7.1f}  {(fl * g).sum() / max(ent, 1e-9):12.1%}  {p[g].sum():+8.2f}  {p[~g].sum():+9.2f}  {p.sum():+8.2f}  {p.sum() / max(ent, 1e-9):+8.4f}  [{lo:+6.2f}, {hi:+6.2f}]  {top:9.0%}")
        tot.append(p.sum())
    if tot: print(f"mean {np.mean(tot):+.2f} SOL/day, worst day {min(tot):+.2f}")
    return tot

rows = [r for r in ok if r["V"] == V and r["S"] == S]
report(rows, xi, TRAIN, f"TRAIN  V={V} S={S} {ename(EX[xi])}")
report(rows, xi, TEST, f"TEST   V={V} S={S} {ename(EX[xi])}")

# fixed E2x1-like rule (not chosen on train): mig+48, SL none, TO 1800 at each V, size 1
print("\n== E2x1-like hold (mig+48, no stop, 30 min timeout), size 1.0, every V: SOL/day train | test ==")
xe = EX.index((48, None, 1800))
for v in sorted({r["V"] for r in ok}):
    rr = [r for r in ok if r["V"] == v and r["S"] == 1.0]
    print(f"V {v:3d}: train {score(rr, xe, TRAIN):+7.2f}  test {score(rr, xe, TEST):+7.2f}  | graduated-only (ORACLE) test {sum(r['res'][xe] for r in rr if r['day'] in TEST and r['grad']) / 2:+7.2f}"
          f"  failed-only test {sum(r['res'][xe] for r in rr if r['day'] in TEST and not r['grad']) / 2:+7.2f}")

# selection variant: flow10 >= X (X chosen on train, with the train-best exit for that V/S)
print("\n== SELECTION variant: last-10s net buy SOL >= X (X and exit chosen on train) ==")
bs = None
for v in sorted({r["V"] for r in ok}):
    for s in sorted({r["S"] for r in ok}):
        for X in [0, 2, 5, 10, 20]:
            rr = [r for r in ok if r["V"] == v and r["S"] == s and r["flow10"] >= X]
            sc = [score(rr, j, TRAIN) for j in range(len(EX))]; j = int(np.argmax(sc))
            if bs is None or sc[j] > bs[4]: bs = (v, s, X, j, sc[j])
v, s, X, j, sc = bs
print(f"chosen on train: V={v} S={s} flow10>={X} exit={ename(EX[j])} train {sc:+.2f}/day")
rr = [r for r in ok if r["V"] == v and r["S"] == s and r["flow10"] >= X]
report(rr, j, TEST, f"TEST selection V={v} S={s} flow10>={X} {ename(EX[j])}")
pickle.dump(dict(best=best, sel=bs, table=table), open(G + "/eval.pkl", "wb"))
