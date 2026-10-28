#!/usr/bin/env python3
"""BOTS step 8b (read-only): EMPIRICAL PROXY without exit selection. For every dump 247 / 248 bought, and for a CONTROL set of comparable
dumps no haqq bot bought (same envelope: 247-like = token <= 15 s old and seller bought in the first 10 slots; 248-like = drop >= 10 %;
both: dv8 universe, usable, non-mayhem, sampled), take EVERY real outside buyer (not haqq, not ours) landing k outside trades after the dump
within slots dump..dump+2, and value the tokens THEY actually got at their REAL entry price, sold (exact curve formula) into the real
curve state 2 s and 4 s after their buy. No landing model (their position and fill price are real); the exit is a fixed-time mark
(their own later trades ignored). Return per SOL, pump fees included, tx costs excluded.
Out: bots/b8b.txt"""
import sys, json, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
import dv8lib as L
from plib import boot_mean, Out
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
KB = [(0, 0), (1, 1), (2, 3), (4, 7), (8, 12)]
SZ = (0.2, 0.6) if len(sys.argv) > 1 and sys.argv[1] == "size" else None      # variant: only buyers of 0.2-0.6 SOL (our size class)


def main():
    P = Out(f"{OUT}/b8b{'_size' if SZ else ''}.txt")
    Z2 = np.load(f"{OUT}/b2.npz"); fn = list(Z2["fnames"]); XF = Z2["XF"]; use = Z2["use"]; day = Z2["day"]
    U = np.load(f"{L.D}/uni.npz"); M = U["M"]; hq = M["hq"]
    rng = np.random.default_rng(4)
    sets = {}
    for c in (247, 248):
        y = Z2[f"Y{c}"] & use
        sets[(c, "his picks")] = np.flatnonzero(y)
        env = use & ~hq & ~Z2["Y247"] & ~Z2["Y248"] & ~Z2["Y244"] & ~Z2["Y226"]
        env &= ((XF[:, fn.index("age_s")] <= 15) & (XF[:, fn.index("d_early")] > 0.5)) if c == 247 else (XF[:, fn.index("drop")] >= 0.10)
        cand = np.flatnonzero(env); sets[(c, "control: same envelope, no haqq bot bought")] = rng.choice(cand, min(8000, len(cand)), replace=False)
    need = np.unique(np.concatenate(list(sets.values())))
    ids, idm = L.ids_map(); our = [idm[w] for w in L.WAL.values() if w in idm]; H = idm[L.HAQQ]
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    mints = np.unique(M["mint"][need])
    sel = np.isin(np.asarray(T["mint"]), mints) & ~np.isin(np.asarray(T["user"]), our)
    cols = ("slot", "idx", "mint", "user", "buy", "sol", "tok", "vsol", "vtok", "fee_bps", "cfee_bps")
    S = np.zeros(int(sel.sum()), dtype=[(c, T.dtype[c]) for c in cols])
    for c in cols: S[c] = np.asarray(T[c])[sel]
    S = S[np.lexsort((S["idx"], S["slot"], S["mint"]))]
    um, st = np.unique(S["mint"], return_index=True); en = np.append(st[1:], len(S)); span = {int(m): (int(a), int(b)) for m, a, b in zip(um, st, en)}
    cc_all = L.cc(S["slot"].astype(np.int64), S["idx"].astype(np.int64))
    P("# Proxy without exit selection: every real buyer k trades after the dump, real entry, tokens marked (exact sell) 2 s / 4 s later (MEASURED entries)")
    P("| set | bot | k | buyers | per SOL at +2 s [90%] | per SOL at +4 s [90%] | win at +4 s | days > 0 (+4 s) | +2 s, haqq rows removed | +4 s, haqq rows removed [90%] |"); P("|---|---|---|---|---|---|---|---|---|---|")
    for (c, nm), us_ in sets.items():
        res = collections.defaultdict(list)
        for u in us_.tolist():
            m = int(M["mint"][u]); a, b = span[m]; X = S[a:b]; cc = cc_all[a:b]
            sl = X["slot"].astype(np.int64); ix = X["idx"].astype(np.int64)
            jd = np.flatnonzero((sl == M["slot"][u]) & (ix == M["idx"][u]) & (X["buy"] == 0))
            if not len(jd): continue
            jd = int(jd[0]); hi = int(np.searchsorted(sl, sl[jd] + 2, side="right"))
            vs = X["vsol"].astype(np.float64) / 1e9; vt = X["vtok"].astype(np.float64)
            fee = (X["fee_bps"].astype(np.float64) + X["cfee_bps"]) / 1e4; fee = np.where(fee > 0, fee, 0.0125)
            for k, j in enumerate(range(jd + 1, min(hi, jd + 14))):
                if not X["buy"][j] or X["user"][j] == H: continue
                tok = float(X["tok"][j]); cost = X["sol"][j] / 1e9 * (1 + fee[j])
                if cost <= 0.01 or (SZ and not (SZ[0] <= cost <= SZ[1])): continue
                out = []
                for dt in (2000, 4000):
                    q = int(np.searchsorted(cc, cc[j] + dt, side="right")) - 1
                    V, Tt = vs[q], vt[q]; out.append((V - V * Tt / (Tt + tok)) * (1 - fee[j]) / cost - 1)
                # same marks with every haqq row after the buyer's entry removed (exact semantics: buys keep SOL, sells keep tokens)
                V = vs[j]; Tt = vt[j]; K = V * Tt; q4 = int(np.searchsorted(cc, cc[j] + 4000, side="right")) - 1; q2 = int(np.searchsorted(cc, cc[j] + 2000, side="right")) - 1
                for r in range(j + 1, q4 + 1):
                    if X["user"][r] != H:
                        if X["buy"][r]: V += X["sol"][r] / 1e9; Tt = K / V
                        else: Tt += float(X["tok"][r]); V = K / Tt
                    if r == q2: out.append((V - K / (Tt + tok)) * (1 - fee[j]) / cost - 1)
                if q2 <= j: out.append(out[0])
                out.append((V - K / (Tt + tok)) * (1 - fee[j]) / cost - 1)
                out = [out[0], out[1], out[2], out[3]]
                for kb in KB:
                    if kb[0] <= k <= kb[1]: res[kb].append((out[0], out[1], int(day[u]), out[2], out[3]))
        for kb in KB:
            v = res.get(kb, [])
            if len(v) < 30: continue
            r2 = np.array([x[0] for x in v]); r4 = np.array([x[1] for x in v]); d = np.array([x[2] for x in v])
            l2 = boot_mean(r2); l4 = boot_mean(r4); pdm = [r4[d == k].mean() for k in range(7) if (d == k).sum() >= 20]
            x2 = np.array([x[3] for x in v]); x4 = np.array([x[4] for x in v]); lx = boot_mean(x4)
            P(f"| {nm} | {c} | {kb[0]}-{kb[1]} | {len(v):,} | {100 * r2.mean():+.2f}% [{100 * l2[0]:+.2f}..{100 * l2[1]:+.2f}] | {100 * r4.mean():+.2f}% [{100 * l4[0]:+.2f}..{100 * l4[1]:+.2f}] | "
              f"{100 * np.mean(r4 > 0):.0f}% | {sum(x > 0 for x in pdm)}/{len(pdm)} | {100 * x2.mean():+.2f}% | {100 * x4.mean():+.2f}% [{100 * lx[0]:+.2f}..{100 * lx[1]:+.2f}] |")
    P.save()


if __name__ == "__main__":
    main()
