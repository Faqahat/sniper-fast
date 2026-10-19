#!/usr/bin/env python3
# READ-ONLY. Robustness checks on race_ds.jsonl: (a) zero-wait bundle gates by time tercile, (b) stream gates that fire the
# instant the trigger trips, (c) 4yFAz-precision of the stream gate when his own buy may not trigger it.
import json, sys, statistics as st
sys.argv = ["race_an.py"]
exec(open("/root/race/race_an.py").read().split("def main():")[0])
B0 = [r for r in R if not r["mayhem"] and not hostbad(r)]
cut = B0[int(len(B0) * 0.6)]["slot"]
base = [r for r in B0 if fix_filter(r) and r["in_rand"]]
sl = sorted(r["slot"] for r in base)
t1, t2 = sl[len(sl) // 3], sl[2 * len(sl) // 3]
V = {"dev>=3 & bundle>=2tx": lambda r: r["dev_sol"] >= 3 and r["glued"] >= 2,
     "dev>=3 & bundle>=2tx & name<=12 (GATE B)": lambda r: r["dev_sol"] >= 3 and r["glued"] >= 2 and r["n_len"] <= 12,
     "dev>=2 & bundle>=2tx": lambda r: r["dev_sol"] >= 2 and r["glued"] >= 2,
     "dev>=2 & bundle>=2tx & name<=12": lambda r: r["dev_sol"] >= 2 and r["glued"] >= 2 and r["n_len"] <= 12,
     "dev>=2 & bundle>=1SOL": lambda r: r["dev_sol"] >= 2 and r["gsol"] >= 1,
     "dev>=3 & bundle>=1SOL": lambda r: r["dev_sol"] >= 3 and r["gsol"] >= 1,
     "bundle>=2tx": lambda r: r["glued"] >= 2, "dev>=3": lambda r: r["dev_sol"] >= 3, "name<=12": lambda r: r["n_len"] <= 12,
     "FIX filter": lambda r: True}
print("(a) zero-wait gates by time tercile (random FIX rows; land S @<=100+3ms; X1 = sell +1 s, X2 = TP1.3/10 s)")
for k, fn in V.items():
    cells = []
    for lo, hi in ((0, t1), (t1, t2), (t2, 10 ** 12)):
        g = [r for r in base if lo <= r["slot"] < hi and fn(r)]
        if not g:
            cells.append("n=0")
            continue
        x1 = [sim(r, d_land=100 + int(3 / r["ms_per_tx"]), tp=None, T=1000)[0] for r in g]
        x2 = [sim(r, d_land=100 + int(3 / r["ms_per_tx"]), tp=1.3, T=10000)[0] for r in g]
        cells.append("n%d race %.0f%% X1 %+.1f%% X2 %+.1f%%" % (len(g), 100 * sum(RACE(r) for r in g) / len(g), 100 * st.mean(x1), 100 * st.mean(x2)))
    g = [r for r in base if fn(r)]
    x1 = [sim(r, d_land=100 + int(3 / r["ms_per_tx"]), tp=None, T=1000)[0] for r in g]
    s1 = [sim(r, land_s1=True, tp=None, T=1000)[0] for r in g]
    print("  %-42s | %s | ALL n%d X1 %+.1f%% ex-top3 %+.1f%% 80/20 %+.1f%%" % (k, " | ".join(cells), len(g), 100 * st.mean(x1), 100 * st.mean(sorted(x1)[:-3]),
                                                                            100 * st.mean([.8 * a + .2 * b for a, b in zip(x1, s1)])))


def trig(r, W, sol, n=1, excl_his=False):
    cum, pay = 0, set()
    for d, v, h in zip(r["outS_d"], r["outS_sv"], r["outS_his"]):
        if d * r["ms_per_tx"] > W:
            break
        if excl_his and h:
            continue
        cum += v
        pay.add(d)
        if cum >= sol and len(pay) >= n:
            return d
    return None


print("\n(b) stream gates that fire the instant the trigger trips (then land +25 or +100 txs later); X1")
for W, sol, n in [(100, 2, 1), (100, 0.5, 1), (50, 0.5, 1), (200, 2, 1), (100, 2, 2), (100, 5, 1)]:
    for per, g in (("ALL", base), ("TEST", [r for r in base if r["slot"] >= cut])):
        p = [(r, trig(r, W, sol, n)) for r in g]
        p = [(r, d) for r, d in p if d is not None]
        if not p:
            continue
        for lat in (25, 100):
            v = [sim(r, d_land=d + lat, tp=None, T=1000)[0] for r, d in p]
            f = [sim(r, d_land=d + lat)[1] for r, d in p]
            print("  W%d sol>=%.1f n>=%d %-4s n=%3d race %3.0f%% lat+%3d: X1 avg %+.1f%% ex-top3 %+.1f%% entry %.2fx | trigger at d med %d" % (
                W, sol, n, per, len(p), 100 * sum(RACE(r) for r, _ in p) / len(p), lat, 100 * st.mean(v), 100 * st.mean(sorted(v)[:-3]), st.median(f), st.median(d for _, d in p)))
print("\n(c) 4yFAz precision of '>=2 SOL outside in 100 ms' (TEST)")
B1 = [r for r in B0 if fix_filter(r) and r["slot"] >= cut]
for excl in (False, True):
    g = lambda r: trig(r, 100, 2, 1, excl) is not None
    p = [r for r in B1 if r["in_rand"] and g(r)]
    hall = sum(1 for r in R if r["his"] and r["slot"] >= cut)
    print("  his own buy %s: random n=%d his-prec %.2f%% his-recall %.0f%%" % ("may NOT trigger" if excl else "may trigger", len(p),
          100 * sum(1 for r in B1 if r["his"] and g(r)) / (len(p) * WGT), 100 * sum(1 for r in B1 if r["his"] and g(r)) / hall))
