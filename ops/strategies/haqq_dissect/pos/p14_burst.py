#!/usr/bin/env python3
"""pos step 14 (read-only): the main session's 'burst' battleground signal, multi-day, and as a rule for US.
Burst slot (main session c1.py definition): a slot with >= 3 outside buys of >= 0.5 SOL each on the mint (haqq's and our trades
excluded). Repeat burst wallets: signers that bought in >= 2 different burst slots of the mint. Features count only SLOTS STRICTLY
BEFORE the decision slot (causal; the engine sees completed slots).
 A. haqq's lots (code-matched, all days) by prior burst slots / repeat wallets, first lots vs adds, per day.
 B. dv8 uni dumps by prior bursts: ideal and our reactive landing (rank, 5-slot), calibrated, haqq per lot.
 C. Rule for US on battleground tokens (prior bursts >= B): buy the dump
      reactive  : dv8 rank landing (4 draws, +5% guard);
      pre-send  : p8c contention model (k from our 1,144 live pre-send fills), fill if entry price <= 0.88 x pre-dump price;
    exits: timer 2 / 5 slots, WAVE = sell in the slot after the first slot (after entry) with no outside buy >= 0.1 SOL (cap 30).
    Walk-forward: (B, exit, min drop) chosen on D-1 by calibrated NOW, tested on D. Calibrated = 0.61 x model - 1.17 mSOL/fire;
    costs NOW 3.52 per fill + 0.53 per failed reactive fire; CHEAP 0.66 / 0.04; pre-send failed tries not counted here (p10: ~0.6 SOL/day
    at 2 tries/slot); -10% followers = outside buy SOL after entry x 0.9.
Out: p14.txt"""
import sys, json, pickle, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import p6_rules as R6
import dv8lib as L
from plib import Out, OUT, day_name, load, boot_sum
P = Out(f"{OUT}/p14.txt")
SH = np.int64(1) << np.int64(33)
EDG = (0, 1, 2, 3, 5, 8, 13, 10 ** 6); QM = {0: 0.0, 1: 0.24, 2: 0.26, 3: 0.21, 4: 0.22, 5: 0.17, 6: 0.13}   # p8c bucket means


def main():
    t0 = time.time()
    ids, idm = L.ids_map(); h = idm[L.HAQQ]; our = [idm[w] for w in L.WAL.values() if w in idm]
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    keep = ~np.isin(np.asarray(T["user"]), our)
    mi = np.asarray(T["mint"])[keep]; o = np.argsort(mi, kind="stable")
    MI = mi[o].astype(np.int64); SG = np.asarray(T["signer"])[keep][o].astype(np.int64); US = np.asarray(T["user"])[keep][o].astype(np.int64)
    del keep, mi, o
    tape = R6.Tape(); SL = tape.sl; BU = tape.bu; SO = tape.so
    big = BU & (SO >= 0.5) & (SG != h) & (US != h)
    bk = (MI[big] << 33) | SL[big]
    uk, cnt = np.unique(bk, return_counts=True); burst = uk[cnt >= 3]
    inb = np.isin(bk, burst)
    m3 = MI[big][inb]; s3 = SL[big][inb]; w3 = SG[big][inb]
    oo = np.lexsort((s3, w3, m3)); m3, s3, w3 = m3[oo], s3[oo], w3[oo]
    # distinct (m, w, s); 2nd distinct slot per (m, w) = repeat event
    d = np.r_[True, (m3[1:] != m3[:-1]) | (w3[1:] != w3[:-1]) | (s3[1:] != s3[:-1])]
    m3, s3, w3 = m3[d], s3[d], w3[d]
    first = np.r_[True, (m3[1:] != m3[:-1]) | (w3[1:] != w3[:-1])]
    grp = np.cumsum(first) - 1; pos = np.arange(len(m3)) - np.flatnonzero(first)[grp]
    rep = np.sort((m3[pos == 1] << 33) | s3[pos == 1])
    print(f"burst slots {len(burst):,}, repeat-wallet events {len(rep):,} ({time.time() - t0:.0f}s)", flush=True)

    def before(keys, m, s):
        m = np.asarray(m, np.int64); s = np.asarray(s, np.int64)
        return np.searchsorted(keys, (m << 33) | s, "left") - np.searchsorted(keys, m << 33, "left")

    # ---------------- A. haqq's lots
    B, LO, TR = load()
    lm = np.array([idm[B[l["b"]]["mint"]] for l in LO]); ls = np.array([B[l["b"]]["slot"] for l in LO])
    nb_l = before(burst, lm, ls); nr_l = before(rep, lm, ls)
    okl = np.array([(not l["probe"]) and (not TR[l["trip_ix"]]["mayhem"]) and (not TR[l["trip_ix"]]["gap"]) and l["code"] not in (234, None) for l in LO])
    cnet = np.array([l["cnet"] for l in LO]); cost = np.array([l["cost"] for l in LO]); kb = np.array([l["kbuy"] for l in LO]); dl = np.array([l["day"] for l in LO])
    P(f"# Burst battlegrounds (burst slots {len(burst):,}; repeat-wallet events {len(rep):,})")
    P("\n## A. haqq's lots (code-matched; dead-curve bot 234 + probes excluded) by prior burst slots on the token")
    P("| lots | prior bursts | n | return per SOL | net SOL [90%] | win | per-day net D0..D5 | days > 0 |"); P("|---|---|---|---|---|---|---|---|")
    for role, rm in (("all", okl), ("first lots", okl & (kb == 1)), ("adds", okl & (kb > 1))):
        for nm, f in (("0", nb_l == 0), ("1", nb_l == 1), ("2-3", (nb_l >= 2) & (nb_l <= 3)), ("4-9", (nb_l >= 4) & (nb_l <= 9)), ("10+", nb_l >= 10)):
            m = rm & f
            if m.sum() < 30: continue
            lo, hi = boot_sum(cnet[m]); pd = [cnet[m & (dl == d)].sum() for d in range(6)]
            P(f"| {role} | {nm} | {int(m.sum()):,} | {100 * cnet[m].sum() / cost[m].sum():+.2f}% | {cnet[m].sum():+.2f} [{lo:+.1f}..{hi:+.1f}] | {100 * (cnet[m] > 0).mean():.0f}% | "
              + " ".join(f"{p:+.1f}" for p in pd) + f" | {sum(p > 0 for p in pd)}/6 |")
    P("\nhaqq's lots by prior repeat burst wallets:")
    for nm, f in (("0", nr_l == 0), ("1-2", (nr_l >= 1) & (nr_l <= 2)), ("3+", nr_l >= 3)):
        m = okl & f; pd = [cnet[m & (dl == d)].sum() for d in range(6)]
        P(f"- rep {nm}: {int(m.sum()):,} lots, {100 * cnet[m].sum() / cost[m].sum():+.2f}%/SOL, net {cnet[m].sum():+.2f}, per day " + " ".join(f"{p:+.1f}" for p in pd))

    # ---------------- B. uni dumps
    Z = np.load(f"{L.D}/uni.npz"); X = Z["X"]; M = Z["M"]; FILL = Z["FILL"]; RR = Z["R"]; ES = Z["ES"]
    P5 = np.load(f"{OUT}/p5.npz"); ev = P5["ev"]; fr = P5["fr"]; valid = P5["valid"]; ideal5 = P5["ideal"]; hqn = P5["hq_n"]; hqv = P5["hq_net"]
    day = ((M["bt"].astype(np.int64) - L.DAY0) // 86400).astype(int)
    nb_u = before(burst, M["mint"], M["slot"]); nr_u = before(rep, M["mint"], M["slot"])
    cal = 0.61 * ev - 0.00117; cnow = fr * 0.00352 + (1 - fr) * 0.00053
    P("\n## B. dv8 dumps (all, usable, non-mayhem) by prior burst slots: per attempt mSOL")
    P("| prior bursts | dumps | ideal 5-slot | ours (rank) | fill | calibrated - NOW costs | haqq lots | haqq mSOL/lot |"); P("|---|---|---|---|---|---|---|---|")
    for nm, f in (("0", nb_u == 0), ("1", nb_u == 1), ("2-3", (nb_u >= 2) & (nb_u <= 3)), ("4-9", (nb_u >= 4) & (nb_u <= 9)), ("10+", nb_u >= 10)):
        m = valid & f
        P(f"| {nm} | {int(m.sum()):,} | {1000 * ideal5[m].mean():+.2f} | {1000 * ev[m].mean():+.2f} | {100 * fr[m].mean():.0f}% | {1000 * (cal[m] - cnow[m]).mean():+.2f} | {int(hqn[m].sum()):,} | {1000 * hqv[m].sum() / max(hqn[m].sum(), 1):+.2f} |")

    # ---------------- C. rule for us
    px = tape.vs / np.maximum(tape.vt, 1)
    drop = X[:, 0]
    cand = np.flatnonzero(valid & (nb_u >= 4) & (drop >= 0.10))
    P(f"\n## C. Rule on battleground tokens (prior bursts >= 4, single-sell drop >= 10% -- pre-send fills need ~12%; {len(cand):,} dumps) -- per-entry sims ({time.time() - t0:.0f}s)")
    rng = np.random.default_rng(8)

    def wave_q(r, end, es):
        hi = min(r + int(np.searchsorted(SL[r:end], es + 31, side="right")), end)
        bs = set(SL[r:hi][BU[r:hi] & (SO[r:hi] >= 0.1)].tolist())
        g = next((s for s in range(es + 1, es + 31) if s not in bs), es + 30)
        return tape.qrow(r, end, es, min(g + 1 - es, 30))

    # per candidate: pre-send style (4 draws) and reactive (4 rank draws); exits T2, T5, WAVE; fol 1.0 and 0.9
    EX = ("T2", "T5", "WAVE")
    PS = np.full((len(M), 3, 2), np.nan); PSF = np.zeros(len(M)); RV = np.full((len(M), 3, 2), np.nan); RVF = np.zeros(len(M))
    for n_, i in enumerate(cand):
        jd = int(M["row"][i]); end = int(M["end"][i]); s0 = int(M["slot"][i]); pre = px[jd - 1]
        nwin = int(np.searchsorted(SL[jd + 1:end], s0 + 1, side="right"))
        b = int(np.searchsorted(EDG, nwin, side="right") - 1)
        acc = np.zeros((3, 2)); nf = 0
        for d_ in range(4):
            q_ = rng.exponential(QM[b]) if QM[b] > 0 else 0.0
            r = min(jd + 1 + int(round(min(q_, 1.0) * nwin)), end)
            if not (px[r - 1] <= 0.88 * pre): continue
            es = int(SL[r - 1]) if r - 1 > jd else s0; nf += 1
            for e, qq in enumerate((tape.qrow(r, end, es, 2), tape.qrow(r, end, es, 5), wave_q(r, end, es))):
                acc[e, 0] += tape.joint([(r, qq)])[0]; acc[e, 1] += tape.joint([(r, qq)], fol=0.9)[0]
        PSF[i] = nf / 4; PS[i] = acc / 4
        acc = np.zeros((3, 2)); nf = 0
        for c in (2, 3, 4, 5):
            if not FILL[i, c]: continue
            r = int(RR[i, c]); es = int(ES[i, c]); nf += 1
            for e, qq in enumerate((tape.qrow(r, end, es, 2), tape.qrow(r, end, es, 5), wave_q(r, end, es))):
                acc[e, 0] += tape.joint([(r, qq)])[0]; acc[e, 1] += tape.joint([(r, qq)], fol=0.9)[0]
        RVF[i] = nf / 4; RV[i] = acc / 4
        if n_ % 5000 == 0: print(f"  {n_:,}/{len(cand):,} ({time.time() - t0:.0f}s)", flush=True)
    np.savez(f"{OUT}/p14.npz", PS=PS, PSF=PSF, RV=RV, RVF=RVF, nb=nb_u, nr=nr_u)
    drop = X[:, 0]

    def money(idx, style, e, cost, calib, fol=0):
        if style == "PS":
            g = PS[idx, e, fol].sum(); nf = PSF[idx].sum(); nfail = 0.0
        else:
            g = RV[idx, e, fol].sum(); nf = RVF[idx].sum(); nfail = (1 - RVF[idx]).sum()
        if calib: g = 0.61 * g - 0.00117 * (nf + (nfail if style == "RV" else 0))
        c = nf * (0.00352 if cost == "NOW" else 0.00066) + nfail * (0.00053 if cost == "NOW" else 0.00004)
        return g - c, nf
    P("\n### Pooled per fill (mSOL, model before costs), all days")
    P("| style | prior bursts | dumps | fill | T2 | T5 | WAVE | WAVE -10% followers |"); P("|---|---|---|---|---|---|---|---|")
    for style, V, F_ in (("pre-send", PS, PSF), ("reactive", RV, RVF)):
        for nm, f in (("4-9", (nb_u >= 4) & (nb_u <= 9)), ("10+", nb_u >= 10), ("4+ & rep>=3", (nb_u >= 4) & (nr_u >= 3)), ("4+ & rep 0", (nb_u >= 4) & (nr_u == 0))):
            idx = cand[f[cand]]; nf = F_[idx].sum()
            P(f"| {style} | {nm} | {len(idx):,} | {100 * F_[idx].mean():.0f}% | " + " | ".join(f"{1000 * V[idx, e, 0].sum() / max(nf, 1e-9):+.2f}" for e in range(3)) +
              f" | {1000 * V[idx, 2, 1].sum() / max(nf, 1e-9):+.2f} |")
    grid = [(Bt, e, dmin) for Bt in (4, 6, 10, 20) for e in range(3) for dmin in (0.10, 0.12, 0.2)]
    P("\n### Walk-forward (B, exit, min drop) chosen on D-1 by calibrated NOW; SOL per day window")
    P("| style | test day | chosen | dumps | fills | model NOW | calibrated NOW | calibrated CHEAP | cal NOW -10% followers |"); P("|---|---|---|---|---|---|---|---|---|")
    for style in ("PS", "RV"):
        tot = np.zeros(4)
        for D in (2, 3, 4, 5, 6):
            def pick(Dd, p):
                Bt, e, dmin = p; m = (day[cand] == Dd) & (nb_u[cand] >= Bt) & (drop[cand] >= dmin); return cand[m]
            best = max(grid, key=lambda p: money(pick(D - 1, p), style, p[1], "NOW", True)[0])
            idx = pick(D, best)
            a, nf = money(idx, style, best[1], "NOW", False); b_, _ = money(idx, style, best[1], "NOW", True); c_, _ = money(idx, style, best[1], "CHEAP", True)
            f_, _ = money(idx, style, best[1], "NOW", True, fol=1)
            P(f"| {style} | {day_name(D)} | B>={best[0]}, {EX[best[1]]}, drop>={best[2]} | {len(idx):,} | {nf:.0f} | {a:+.2f} | {b_:+.2f} | {c_:+.2f} | {f_:+.2f} |")
            if D <= 5: tot += (a, b_, c_, f_)
        P(f"| {style} | sum D2-D5 | | | | {tot[0]:+.2f} | {tot[1]:+.2f} | {tot[2]:+.2f} | {tot[3]:+.2f} |")
    P(f"\n(done {time.time() - t0:.0f}s)")
    P.save()


if __name__ == "__main__":
    main()
