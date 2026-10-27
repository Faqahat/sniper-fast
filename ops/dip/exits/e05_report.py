#!/usr/bin/env python3
# e05: full comparison of the candidate exits (today c4, runs 10-14, the best baselines chosen on TRAIN, the learned exits, the oracle)
# on TRAIN and TEST: engine SOL/day for both servers at our MEASURED landing and at 35 / 50 / 75 ms, sell-latency rows, paired
# bootstrap CIs vs today's exit (30-min time blocks, and per dump), PKT hour bands, crowded vs quiet dumps, per server, AMS no-BAM.
# usage: nice python3 -I e05_report.py [learned tags, comma separated, e.g. gbU,rule1]  -> /home/moiz/sniper-data/exits/e05_report.txt/.json
import sys, os, json, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E, e03_baselines as B, e08_rules as R8, e10_select as R10

OUT = f"{E.DATA}/e05_report"
PER = {"train": (V.W0, V.SPLIT), "test": (V.SPLIT, V.W1), "all24h": (V.W0, V.W1)}


def policies(d, learned):
    P = {
        "TODAY_c4": lambda: d.tick_policy(np.full(len(d.s_in), 4)),
        "RUN10-14_c5_sl10": lambda: d.tpsl(5, sl=0.10),
        "paper_c6_sl10": lambda: d.tpsl(6, sl=0.10),
        "cap2": lambda: d.tick_policy(np.full(len(d.s_in), 2)),
        "cap8": lambda: d.tick_policy(np.full(len(d.s_in), 8)),
        "TPSL_c4_tp40_sl10": lambda: d.tpsl(4, tp=0.40, sl=0.10),
        "TPSL_c4_tp20_sl20": lambda: d.tpsl(4, tp=0.20, sl=0.20),
        "TRAIL_c6_t20": lambda: d.tpsl(6, trail=0.20, trail_min=0.0),
        "STALL1_k2_c30": lambda: B.stall_policy(d, 2, 1, 0.0, 30),
        "STALL2_k2_c30": lambda: B.stall_policy(d, 2, 2, 0.0, 30),
        "haqq_check": lambda: B.haqq_check(d),
        "HkQ7_dump+6": lambda: B.dump_timer(d, 6),
        "CROWDHOLD_1_4_2_2_0_30": lambda: R8.crowdhold(d, 1, 4, 2, 2, 0.0, 30),
        "HOLD_IF_BUY03_k2_c30": lambda: R10.buying_rule(d, 424, 0.3, 2, None, 30),
        "TREE_direct_d3": lambda: d.tick_policy(np.load(f"{E.DATA}/e09_h1248_direct_d3_ksell.npy")),
    }
    for tg in learned:
        f = next(p for p in (f"{E.DATA}/e04_{tg}_ksell.npy", f"{E.DATA}/e04b_{tg}_ksell.npy", f"{E.DATA}/{tg}_ksell.npy") if os.path.exists(p))
        P[f"LEARN_{tg}"] = (lambda f=f: d.tick_policy(np.load(f)))
    P["ORACLE"] = lambda: B.oracle(d)
    return P


def block_sums(d, rows, period, R, block=1800):
    nb = int(np.ceil((period[1] - period[0]) / block)); v = np.zeros(nb)
    t = d.D["t"]
    for dd, rep, p, f in rows:
        b = min(nb - 1, int((t[dd] - period[0]) // block)); v[b] += p / R
    return v


def boot_ci(x, B=4000, seed=1, stat=np.sum):
    rng = np.random.default_rng(seed); n = len(x)
    bs = np.array([stat(x[rng.integers(0, n, n)]) for _ in range(B)])
    return np.percentile(bs, 5), np.percentile(bs, 95)


def per_dump_expect(d, pnl, sel, period):
    """per pick dump (near leaders): expected P&L over our measured landing deciles (fails count -FAIL)"""
    D = d.D
    m = sel & (D["near_f"] | D["near_a"]) & (D["t"] >= period[0]) & (D["t"] < period[1])
    ids = np.flatnonzero(m); out = np.zeros(len(ids))
    for x, dd in enumerate(ids):
        acc = 0.0; n = 0
        for li in range(10):
            ei = d.eidx[dd, li]
            if ei < 0: continue
            st = d.ent[ei, 3]
            if st == 2: continue
            n += 1
            if st == 1: acc -= E.FAIL
            else: acc += pnl[d.tidx[dd, li]]
        out[x] = acc / n if n else 0.0
    return ids, out


if __name__ == "__main__":
    T0 = time.time()
    learned = [x for x in (sys.argv[1].split(",") if len(sys.argv) > 1 else []) if x]
    d = V.Data(); D = d.D
    P = policies(d, learned)
    lines = []
    def L(s=""): lines.append(s); print(s, flush=True)
    res = {}
    V_ = {nm: fn() for nm, fn in P.items()}
    PN = {nm: d.pnl(v[0], 0) for nm, v in V_.items()}
    # mean sell tick / hold
    L("EXIT COMPARISON — corrected replay, 0.35 SOL, FIX 0.0045 + FAIL 0.000505, both servers' near leaders, one position each")
    L(f"TRAIN = 10-24 09:45 -> 10-25 01:00 PKT (15.25 h), TEST = 10-25 01:00 -> 09:45 (8.75 h). Rules / models chosen on TRAIN only.\n")
    for which in ("M2", "IMIT1"):
        sel = d.picks(which)
        L(f"===== {which} picks =====")
        L("A) SOL/day, both servers. Landing = our MEASURED landing (Monte Carlo, 24 draws) or fixed; sell landing MEASURED")
        L(f"{'exit':26s} | {'TRAIN meas':>10s} | {'TEST meas':>9s} {'35ms':>6s} {'50ms':>6s} {'75ms':>6s} | fills/day TEST | mean hold slots (TEST fills)")
        base_rows = {}
        for nm in P:
            val, tdec, knd = V_[nm]; pnl = PN[nm]
            r = {}
            for pn in ("train", "test"):
                for lm in (("meas", "35", "50", "75") if pn == "test" else ("meas",)):
                    e = d.engine(sel, pnl, tdec, knd, lmode=lm, R=24, period=PER[pn], return_rows=(lm == "meas"))
                    r[f"{pn}_{lm}"] = V.fmt_day(e["pnl"], PER[pn])
                    if lm == "meas": r[f"{pn}_fills"] = e["fills"] * 24 / V.hours(PER[pn]); r[f"{pn}_rows"] = e["rows"]
            # hold: mean (tdec - a_in) over TEST pick fills
            m = sel & (D["near_f"] | D["near_a"]) & (D["t"] >= V.SPLIT) & (D["t"] < V.W1)
            ti = d.tidx[np.flatnonzero(m)][:, :10].ravel(); ti = ti[ti >= 0]
            hold = ((tdec[ti] - d.a_in[ti]) / E.SMS).mean() if len(ti) else 0
            res.setdefault(which, {})[nm] = {k: v for k, v in r.items() if not k.endswith("_rows")}
            base_rows[nm] = r
            L(f"{nm:26s} | {r['train_meas']:+10.2f} | {r['test_meas']:+9.2f} {r['test_35']:+6.2f} {r['test_50']:+6.2f} {r['test_75']:+6.2f} | {r['test_fills']:6.0f} | {hold:5.1f}")
        # ---- B) sell-latency rows at our measured landing (TEST)
        L("\nB) TEST SOL/day at our measured landing, by SELL landing row (MEASURED / 35 / 50 / 75 ms after the decision)")
        for nm in P:
            val, tdec, knd = V_[nm]
            s = []
            for r_ in range(4):
                e = d.engine(sel, d.pnl(val, r_), tdec, knd, lmode="meas", R=24, period=PER["test"])
                s.append(V.fmt_day(e["pnl"], PER["test"]))
            L(f"   {nm:26s} " + " ".join(f"{x:+6.2f}" for x in s))
            res[which][nm]["test_sellrows"] = s
        # ---- C) paired CIs vs TODAY (TEST, measured landing)
        L("\nC) TEST difference vs TODAY c4 (SOL/day), 90% CI: (i) 30-min time blocks of the engine run, (ii) per dump (expected over landing)")
        bt = block_sums(d, base_rows["TODAY_c4"]["test_rows"], PER["test"], 24)
        ids, e4 = per_dump_expect(d, PN["TODAY_c4"], sel, PER["test"])
        for nm in P:
            if nm == "TODAY_c4": continue
            bx = block_sums(d, base_rows[nm]["test_rows"], PER["test"], 24)
            diff = bx - bt; lo, hi = boot_ci(diff)
            sc = 24 / V.hours(PER["test"])
            _, ex = per_dump_expect(d, PN[nm], sel, PER["test"])
            dd = ex - e4; lo2, hi2 = boot_ci(dd, stat=np.mean)
            L(f"   {nm:26s} blocks: {diff.sum() * sc:+6.2f} [{lo * sc:+6.2f}, {hi * sc:+6.2f}] SOL/day | per dump (all {len(dd)} pick dumps, no engine): "
              f"{1000 * dd.mean():+5.2f} mSOL [{1000 * lo2:+5.2f}, {1000 * hi2:+5.2f}], better on {np.mean(dd > 1e-9):.0%} / worse on {np.mean(dd < -1e-9):.0%}")
            res[which][nm]["test_ci_blocks"] = [diff.sum() * sc, lo * sc, hi * sc]; res[which][nm]["test_ci_dump"] = [dd.mean(), lo2, hi2]
        # ---- D) hour bands (PKT), measured landing
        L("\nD) SOL by PKT hour band (measured landing; sums over the band, not per day)")
        bands = [("10-24 09:45", "10-24 14:00"), ("10-24 14:00", "10-24 18:00"), ("10-24 18:00", "10-24 21:00"), ("10-24 21:00", "10-25 01:00"),
                 ("10-25 01:00", "10-25 03:00"), ("10-25 03:00", "10-25 05:00"), ("10-25 05:00", "10-25 07:00"), ("10-25 07:00", "10-25 09:45")]
        L("   " + " ".join(f"{a[6:]}-{b[6:]:>5s}" for a, b in bands))
        for nm in P:
            val, tdec, knd = V_[nm]; s = []
            for a, b in bands:
                per = (E.pk(a), E.pk(b)); e = d.engine(sel, PN[nm], tdec, knd, lmode="meas", R=24, period=per); s.append(e["pnl"])
            L(f"   {nm:26s} " + " ".join(f"{x:+11.2f}" for x in s))
            res[which][nm]["bands"] = s
        # ---- E) crowded vs quiet (real tape: distinct fast bots buying in the dump slot .. +3), per fill, near picks, measured landing
        L("\nE) per fill (mSOL) by crowd = distinct fast dip bots (75-bot list) buying in the dump slot .. +3 (real tape); all near pick fills")
        segs = [("quiet 0-1", lambda x: x <= 1), ("2", lambda x: x == 2), ("crowded 3+", lambda x: x >= 3)]
        for pn in ("train", "test"):
            per = PER[pn]
            m0 = sel & (D["near_f"] | D["near_a"]) & (D["t"] >= per[0]) & (D["t"] < per[1])
            head = f"   {pn:5s} " + " | ".join(f"{sn} (dumps {int((m0 & f(d.tg_n3)).sum())}, fills {int((d.tidx[np.flatnonzero(m0 & f(d.tg_n3))][:, :10] >= 0).sum())})" for sn, f in segs)
            L(head)
            for nm in P:
                s = []
                for sn, f in segs:
                    ti = d.tidx[np.flatnonzero(m0 & f(d.tg_n3))][:, :10].ravel(); ti = ti[ti >= 0]
                    s.append(1000 * PN[nm][ti].mean() if len(ti) else float("nan"))
                L(f"      {nm:26s} " + "  ".join(f"{x:+7.1f}" for x in s))
                res[which][nm][f"crowd_{pn}"] = s
        # ---- F) per server and AMS no-BAM (TEST, measured)
        L("\nF) TEST SOL/day by server (measured landing): FRA | AMS | AMS with the no-BAM list")
        for nm in P:
            val, tdec, knd = V_[nm]
            f_ = d.engine(sel, PN[nm], tdec, knd, lmode="meas", R=24, period=PER["test"], servers=("f",))
            a_ = d.engine(sel, PN[nm], tdec, knd, lmode="meas", R=24, period=PER["test"], servers=("a",))
            b_ = d.engine(sel, PN[nm], tdec, knd, lmode="meas", R=24, period=PER["test"], servers=("a",), nobam=True)
            L(f"   {nm:26s} {V.fmt_day(f_['pnl'], PER['test']):+6.2f} | {V.fmt_day(a_['pnl'], PER['test']):+6.2f} | {V.fmt_day(b_['pnl'], PER['test']):+6.2f}")
        # ---- G) by day (calendar): 10-24 09:45-24:00 and 10-25 00:00-09:45
        L("\nG) by calendar day (measured landing, SOL/day): 10-24 (09:45-24:00, mostly TRAIN) | 10-25 (00:00-09:45, mostly TEST)")
        for nm in P:
            val, tdec, knd = V_[nm]; s = []
            for per in ((V.W0, E.pk("10-25 00:00")), (E.pk("10-25 00:00"), V.W1)):
                e = d.engine(sel, PN[nm], tdec, knd, lmode="meas", R=24, period=per); s.append(V.fmt_day(e["pnl"], per))
            L(f"   {nm:26s} {s[0]:+6.2f} | {s[1]:+6.2f}")
        L("")
    json.dump(res, open(f"{OUT}.json", "w"), default=float)
    open(f"{OUT}.txt", "w").write("\n".join(lines) + "\n")
    print(f"done {time.time() - T0:.0f} s")
