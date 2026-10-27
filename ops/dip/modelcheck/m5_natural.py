#!/usr/bin/env python3
# MODEL CHECK step 5: natural experiments on how dip buyers react to an EXTRA early buyer.
# (a) attempts (att_<day>.npz): target bots' success at the same price ratio, with vs without another target bot's buy landed
#     between the dump and their first tx (does it matter who moved the price, or only how much?)
# (b) dumps (day arrays): follower buy SOL after the early window vs the number of early fast buyers (target bots landing
#     <= 60 ms after the dump), within strata of the M2 score / dump size (selection: attractive dumps attract both).
#     The model's assumption: later followers buy the same SOL whoever bought early (only slippage drops).
# usage: nice python3 -I m5_natural.py
import sys, os, json, zlib, collections, gzip
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import mc_lib as M
OUT = M.OUT
TG = [l.strip() for l in open(os.path.join(HERE, "targets.txt")) if l.strip()]
TGU = {zlib.crc32(w.encode()): w for w in TG}; TGA = np.array(list(TGU), np.int64)
BINS = [0, 1.002, 1.01, 1.02, 1.03, 1.05, 1.10, 1.20, 99]
BL = ["<1.002", "1.002-1.01", "1.01-1.02", "1.02-1.03", "1.03-1.05", "1.05-1.10", "1.10-1.20", ">1.20"]

def part_a():
    A = collections.defaultdict(list)
    for day in ("R1", "R2", "R3", "R4"):
        z = np.load(f"{OUT}/att_{day}.npz")
        for k in z.files: A[k].append(z[k])
    A = {k: np.concatenate(v) for k, v in A.items()}
    fresh = ~A["held"].astype(bool) & (A["age"] <= 1622)
    isT = np.isin(A["u"], TGA); ok = A["ok"].astype(float); b = np.digitize(A["ratio"], BINS) - 1
    print("(a) target bots: success rate at the same price ratio, another target bot landed a buy ahead (yes) vs not (no)")
    print(f"  {'wallet':12s} " + " ".join(f"{x:>17s}" for x in BL))
    def line(name, m):
        cells = []
        for x in range(len(BL)):
            y = m & (b == x) & (A["tga"] > 0); n_ = m & (b == x) & (A["tga"] == 0)
            if y.sum() >= 20 and n_.sum() >= 20: cells.append(f"{ok[n_].mean():4.0%}/{ok[y].mean():4.0%} ({int(y.sum()):4d})")
            else: cells.append(f"{'-':>17s}")
        print(f"  {name:12s} " + " ".join(f"{c:>17s}" for c in cells))
    line("all targets", fresh & isT)
    cnt = collections.Counter(A["u"][fresh & isT].tolist())
    for u, _ in cnt.most_common(14): line(TGU[u][:8], fresh & (A["u"] == u))
    print("  (cells: success without / with a target bot ahead (n with))")

def part_b():
    import m1_trades as T1
    rows = []
    for day in ("R1", "R2", "R3", "R4"):
        d = M.load_day(day); PF = T1.pick_flags(day)
        isT = np.isin(d["uid"], TGA)
        for t in range(len(d["meta"])):
            n = int(d["cnt"][t])
            if n < 5: continue
            tp = M.Tape(d, t); o = tp.o; mv = d["move"][o:o + n]; age = d["age"][o:o + n]; tg = isT[o:o + n]
            for j0 in range(n):
                if tp.B[j0] or tp.SOL[j0] < 1e9 or mv[j0] > -2.0 or tp.V[j0] >= 100e9 or not (5 <= age[j0] <= 1622): continue
                pf = PF.get(o + j0)
                if pf is None or not pf["env"]: continue
                a0 = tp.A[j0]; s0 = tp.S[j0]
                e_n = 0; e_sol = 0.0; f_sol = 0.0; f_nt = 0.0; f_tg = 0.0; nb_f = 0; seen = set(); post = tp.V[j0] / tp.T[j0]; pk = post
                for j in range(j0 + 1, n):
                    if tp.S[j] > s0 + 4: break
                    if not tp.B[j]: continue
                    dl = tp.A[j] - a0
                    if dl <= 60:
                        if tg[j] and tp.U[j] not in seen: e_n += 1; e_sol += tp.SOL[j]; seen.add(tp.U[j])
                    else:
                        f_sol += tp.SOL[j]; nb_f += 1
                        if tg[j]: f_tg += tp.SOL[j]
                        else: f_nt += tp.SOL[j]
                rows.append((day, pf["m2s"], tp.SOL[j0] / 1e9, -mv[j0], tp.V[j0] / 1e9, age[j0], pf["since_buy"], e_n, e_sol / 1e9, f_sol / 1e9, f_nt / 1e9, f_tg / 1e9, nb_f))
        print(f"  {day}: {len(rows)} envelope dumps so far", flush=True)
    R = np.array([r[1:] for r in rows], float)
    m2, dsol, drop, curve, agev, sb, en, esol, fsol, fnt, ftg, nbf = R.T
    print("\n(b) envelope dumps: follower buy SOL (landing > 60 ms after the dump, up to 4 slots) vs the number of target bots landing <= 60 ms")
    q = np.quantile(m2, [0, .25, .5, .75, .9, 1.0]); qb = np.clip(np.searchsorted(q, m2, side="right") - 1, 0, 4)
    print(f"  {'M2 score band':16s} {'n dumps':>8s} | follower SOL (all / non-target / target) by early target bots = 0, 1, 2+")
    for k in range(5):
        cells = []
        for e in (0, 1, 2):
            m = (qb == k) & ((en == e) if e < 2 else (en >= 2))
            cells.append(f"{int(m.sum()):5d}: {fsol[m].mean():5.2f} / {fnt[m].mean():5.2f} / {ftg[m].mean():5.2f}" if m.sum() else "-")
        print(f"  {f'q{k} ({q[k]:.3f}..)':16s} {int((qb == k).sum()):8d} | " + " | ".join(cells))
    # OLS: follower SOL on early-bot count + controls
    X = np.column_stack([np.ones(len(R)), en, dsol, drop, curve, np.log1p(agev), np.log1p(np.minimum(sb, 30)), m2])
    for name, y in (("all followers", fsol), ("non-target followers", fnt), ("target-bot followers", ftg)):
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        res = y - X @ beta; s2 = (res ** 2).sum() / (len(y) - X.shape[1]); se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
        print(f"  OLS {name:22s}: each extra early target bot -> {beta[1]:+.3f} SOL of follower buys (se {se[1]:.3f}); mean {y.mean():.2f} SOL; early-bot mean SOL {esol[en > 0].mean():.2f}")
    np.save(f"{OUT}/m5_dumps.npy", R)

if __name__ == "__main__":
    part_a(); part_b()
