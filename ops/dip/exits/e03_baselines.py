#!/usr/bin/env python3
# e03: baseline exits on the corrected replay paths (e02), M2 and IMIT1 picks, both servers' near leaders.
# Families: fixed caps, today's exit (c4 = sell lands in slot s_in + 4 = hold 5), runs 10-14 (hold 6 + SL -10%: c5 + SL10 as the
# engine really sold; c6 + SL10 = the replay's name c6_tpnone_sl10), TP/SL grid, trailing stops, "hold while outside buying
# continues" stall rules, haqq-like timers from the dump slot, and the look-ahead oracle (upper bound).
# Every rule is chosen on TRAIN (10-24 09:45 -> 10-25 01:00 PKT) and reported on TEST (01:00 -> 09:45) as well.
# -> /home/moiz/sniper-data/exits/e03_baselines.json + .txt
import sys, os, json, time, itertools
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E

OUT = f"{E.DATA}/e03_baselines"


def stall_policy(d, kmin, m, b, cap, net=False):
    """tick rule: from tick kmin on, sell at the first tick where the outside buy SOL of the last m slots is below b (b = 0: no buy at
    all; net: buy - sell SOL <= 0); cap = forced sell tick"""
    F = d.ft; I = d.TFI
    if m == 1: bs = F[:, :, I["bsol1"]]; nb = F[:, :, I["nb1"]]; ss = F[:, :, I["ssol1"]]
    else: bs = F[:, :, I["bsol2"]]; nb = F[:, :, I["nb2"]]; ss = F[:, :, I["ssol2"]]
    if net: cond = (bs - ss) <= 0
    elif b <= 0: cond = nb == 0
    else: cond = bs < b
    ks = np.arange(1, d.K + 1)[None, :]
    cond = cond & (ks >= kmin) & (ks <= cap)
    cond[:, cap - 1] = True
    k = cond.argmax(1) + 1
    return d.tick_policy(k)


def dump_timer(d, N):
    """sell at the dump slot + N (haqq / HkQ7-style timers count from the dump), at least one slot after entry"""
    s_dump = d.D["s"][d.t_did]
    k = np.clip(s_dump + N - d.s_in, 1, d.K)
    return d.tick_policy(k)


def haqq_check(d, checks=(10, 12, 15, 20, 25, 30), quiet=4, up=0.25):
    """haqq-like: at checkpoints after the dump, sell if the tape is quiet (no outside buy for >= quiet slots) or the lot is up >= 25%;
    forced out at the last checkpoint"""
    s_dump = d.D["s"][d.t_did]; F = d.ft; I = d.TFI
    N = len(d.s_in); k_out = np.full(N, -1)
    for c in checks:
        k = np.clip(s_dump + c - d.s_in, 1, d.K)
        row = F[np.arange(N), k - 1]
        sell = (row[:, I["stall_slots"]] >= quiet) | (row[:, I["r"]] >= up) | (c == checks[-1])
        nw = (k_out < 0) & sell
        k_out[nw] = k[nw]
    return d.tick_policy(k_out)


def oracle(d):
    k = d.tv[:, 0, 1:].argmax(1) + 1
    return d.tick_policy(k)


def families(d):
    P = {}
    for c in (1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30):
        P[f"cap{c}"] = ("cap", lambda c=c: d.tick_policy(np.full(len(d.s_in), c)))
    P["TODAY_c4"] = ("today", lambda: d.tick_policy(np.full(len(d.s_in), 4)))
    P["RUN10-14_c5_sl10"] = ("run10-14", lambda: d.tpsl(5, sl=0.10))
    P["paper_c6_sl10"] = ("run10-14", lambda: d.tpsl(6, sl=0.10))
    for c, tp, sl in itertools.product((2, 4, 6, 9, 12, 19, 28), (None, 0.05, 0.10, 0.20, 0.40), (None, 0.05, 0.10, 0.20, 0.30)):
        if tp is None and sl is None: continue
        P[f"tpsl_c{c}_tp{tp}_sl{sl}"] = ("tpsl", lambda c=c, tp=tp, sl=sl: d.tpsl(c, tp=tp, sl=sl))
    for c, tr, tm in itertools.product((6, 9, 12, 19, 28), (0.03, 0.05, 0.08, 0.12, 0.20), (None, 0.0, 0.05)):
        P[f"trail_c{c}_t{tr}_min{tm}"] = ("trail", lambda c=c, tr=tr, tm=tm: d.tpsl(c, trail=tr, trail_min=tm))
    for kmin, m, b, cap in itertools.product((1, 2, 3, 4), (1, 2), (0.0, 0.1, 0.3, 0.5, 1.0), (6, 9, 12, 19, 30)):
        if cap <= kmin: continue
        P[f"stall_k{kmin}_m{m}_b{b}_c{cap}"] = ("stall", lambda kmin=kmin, m=m, b=b, cap=cap: stall_policy(d, kmin, m, b, cap))
    for kmin, m, cap in itertools.product((1, 2, 3, 4), (1, 2), (6, 9, 12, 19, 30)):
        if cap <= kmin: continue
        P[f"stallnet_k{kmin}_m{m}_c{cap}"] = ("stall", lambda kmin=kmin, m=m, cap=cap: stall_policy(d, kmin, m, 0, cap, net=True))
    for N in (6, 8, 10, 12, 15, 20, 25, 30):
        P[f"dumptimer_{N}"] = ("timer", lambda N=N: dump_timer(d, N))
    P["haqq_check"] = ("timer", lambda: haqq_check(d))
    P["ORACLE"] = ("oracle", lambda: oracle(d))
    return P


def per_fill(d, pnl, sel, period):
    D = d.D
    m = sel & (D["near_f"] | D["near_a"]) & (D["t"] >= period[0]) & (D["t"] < period[1])
    ti = d.tidx[np.flatnonzero(m)][:, :10].ravel(); ti = ti[ti >= 0]
    return float(pnl[ti].mean()) if len(ti) else float("nan"), len(ti)


if __name__ == "__main__":
    T0 = time.time()
    d = V.Data(); D = d.D
    PER = {"train": (V.W0, V.SPLIT), "val": (V.VAL0, V.SPLIT), "test": (V.SPLIT, V.W1)}
    fam = families(d)
    res = {}
    for i, (name, (kind, fn)) in enumerate(fam.items()):
        val, tdec, knd = fn()
        r = dict(kind=kind)
        for which in ("M2", "IMIT1"):
            sel = d.picks(which)
            for pn, per in PER.items():
                pnl = d.pnl(val, 0)
                pf, nf = per_fill(d, pnl, sel, per)
                eng = d.engine(sel, pnl, tdec, knd, lmode="meas", R=16, period=per)
                r[f"{which}_{pn}"] = dict(per_fill=pf, n=nf, sol=eng["pnl"], day=V.fmt_day(eng["pnl"], per), fills=eng["fills"], att=eng["att"])
        res[name] = r
        if (i + 1) % 50 == 0: print(f"  {i + 1}/{len(fam)} policies, {time.time() - T0:.0f} s", flush=True)
    json.dump(res, open(f"{OUT}.json", "w"))
    # ---- report: TODAY / RUN10-14 / best of each family chosen on TRAIN (M2 engine SOL/day), with val / test
    lines = []
    def L(s=""): lines.append(s); print(s)
    L(f"BASELINE EXITS (corrected replay, 0.35 SOL, our MEASURED landing, sell landing MEASURED; FIX {E.FIX} / FAIL {E.FAIL}; both servers)")
    L("columns: SOL/day in the engine (train | val | test), per fill mSOL (train | test); M2 then IMIT1")
    def row(nm):
        r = res[nm]; s = f"{nm:34s}"
        for w in ("M2", "IMIT1"):
            s += f" | {w}: {r[w + '_train']['day']:+6.2f} {r[w + '_val']['day']:+6.2f} {r[w + '_test']['day']:+6.2f}  pf {1000 * r[w + '_train']['per_fill']:+5.1f} {1000 * r[w + '_test']['per_fill']:+5.1f}"
        return s
    for nm in ("TODAY_c4", "RUN10-14_c5_sl10", "paper_c6_sl10", "ORACLE"): L(row(nm))
    L("\nfixed caps:")
    for c in (1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30): L(row(f"cap{c}"))
    for fk in ("tpsl", "trail", "stall", "timer"):
        names = [n for n, (k, _) in fam.items() if k == fk]
        for w in ("M2", "IMIT1"):
            best = sorted(names, key=lambda n: -res[n][f"{w}_train"]["day"])[:5]
            L(f"\n{fk}: top 5 on TRAIN by {w} SOL/day")
            for n in best: L(row(n))
    open(f"{OUT}.txt", "w").write("\n".join(lines) + "\n")
    print(f"done {time.time() - T0:.0f} s")
