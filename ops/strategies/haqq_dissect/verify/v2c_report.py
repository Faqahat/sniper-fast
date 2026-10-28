#!/usr/bin/env python3
"""VERIFY v2c: tables from v2b_reimpl.py (INFERRED). Per group (dv8 day or fresh hour, PKT), mean over seeds:
windows, fills, added fills (not inside a T2 window), wins, P&L of added fills (live exit, after 2.015 mSOL/fill), failed-try fees of
re windows, NET replay = P&L - fees, x0.81 (only when > 0), 10% / 20% fewer followers (cal), wave exit (cal); 90% bootstrap of the
replay net (windows resampled, seed-averaged per window).
usage: v2c_report.py PKL day|hour"""
import sys, pickle, collections, time
import numpy as np

COST = 5120 + 200_000 + 605_000 + 1_200_000 + 5020
DAY0 = 1793038500 - 5 * 86400


def pkt(t, f="%m-%d %H:%M"): return time.strftime(f, time.gmtime(int(t) + 18000))


def cal(x): return 0.81 * x if x > 0 else x


if __name__ == "__main__":
    Z = pickle.load(open(sys.argv[1], "rb")); mode = sys.argv[2]
    rows = Z["rows"]; ns = Z["seeds"]
    key = (lambda r: int((r["bt"] - DAY0) // 86400)) if mode == "day" else (lambda r: (r["bt"] + 18000) // 3600 * 3600 - 18000)
    name = (lambda k: f"D{k} {pkt(DAY0 + k * 86400, '%m-%d')}") if mode == "day" else (lambda k: pkt(k))
    # per window (mint, s) seed-averaged values for the bootstrap
    W = collections.defaultdict(lambda: np.zeros(8))
    for r in rows:
        f = r["fill"]; v = np.zeros(8)
        v[0] = -r["fees"] / 1e9
        if f is not None and not r["base_has"]:
            v[1] = 1; v[2] = (f["ex"]["live"] - COST) / 1e9; v[3] = (f["ex"]["live10"] - COST) / 1e9; v[4] = (f["ex"]["live20"] - COST) / 1e9
            v[5] = (f["ex"]["wave"] - COST) / 1e9; v[6] = (f["ex"]["wave10"] - COST) / 1e9; v[7] = int(f["ex"]["live"] - COST > 0)
        W[(key(r), r["mint"], r["s"])] += v / ns
    G = collections.defaultdict(list)
    for (g, m, s), v in W.items(): G[g].append(v)
    print("| Group | Re windows | Added fills (wins) | P&L/added fill mSOL | Fees SOL | **Replay net [90%]** | x0.81 | 10% fewer fol (cal) | 20% fewer (cal) | Wave exit (cal) | Wave, 10% fewer (cal) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    TOT = np.zeros(8); allv = []
    rng = np.random.default_rng(5)
    for g in sorted(G):
        A = np.array(G[g]); s = A.sum(0); TOT += s; allv.append(A)
        net = A[:, 0] + A[:, 2]
        bs = [net[rng.integers(0, len(net), len(net))].sum() for _ in range(2000)]
        lo, hi = np.percentile(bs, [5, 95])
        print(f"| {name(g)} | {len(A)} | {s[1]:.0f} ({s[7]:.0f}) | {1e3 * s[2] / max(s[1], 1):+.2f} | {-s[0]:.3f} | **{s[0] + s[2]:+.2f}** [{lo:+.2f}, {hi:+.2f}] | "
              f"{cal(s[2]) + s[0]:+.2f} | {cal(s[3]) + s[0]:+.2f} | {cal(s[4]) + s[0]:+.2f} | {cal(s[5]) + s[0]:+.2f} | {cal(s[6]) + s[0]:+.2f} |")
    A = np.concatenate(allv); net = A[:, 0] + A[:, 2]
    bs = [net[rng.integers(0, len(net), len(net))].sum() for _ in range(2000)]; lo, hi = np.percentile(bs, [5, 95])
    s = TOT
    print(f"| **Total** | {len(A)} | {s[1]:.0f} ({s[7]:.0f}) | {1e3 * s[2] / max(s[1], 1):+.2f} | {-s[0]:.3f} | **{s[0] + s[2]:+.2f}** [{lo:+.2f}, {hi:+.2f}] | "
          f"{cal(s[2]) + s[0]:+.2f} | {cal(s[3]) + s[0]:+.2f} | {cal(s[4]) + s[0]:+.2f} | {cal(s[5]) + s[0]:+.2f} | {cal(s[6]) + s[0]:+.2f} |")
    # per-seed totals (landing-draw noise)
    per = collections.defaultdict(float)
    for r in rows:
        f = r["fill"]; per[r["seed"]] -= r["fees"] / 1e9
        if f is not None and not r["base_has"]: per[r["seed"]] += (f["ex"]["live"] - COST) / 1e9
    print("per seed replay net: " + ", ".join(f"{k}: {v:+.2f}" for k, v in sorted(per.items())))
