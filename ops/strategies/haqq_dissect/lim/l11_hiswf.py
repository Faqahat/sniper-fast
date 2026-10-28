#!/usr/bin/env python3
"""LIM step 11 (read-only): a smarter limit learned on haqq's (much larger) behind-the-crowd sample, tested walk-forward on OUR fires.
Train (days < D): haqq's DIP fills with pr in (1.05, 1.20] replayed at his position with a 5-slot timer (hfeat.pkl), per bucket
of one send-time feature (terciles on train; categories for seller type). A fire is loosened if it hits >= k 'loosen' buckets (k picked on haqq's train days). A bucket is 'loosen' if his h5 return there is
>= +1.2 %/SOL (our extra fill costs ~0.7 %/SOL) on >= 150 lots AND positive on >= 60% of train days.
Policy on test day D (our fires): guard +15% if the fire is in ANY 'loosen' bucket, else +5% (variants: +10%).
Out: data/lim/l11.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
CF, CX = 3.52e-3, 0.53e-3
MAP = {"dj_drop": "drop", "d_sol": "dsol", "v_post": "vpost", "age": "age", "n10": "n10", "nsame": "nsame", "b10": "b10"}
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def net(r, g, fo=1.0):
    return (r["pn"][(r["hold"], fo)] - CF) if r["need"] <= 1 + g + 1e-9 else -CX


def main():
    H = [r for r in pickle.load(open(f"{OUT}/hfeat.pkl", "rb")) if not r["mayhem"] and 1.05 < r["pr"] <= 1.20]
    R = [r for r in pickle.load(open(f"{OUT}/fires_cf.pkl", "rb")) if not r["mayhem"]]
    P("# Smarter limit learned on haqq's behind-crowd fills, tested walk-forward on our fires (exit = run's own; fol 1.0 / 0.8)")
    P("| test day | loosen buckets chosen on haqq days < D | our fires in them | live +5% | policy (+15% in buckets) | policy (+10%) | fol 0.8: live / +15% |")
    P("|---|---|---|---|---|---|---|")
    T = collections.Counter()
    for d in sorted({r["day"] for r in R})[1:]:
        tr = [h for h in H if h["day"] < d]; tdays = sorted({h["day"] for h in tr})
        rules = []
        for hf, of in MAP.items():
            x = np.array([h[hf] for h in tr if h.get(hf) is not None], float)
            q = np.percentile(x, [33.3, 66.7]); edges = [(-np.inf, q[0]), (q[0], q[1]), (q[1], np.inf)]
            for lo, hi in edges:
                v = [h for h in tr if h.get(hf) is not None and lo < h[hf] <= hi]
                if len(v) < 150: continue
                ret = 100 * sum(h["rep"][(5, 1.0)] for h in v) / sum(h["spend"] for h in v)
                pd = [sum(h["rep"][(5, 1.0)] for h in v if h["day"] == dd) for dd in tdays if sum(h["day"] == dd for h in v) >= 20]
                if ret >= 1.2 and pd and np.mean(np.array(pd) > 0) >= 0.6: rules.append((of, lo, hi, round(ret, 2)))
        for c in ("dev", "bundler", "early", "fbot", "other"):
            v = [h for h in tr if h["stype"] == c]
            if len(v) < 150: continue
            ret = 100 * sum(h["rep"][(5, 1.0)] for h in v) / sum(h["spend"] for h in v)
            pd = [sum(h["rep"][(5, 1.0)] for h in v if h["day"] == dd) for dd in tdays if sum(h["day"] == dd for h in v) >= 20]
            if ret >= 1.2 and pd and np.mean(np.array(pd) > 0) >= 0.6: rules.append(("stype", c, c, round(ret, 2)))
        def nb(r):
            k = 0
            for of, lo, hi, _ in rules:
                if of == "stype": k += r["stype"] == lo
                elif r[of] is not None and lo < r[of] <= hi: k += 1
            return k
        # how many 'loosen' buckets a fire must hit: chosen on haqq's train days (best h5 return at >= 300 lots)
        bestk, bestv = 1, -9
        for k in range(1, 8):
            v = [h for h in tr if nb({"stype": h["stype"], **{of: h.get(hf) for hf, of in MAP.items()}}) >= k]
            if len(v) >= 300:
                ret = 100 * sum(h["rep"][(5, 1.0)] for h in v) / sum(h["spend"] for h in v)
                if ret > bestv: bestk, bestv = k, ret
        inb = lambda r: nb(r) >= bestk
        te = [r for r in R if r["day"] == d]
        live = sum(net(r, 0.05) for r in te)
        p15 = sum(net(r, 0.15 if inb(r) else 0.05) for r in te); p10 = sum(net(r, 0.10 if inb(r) else 0.05) for r in te)
        l8 = sum(net(r, 0.05, 0.8) for r in te); p8 = sum(net(r, 0.15 if inb(r) else 0.05, 0.8) for r in te)
        T["live"] += live; T["p15"] += p15; T["p10"] += p10; T["l8"] += l8; T["p8"] += p8
        P(f"| {L.day_name(d)} | k>={bestk} of: {'; '.join(f'{a} {b:.3g}..{c:.3g} ({e:+.1f}%)' if a != 'stype' else f'seller={b} ({e:+.1f}%)' for a, b, c, e in rules) or 'none'} (haqq train h5 {bestv:+.1f}%) | "
          f"{sum(inb(r) for r in te)} / {len(te)} | {live:+.3f} | {p15:+.3f} | {p10:+.3f} | {l8:+.3f} / {p8:+.3f} |")
    P(f"| total | | | {T['live']:+.3f} | {T['p15']:+.3f} | {T['p10']:+.3f} | {T['l8']:+.3f} / {T['p8']:+.3f} |")
    open(f"{OUT}/l11.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
