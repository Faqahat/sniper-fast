#!/usr/bin/env python3
"""SELLID step 3 (read-only): what is on the tape right before a 247/248 sell vs at MATCHED RANDOM moments of the same lots.

For every lot sold at chain-clock T (ms after the buy, first sell), and for 10 random moments per lot drawn uniformly from
[start of slot buy+2 (he never sells earlier), T) (same lot, same token, same hold window), the tape in the 212 / 424 ms before:
  any outside buy; max outside buy SOL; any outside sell; outside sell SOL; time since the last outside buy / trade;
  number of outside buys in the last 1 s; lot value change over the last 212 ms (exact replay of the lot alone, path values).
Likelihood ratio = P(feature | sell moment) / P(feature | random moment) - a ratio > 1 means the feature precedes his sells
more often than chance. Reaction-time histogram: gap from the last >= 1 SOL outside buy to the sell, vs random moments.
Same-slot / idx gap of the trade right before the sell.
Out: sellid/s3.txt"""
import pickle, sys, collections
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_dissect/sellid"
SMS = 212.0
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)


def feats(l, t):
    d = l["p_dcc"].astype(np.float64); b = l["p_bu"]; so = l["p_so"]
    m212 = (d < t) & (d >= t - 212); m424 = (d < t) & (d >= t - 424); m1s = (d < t) & (d >= t - 1000)
    pb = (d < t) & b; ps = (d < t) & ~b
    lb = t - d[pb][-1] if pb.any() else 1e9
    lt = t - d[d < t][-1] if (d < t).any() else 1e9
    return dict(buy212=bool((m212 & b).any()), buy424=bool((m424 & b).any()), maxb212=float(so[m212 & b].max()) if (m212 & b).any() else 0.0,
                maxb424=float(so[m424 & b].max()) if (m424 & b).any() else 0.0, sell212=bool((m212 & ~b).any()), sells212=float(so[m212 & ~b].sum()),
                nb1s=int((m1s & b).sum()), bsol1s=float(so[m1s & b].sum()), lastbuy=lb, lasttr=lt)


def main():
    Z = pickle.load(open(f"{OUT}/s1.pkl", "rb")); LOTS = Z["lots"]
    g = np.random.default_rng(7)
    R = collections.defaultdict(list)
    mins = collections.Counter()
    for l in LOTS:
        if l["first_sell_k"] is None: continue
        T = l["sell_dcc"]; t0 = 2 * SMS - l["off_in_slot"]
        mins[int((T + l["off_in_slot"]) // SMS)] += 1
        if T <= t0: continue
        f = feats(l, T); f.update(code=l["code"], sell=1, hold=T, net=l["net"], day=l["day"]); R[l["code"]].append(f)
        for t in g.uniform(t0, T, 10):
            f = feats(l, t); f.update(code=l["code"], sell=0, hold=T, net=l["net"], day=l["day"]); R[l["code"]].append(f)
    P("# 247/248 sell moments vs matched random moments in the same lots (MEASURED)")
    P("first-sell slot offset (slots after the buy slot) distribution: " + ", ".join(f"{k}:{v}" for k, v in sorted(mins.items())[:12]))
    for code in (247, 248):
        F = R[code]; s = np.array([f["sell"] for f in F]) == 1
        P(f"\n## bot {code}: sells {s.sum():,}, random moments {(~s).sum():,}")
        P("| feature | at his sell | at random moments | ratio |"); P("|---|---|---|---|")
        tests = [("outside buy in last 212 ms", lambda f: f["buy212"]), ("outside buy in last 424 ms", lambda f: f["buy424"]),
                 ("outside buy >= 0.5 SOL in last 212 ms", lambda f: f["maxb212"] >= 0.5), ("outside buy >= 1 SOL in last 212 ms", lambda f: f["maxb212"] >= 1),
                 ("outside buy >= 2 SOL in last 212 ms", lambda f: f["maxb212"] >= 2), ("outside buy >= 2 SOL in last 424 ms", lambda f: f["maxb424"] >= 2),
                 ("outside sell in last 212 ms", lambda f: f["sell212"]), ("outside sells >= 1 SOL in last 212 ms", lambda f: f["sells212"] >= 1),
                 ("no outside trade in last 424 ms", lambda f: f["lasttr"] > 424), ("no outside buy in last 1000 ms", lambda f: f["lastbuy"] > 1000),
                 ("no outside buy in last 500 ms", lambda f: f["lastbuy"] > 500),
                 (">= 3 outside buys in last 1 s", lambda f: f["nb1s"] >= 3), (">= 2 SOL outside buys in last 1 s", lambda f: f["bsol1s"] >= 2)]
        for name, fn in tests:
            a = np.mean([fn(f) for f in F if f["sell"]]); b = np.mean([fn(f) for f in F if not f["sell"]])
            P(f"| {name} | {a:.3f} | {b:.3f} | {a / max(b, 1e-9):.2f} |")
        # by hold bucket (fast winners vs slow)
        P(f"\n### bot {code}: by hold of the lot (sell moment vs random moments of the same lots)")
        P("| hold | lots | mSOL/lot | buy>=1 SOL last 212 ms: sell / random | any buy last 212: sell / random | no buy last 500 ms: sell / random | outside sell last 212: sell / random |")
        P("|---|---|---|---|---|---|---|")
        for lo, hi in ((0, 1000), (1000, 2000), (2000, 4000), (4000, 8000), (8000, 15000), (15000, 1e9)):
            G = [f for f in F if lo <= f["hold"] < hi]
            if not G: continue
            S_ = [f for f in G if f["sell"]]; Rr = [f for f in G if not f["sell"]]
            c = lambda X, fn: np.mean([fn(f) for f in X]) if X else float("nan")
            P(f"| {lo / 1000:g}-{hi / 1000:g} s | {len(S_):,} | {1000 * np.mean([f['net'] for f in S_]):+.1f} | {c(S_, lambda f: f['maxb212'] >= 1):.3f} / {c(Rr, lambda f: f['maxb212'] >= 1):.3f} | "
              f"{c(S_, lambda f: f['buy212']):.3f} / {c(Rr, lambda f: f['buy212']):.3f} | {c(S_, lambda f: f['lastbuy'] > 500):.3f} / {c(Rr, lambda f: f['lastbuy'] > 500):.3f} | "
              f"{c(S_, lambda f: f['sell212']):.3f} / {c(Rr, lambda f: f['sell212']):.3f} |")
        # reaction-time histogram: time since the last outside buy (any size, and >= 1 SOL)
        P(f"\n### bot {code}: time since the last outside buy -> density ratio (sell / random), 25 ms bins up to 400 ms")
        ls = np.array([f["lastbuy"] for f in F if f["sell"]]); lr = np.array([f["lastbuy"] for f in F if not f["sell"]])
        bins = list(range(0, 425, 25)) + [600, 1000, 2000, 1e9]
        hs = np.histogram(ls, bins)[0] / len(ls); hr = np.histogram(lr, bins)[0] / len(lr)
        P("| ms since last outside buy | sells | random | ratio |"); P("|---|---|---|---|")
        for a, b, x, y in zip(bins[:-1], bins[1:], hs, hr): P(f"| {a:g}-{b:g} | {x:.4f} | {y:.4f} | {x / max(y, 1e-9):.2f} |")
    open(f"{OUT}/s3.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
