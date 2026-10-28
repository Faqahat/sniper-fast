#!/usr/bin/env python3
"""LIM step 9 (read-only): walk-forward choice of a fill policy (guard) on our live regular fires (data/lim/fires_cf.pkl).
Policies (all use only send-time information):
  G   one global guard g in {0, 1, 2, 3, 3.5, 4, 5, 6, 7.5, 10, 15, 20, none} %
  F:x guard per bucket of ONE send-time feature x (2 or 3 buckets, cut at train quantiles), each bucket's g chosen on train
      (a bucket with < 40 train fires uses the global g); x in drop, dump SOL, curve SOL, age, n10, b10, nsame, seller type,
      dump-slot leader client, spend.
  BEST = the family/feature with the best TRAIN net (penalised: -0.3 SOL per extra free parameter).
Walk-forward: train on all days before D, test on D (D3, D4, D5; D6 is 2 h, shown).
Net SOL = exact replay at the measured position, run's own exit, minus costs (fill 3.52 / failed 0.53 mSOL); fol 1.0/0.9/0.8.
Out: data/lim/l9.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
CF, CX = 3.52e-3, 0.53e-3
GR = [0.0, 0.01, 0.02, 0.03, 0.035, 0.04, 0.05, 0.06, 0.075, 0.10, 0.15, 0.20, 9.0]
FEATS = ["drop", "dsol", "vpost", "age", "n10", "b10", "nsame", "stype", "dclient", "spend"]
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def net(r, g, fo=1.0):
    return (r["pn"][(r["hold"], fo)] - CF) if r["need"] <= 1 + g + 1e-9 else -CX


def bucketer(train, f):
    if f in ("stype", "dclient"):
        cats = collections.Counter(r[f] for r in train)
        keep = [c for c, n in cats.items() if n >= 40]
        return lambda r: r[f] if r[f] in keep else "_other", sorted(keep) + ["_other"]
    x = np.array([r[f] for r in train if r[f] is not None], float)
    qs = np.percentile(x, [33.3, 66.7])
    return (lambda r: -1 if r[f] is None else int(np.searchsorted(qs, r[f]))), [-1, 0, 1, 2]


def fit(train, f):
    gg = max(GR, key=lambda g: sum(net(r, g) for r in train))
    if f is None: return (lambda r: gg), sum(net(r, gg) for r in train), 1, {"all": gg}
    bk, labels = bucketer(train, f)
    choice = {}
    for b in labels:
        v = [r for r in train if bk(r) == b]
        choice[b] = gg if len(v) < 40 else max(GR, key=lambda g: sum(net(r, g) for r in v))
    pol = lambda r: choice.get(bk(r), gg)
    return pol, sum(net(r, pol(r)) for r in train), len(set(choice.values())), choice


def main():
    R = [r for r in pickle.load(open(f"{OUT}/fires_cf.pkl", "rb")) if not r["mayhem"]]
    days = sorted({r["day"] for r in R})
    P("# Walk-forward fill policy on our live regular fires (measured positions, exact replay, run's own exit)")
    P("\n## In-sample curve: net SOL by global guard, all fires, per day (fol 1.0)")
    P("| guard | " + " | ".join(f"D{d}" for d in days) + " | all | fol 0.8 all |"); P("|---|" + "---|" * (len(days) + 2))
    for g in GR:
        P(f"| {'none' if g > 1 else f'+{100*g:g}%'} | " + " | ".join(f"{sum(net(r, g) for r in R if r['day'] == d):+.2f}" for d in days) +
          f" | {sum(net(r, g) for r in R):+.2f} | {sum(net(r, g, 0.8) for r in R):+.2f} |")
    P("\n## Walk-forward (train = days before the test day)")
    P("| test day | fires | live +5% | global g (train pick) | best one-feature policy (train pick) | its test net fol 1.0 / 0.9 / 0.8 | live fol 0.8 |")
    P("|---|---|---|---|---|---|---|")
    tot = collections.Counter()
    for d in days[1:]:
        tr = [r for r in R if r["day"] < d]; te = [r for r in R if r["day"] == d]
        live = sum(net(r, 0.05) for r in te)
        pg, trg, _, cg = fit(tr, None)
        cands = [("global", pg, trg, 1, cg)]
        for f in FEATS:
            pol, sc, k, ch = fit(tr, f)
            cands.append((f, pol, sc - 0.3 * (k - 1), k, ch))
        best = max(cands, key=lambda c: c[2])
        gl = sum(net(r, pg(r)) for r in te)
        b1, b9, b8 = (sum(net(r, best[1](r), fo) for r in te) for fo in (1.0, 0.9, 0.8))
        tot["live"] += live; tot["glob"] += gl; tot["best"] += b1; tot["best8"] += b8; tot["live8"] += sum(net(r, 0.05, 0.8) for r in te)
        P(f"| {L.day_name(d)} | {len(te)} | {live:+.3f} | g={cg['all']:.3f} -> {gl:+.3f} | {best[0]} {best[4]} | {b1:+.3f} / {b9:+.3f} / {b8:+.3f} | {sum(net(r, 0.05, 0.8) for r in te):+.3f} |")
    P(f"| total | | {tot['live']:+.3f} | {tot['glob']:+.3f} | | {tot['best']:+.3f} / - / {tot['best8']:+.3f} | {tot['live8']:+.3f} |")
    # bootstrap on the pooled test days: global tighter guard vs live
    te = [r for r in R if r["day"] > days[0]]
    for g in (0.03, 0.035, 0.04):
        dlt = np.array([net(r, g) - net(r, 0.05) for r in te]); rng = np.random.default_rng(4)
        bs = [dlt[rng.integers(0, len(dlt), len(dlt))].sum() for _ in range(2000)]
        P(f"- guard +{100*g:g}% vs +5% on days D3+: delta {dlt.sum():+.3f} SOL [90%: {np.percentile(bs,5):+.3f} .. {np.percentile(bs,95):+.3f}]; per day: " +
          ", ".join(f"D{d} {sum(net(r, g) - net(r, 0.05) for r in R if r['day'] == d):+.2f}" for d in days))
    open(f"{OUT}/l9.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
