#!/usr/bin/env python3
"""SIZE_48H step 4 (read-only): tables from s48/size48_<tag>.pkl.
Per size and follower cut: fills, win %, realized, failed-try fees, net (48 h, per day, per fill), worst 4-hour block, worst
24 h, 90% band over draws; what the live caps (100 fills / 0.1 SOL failed-try fees per 4-hour run) would have done.
usage: size48report.py [TAG]"""
import sys, os, pickle, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s48lib, rlib

def blocks(H, hours=4):
    """[(t_lo, t_hi, usable hours)] from the window start"""
    out = []; B = hours * 3600
    use = {x["t0"] for x in H["use"]}
    for t in range(H["start"], H["end"], B):
        out.append((t, t + B, sum(1 for b in range(t, t + B, 600) if b in use) / 6.0))
    return out

def capped(rows, blk, max_fills=100, fee_budget=0.1e9):
    """net with the live caps, each 4-hour block run as its own capped run (rows in trigger time order)"""
    tot = 0; hits = 0; t_hit = []
    for lo, hi, h in blk:
        r = sorted((x for x in rows if lo <= x[0] < hi), key=lambda x: x[0])
        f = 0; fee = 0
        for x in r:
            tot += x[2]; f += x[1]; fee += x[4]
            if f >= max_fills or fee >= fee_budget:
                hits += 1; t_hit.append((x[0] - lo) / 3600); break
    return tot, hits, t_hit

def summarize(lst, H):
    hours = H["hours"]; b4 = blocks(H, 4); b24 = blocks(H, 24)
    per = []
    for seed, rows in lst:
        fills = sum(r[1] for r in rows); net = sum(r[2] for r in rows) / 1e9; pnl = sum(r[3] for r in rows) / 1e9; fees = sum(r[4] for r in rows) / 1e9
        wins = sum(1 for r in rows if r[1] and r[3] > 0)
        nb4 = [sum(r[2] for r in rows if lo <= r[0] < hi) / 1e9 for lo, hi, h in b4]
        nb24 = [sum(r[2] for r in rows if lo <= r[0] < hi) / 1e9 for lo, hi, h in b24]
        cn, hits, th = capped(rows, b4)
        per.append(dict(fills=fills, net=net, pnl=pnl, fees=fees, wins=wins, b4=nb4, b24=nb24, cap_net=cn / 1e9, cap_hits=hits, cap_t=th,
                        exits=collections.Counter(r[5] for r in rows if r[1])))
    A = lambda k: np.array([p[k] for p in per], float)
    net = A("net"); fills = A("fills")
    b4m = np.mean([p["b4"] for p in per], axis=0); b24m = np.mean([p["b24"] for p in per], axis=0)
    w4 = int(np.argmin(b4m)); w24 = int(np.argmin(b24m))
    w4_draws = np.array([p["b4"][w4] for p in per]); w24_draws = np.array([p["b24"][w24] for p in per])
    ex = sum((p["exits"] for p in per), collections.Counter())
    return dict(n=len(per), hours=hours, fills=fills.mean(), win=(A("wins").sum() / max(fills.sum(), 1)), pnl=A("pnl").mean(), fees=A("fees").mean(),
                net=net.mean(), net5=np.percentile(net, 5), net95=np.percentile(net, 95), day=net.mean() / hours * 24,
                day5=np.percentile(net, 5) / hours * 24, day95=np.percentile(net, 95) / hours * 24, per_fill=net.sum() / max(fills.sum(), 1),
                pnl_fill=A("pnl").sum() / max(fills.sum(), 1),
                worst4=(b4m[w4], np.percentile(w4_draws, 5), rlib.pkt(b4[w4][0]), b4[w4][2]), worst24=(b24m[w24], np.percentile(w24_draws, 5), rlib.pkt(b24[w24][0]), b24[w24][2]),
                pos4=float((b4m > 0).mean()), b4=[(rlib.pkt(lo), h, float(m)) for (lo, hi, h), m in zip(b4, b4m)],
                b24=[(rlib.pkt(lo), h, float(m)) for (lo, hi, h), m in zip(b24, b24m)],
                cap_net=A("cap_net").mean(), cap_hits=A("cap_hits").mean(), cap_t=float(np.mean([t for p in per for t in p["cap_t"]])) if any(p["cap_t"] for p in per) else None,
                exits={k: v / max(sum(ex.values()), 1) for k, v in ex.items()})

if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "main"
    X = pickle.load(open(f"{s48lib.S48}/size48_{tag}.pkl", "rb"))
    H = X["H"]; R = X["R"]
    S = {k: summarize(v, H) for k, v in sorted(R.items())}
    pickle.dump(S, open(f"{s48lib.S48}/size48_{tag}_summary.pkl", "wb"))
    print(f"window {rlib.pkt(H['start'])} -> {rlib.pkt(H['end'])} PKT, usable {H['hours']:.2f} h, pool {X['pool']}, draws {S[next(iter(S))]['n']}")
    print("| Size | Followers removed | Fills | Win % | Realized SOL | Failed-try fees | Net SOL (48 h) | 90% band | Per day | Per fill | Worst 4 h block | Worst 24 h | 4-h blocks > 0 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for (size, cut), s in S.items():
        print(f"| {size:.2f} | {cut * 100:.0f}% | {s['fills']:.0f} | {s['win'] * 100:.0f}% | {s['pnl']:+.2f} | {s['fees']:.2f} | **{s['net']:+.2f}** | {s['net5']:+.2f} to {s['net95']:+.2f} | "
              f"{s['day']:+.2f} | {s['per_fill']:+.4f} | {s['worst4'][0]:+.2f} ({s['worst4'][2]}) | {s['worst24'][0]:+.2f} ({s['worst24'][2]}) | {s['pos4'] * 100:.0f}% |")
    print("\ncaps (100 fills / 0.1 SOL failed-try fees per 4-hour run, 12 runs):")
    for (size, cut), s in S.items():
        if cut == 0:
            print(f"  size {size:.2f}: net with caps {s['cap_net']:+.2f} vs {s['net']:+.2f} without; runs that hit a cap {s['cap_hits']:.1f} of 12, after {s['cap_t'] or 0:.1f} h on average")
    print("\n4-hour blocks (mean net SOL), cut 0:")
    for (size, cut), s in S.items():
        if cut == 0: print(f"  {size:.2f}: " + "  ".join(f"{t[6:]}({h:.1f}h) {m:+.2f}" for t, h, m in s["b4"]))
    print("\n24 h:")
    for (size, cut), s in S.items(): print(f"  {size:.2f} cut {cut:.1f}: " + "  ".join(f"{t} ({h:.1f}h) {m:+.2f}" for t, h, m in s["b24"]))
    print("\nexits (cut 0):")
    for (size, cut), s in S.items():
        if cut == 0: print(f"  {size:.2f}: " + ", ".join(f"{k} {v * 100:.0f}%" for k, v in sorted(s["exits"].items())), f"| P&L per fill before failed tries {s['pnl_fill']:+.4f}")
