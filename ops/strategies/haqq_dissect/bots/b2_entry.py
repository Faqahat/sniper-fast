#!/usr/bin/env python3
"""BOTS step 2 (read-only): WHICH dumps do bots 247 / 248 buy? Universe = dv8 uni.npz candidates (outside sell drop >= 5 %, sell >= 0.5
SOL, curve > 30.52, age <= 30 min), usable tape hours, non-mayhem. 95 % of their dump-reactive lots are inside it (b1).
Label y_c = bot c bought this dump (a code-c lot whose biggest preceding drop is this dump, <= 2 slots after it). MEASURED.
Extra decision-time features (all from rows BEFORE the dump): leader client class of the dump slot + near flag; per haqq code: an open
lot on the mint at the dump (247 / 248 / 244 / any other code); the same code's previous lot on the mint (closed before the dump):
its return and seconds since it closed.
Out: bots/b2.npz (features, labels, per-candidate meta), b2.txt (univariate selection tables)"""
import sys, pickle, collections, json, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
from plib import load, Out
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
BOTS = (247, 248)


def main():
    t0 = time.time()
    P = Out(f"{OUT}/b2.txt")
    B, LO, T = load()
    ids, idm = L.ids_map()
    rows = pickle.load(open(f"{OUT}/b1.pkl", "rb"))
    from g1_walkforward import load as uload
    d = uload()
    M = d["M"]; X = d["X"].astype(np.float64); feats = [str(f) for f in d["feats"]]
    use = d["usable"]
    N = len(M)
    # ---- labels
    Y = {c: np.zeros(N, bool) for c in BOTS + (244, 226)}
    YN = {c: np.zeros(N) for c in BOTS}     # his net on that dump (sum of the code's lots on it)
    for r in rows:
        if r["u"] is not None and r["dump"] and r["code"] in Y:
            Y[r["code"]][r["u"]] = True
            if r["code"] in YN: YN[r["code"]][r["u"]] += r["net"]
    hq_any = M["hq"]
    # ---- haqq per-code lots per mint: (buy cc, close cc, code, return)
    bym = collections.defaultdict(list)
    for l in LO:
        if l["code"] is None: continue
        b = B[l["b"]]
        mi = idm.get(b["mint"])
        if mi is None: continue
        cl = l.get("cclose_cc") or 1e18
        bym[mi].append((b["cc"], cl, l["code"], l["cgross"] / max(l["cost"], 1e-9)))
    OPEN = np.zeros((N, 4), np.float32)          # 247, 248, 244, other code open at the dump
    PREV = np.full((N, 4), np.nan, np.float32)   # for 247 and 248: previous same-code lot return, seconds since close
    cc = M["cc"]; mint = M["mint"].astype(np.int64)
    idx_by_m = collections.defaultdict(list)
    for i in np.flatnonzero(np.isin(mint, np.array(list(bym.keys()), np.int64))): idx_by_m[int(mint[i])].append(i)
    for mi, ii in idx_by_m.items():
        ls = bym[mi]
        bc = np.array([x[0] for x in ls]); clc = np.array([x[1] for x in ls]); co = np.array([x[2] for x in ls]); rt = np.array([x[3] for x in ls])
        for i in ii:
            t = cc[i]; op = (bc < t) & (clc > t)
            OPEN[i, 0] = (op & (co == 247)).any(); OPEN[i, 1] = (op & (co == 248)).any(); OPEN[i, 2] = (op & (co == 244)).any()
            OPEN[i, 3] = (op & ~np.isin(co, (247, 248, 244))).any()
            for k, c in enumerate(BOTS):
                pm = (co == c) & (clc < t)
                if pm.any():
                    j = np.flatnonzero(pm)[np.argmax(clc[pm])]
                    PREV[i, 2 * k] = rt[j] - 1; PREV[i, 2 * k + 1] = (t - clc[j]) / 1000
    print(f"open/prev features ({time.time() - t0:.0f}s)", flush=True)
    lc = d["lcls"]; LC = np.stack([(lc == k) for k in ("bam", "harmonic", "jito", "fd", "agave")], 1).astype(np.float32)
    XF = np.hstack([X, LC, d["near"][:, None].astype(np.float32), OPEN, PREV])
    fnames = feats + ["L_bam", "L_harmonic", "L_jito", "L_fd", "L_agave", "near", "open247", "open248", "open244", "open_other",
                      "prev247_ret", "prev247_s", "prev248_ret", "prev248_s"]
    np.savez(f"{OUT}/b2.npz", XF=XF.astype(np.float32), fnames=np.array(fnames), Y247=Y[247], Y248=Y[248], Y244=Y[244], Y226=Y[226],
             N247=YN[247], N248=YN[248], use=use, day=d["day"])
    # ---- univariate selection tables
    day = d["day"]; m = use
    P(f"# Bots 247 / 248: which dumps they buy (dv8 universe, usable hours, non-mayhem): {m.sum():,} dumps D0-D6")
    for c in BOTS:
        y = Y[c] & m
        P(f"- {c}: bought {y.sum():,} dumps ({100 * y.sum() / m.sum():.2f}%), his net on them {YN[c][m].sum():+.2f} SOL; per day: "
          + ", ".join(f"D{k} {int((y & (day == k)).sum())}/{int((m & (day == k)).sum())}" for k in range(7)))
    P(f"- overlap: both 247 and 248 bought {int((Y[247] & Y[248] & m).sum()):,}; 247 only {int((Y[247] & ~Y[248] & m).sum()):,}; 248 only {int((~Y[247] & Y[248] & m).sum()):,}")
    F = {n: XF[:, i] for i, n in enumerate(fnames)}
    def tab(name, edges, fmt="{:.2f}"):
        x = F[name]
        P(f"\n## {name}")
        P("| bin | dumps | 247 buy % | 247 net mSOL/bought dump | 248 buy % | 248 net mSOL/bought dump | share of 247 buys | share of 248 buys |")
        P("|---|---|---|---|---|---|---|---|")
        for a, b in zip(edges[:-1], edges[1:]):
            s = m & (x >= a) & (x < b)
            if s.sum() < 50: continue
            cells = []
            for c in BOTS:
                yy = Y[c] & s
                cells.append(f"{100 * yy.sum() / s.sum():.2f} | {1000 * YN[c][yy].sum() / max(yy.sum(), 1):+.1f}")
            P(f"| {fmt.format(a)}..{fmt.format(b)} | {s.sum():,} | {cells[0]} | {cells[1]} | {100 * (Y[247] & s).sum() / max((Y[247] & m).sum(), 1):.0f}% | {100 * (Y[248] & s).sum() / max((Y[248] & m).sum(), 1):.0f}% |")
    inf = 1e9
    tab("drop", [0.05, 0.07, 0.10, 0.15, 0.20, 0.30, 0.50, 1.01])
    tab("sell_sol", [0.5, 1, 2, 3, 5, 8, 15, inf])
    tab("sell_pct", [0, 1, 2, 3, 5, 8, 15, inf])
    tab("vpost", [30, 32, 35, 40, 50, 60, 80, inf], "{:.0f}")
    tab("age_s", [0, 5, 15, 30, 60, 120, 300, 900, 1801], "{:.0f}")
    tab("n_dumps", [0, 1, 2, 3, 5, 10, 20, inf], "{:.0f}")
    tab("n_tr", [0, 10, 25, 50, 100, 200, 500, inf], "{:.0f}")
    tab("b10", [0, 1, 3, 6, 10, 20, inf])
    tab("nb3", [0, 1, 2, 3, 5, 8, inf], "{:.0f}")
    tab("ath_dd", [0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.01])
    tab("last_dump_s", [0, 1, 3, 10, 30, 100, 998, inf], "{:.0f}")
    for nm in ("d_dev", "d_bund", "d_early", "d_fb", "dev_sold", "near", "L_bam", "L_harmonic", "L_jito", "L_fd", "L_agave", "hq_open", "open247", "open248", "open244", "open_other"):
        tab(nm, [0, 0.5, 1.5])
    tab("hour", list(range(0, 25, 3)), "{:.0f}")
    P.save()
    print(f"done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
