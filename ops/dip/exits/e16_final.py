#!/usr/bin/env python3
# e16: the final tables of EXIT_MODEL.md, for one fixed list of exits (no selection happens here).
# A) SOL/day both servers (engine): TRAIN measured landing; TEST measured / crowd-conditional measured / 35 / 50 / 75 ms; M2 and IMIT1.
# B) TEST difference vs today's exit with the 90% CI (30-min blocks) and per dump.
# C) our real live fills at their exact landing (train hours / test hours).
# D) per fill by crowd on TEST (quiet 0-1 / 2 / crowded 3+ fast bots in the dump slot .. +3).
# -> /home/moiz/sniper-data/exits/e16_final.txt + .json
import sys, os, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E, e03_baselines as B, e_apply as AP, e05_report as R5, e14_cut as C14

if __name__ == "__main__":
    lines = []; out = {}
    def L(s=""): lines.append(s); print(s, flush=True)
    d = V.Data(); D = d.D; N = len(d.t_did)
    dl = V.Data(paths=f"{E.DATA}/paths/paths_live.npz")
    idx = [x for x in json.load(open(f"{E.DATA}/paths/live_index.json")) if x["st"] == 0]
    te_l = np.array([x["t"] for x in idx]) >= V.SPLIT
    ks = np.load(f"{E.DATA}/e04b_ENS3_ksell.npy"); kl, _ = AP.apply_saved(dl, f"{E.DATA}/e04b_ENS3_model.pkl")
    def both(fn):
        return fn(d), fn(dl)
    P = {
        "TODAY c4 (hold 5)": both(lambda x: x.tick_policy(np.full(len(x.s_in), 4))),
        "Runs 10-14 (hold 6, SL -10%)": both(lambda x: x.tpsl(5, sl=0.10)),
        "paper c6_tpnone_sl10": both(lambda x: x.tpsl(6, sl=0.10)),
        "fixed 2 slots": both(lambda x: x.tick_policy(np.full(len(x.s_in), 2))),
        "fixed 8 slots": both(lambda x: x.tick_policy(np.full(len(x.s_in), 8))),
        "TP +20% / SL -20%, cap 4": both(lambda x: x.tpsl(4, tp=0.20, sl=0.20)),
        "trail 20% from peak, cap 6": both(lambda x: x.tpsl(6, trail=0.20, trail_min=0.0)),
        "stall 1 slot (from slot 2)": both(lambda x: B.stall_policy(x, 2, 1, 0.0, 30)),
        "stall 2 slots (from slot 2)": both(lambda x: B.stall_policy(x, 2, 2, 0.0, 30)),
        "haqq-like checks": both(lambda x: B.haqq_check(x)),
        "HkQ7-like dump+6 timer": both(lambda x: B.dump_timer(x, 6)),
        "LEARNED (GBDT x3)": (d.tick_policy(ks), dl.tick_policy(kl)),
        "  learned: cut-only half": (d.tick_policy(np.minimum(ks, 4)), dl.tick_policy(np.minimum(kl, 4))),
        "  learned: hold-only half": (d.tick_policy(np.maximum(ks, 4)), dl.tick_policy(np.maximum(kl, 4))),
        "SIMPLE CUT (stale 424 ms)": both(lambda x: C14.cut_rule(x, 424, 1, 4)),
        "ORACLE (look-ahead)": both(lambda x: B.oracle(x)),
    }
    PER = {"train": (V.W0, V.SPLIT), "test": (V.SPLIT, V.W1)}
    sc = 24 / V.hours(PER["test"])
    for w in ("M2", "IMIT1"):
        sel = d.picks(w)
        L(f"===== {w} picks: SOL/day, both servers' near leaders =====")
        L(f"{'exit':30s} | TRAIN meas | TEST meas  measc   35ms   50ms   75ms | TEST diff vs c4 [90% CI]   | per dump mSOL [90% CI]")
        rows4 = None; e4 = None
        for nm, ((val, tdec, knd), _) in P.items():
            pnl = d.pnl(val, 0); r = {}
            for pn in ("train", "test"):
                for lm in (("meas", "measc", "35", "50", "75") if pn == "test" else ("meas",)):
                    e = d.engine(sel, pnl, tdec, knd, lmode=lm, R=24, period=PER[pn], return_rows=(pn == "test" and lm == "meas"))
                    r[f"{pn}_{lm}"] = V.fmt_day(e["pnl"], PER[pn])
                    if pn == "test" and lm == "meas": rows = e["rows"]
            ids, ex = R5.per_dump_expect(d, pnl, sel, PER["test"])
            if rows4 is None: rows4 = rows; e4 = ex; cis = ""
            else:
                bt = R5.block_sums(d, rows4, PER["test"], 24); bx = R5.block_sums(d, rows, PER["test"], 24); df = bx - bt
                lo, hi = R5.boot_ci(df); dd = ex - e4; lo2, hi2 = R5.boot_ci(dd, stat=np.mean)
                cis = f"{df.sum() * sc:+5.2f} [{lo * sc:+5.2f}, {hi * sc:+5.2f}] | {1000 * dd.mean():+5.2f} [{1000 * lo2:+5.2f}, {1000 * hi2:+5.2f}]"
                r["test_diff"] = [df.sum() * sc, lo * sc, hi * sc]; r["test_dump"] = [dd.mean(), lo2, hi2]
            out.setdefault(w, {})[nm] = r
            L(f"{nm:30s} | {r['train_meas']:+10.2f} | {r['test_meas']:+9.2f} {r['test_measc']:+6.2f} {r['test_35']:+6.2f} {r['test_50']:+6.2f} {r['test_75']:+6.2f} | {cis}")
        L("")
    # ---- live fills
    L("===== our 128 real live fills at their exact landing (0.35 SOL), SOL total and diff vs c4 [90% CI] =====")
    p4 = dl.pnl(P["TODAY c4 (hold 5)"][1][0], 0); rng = np.random.default_rng(9)
    for nm, (_, (val, tdec, knd)) in P.items():
        p = dl.pnl(val, 0); s = f"{nm:30s}"
        for pn, m in (("train hours (n 66)", ~te_l), ("test hours (n 62)", te_l)):
            df = p[m] - p4[m]; bs = [df[rng.integers(0, m.sum(), m.sum())].sum() for _ in range(3000)]
            s += f" | {pn}: {p[m].sum():+.3f}, diff {df.sum():+.3f} [{np.percentile(bs, 5):+.3f}, {np.percentile(bs, 95):+.3f}]"
            out.setdefault("live", {}).setdefault(nm, {})[pn] = [p[m].sum(), df.sum(), np.percentile(bs, 5), np.percentile(bs, 95)]
        L(s)
    # ---- crowd segments, TEST
    L("\n===== TEST per fill (mSOL) by crowd (distinct fast bots buying in the dump slot .. +3): quiet 0-1 | 2 | crowded 3+ =====")
    for w in ("M2", "IMIT1"):
        sel = d.picks(w)
        m0 = sel & (D["near_f"] | D["near_a"]) & (D["t"] >= V.SPLIT) & (D["t"] < V.W1)
        segs = [("quiet", d.tg_n3 <= 1), ("2", d.tg_n3 == 2), ("crowded", d.tg_n3 >= 3)]
        tis = {}
        for sn, f in segs:
            ti = d.tidx[np.flatnonzero(m0 & f)][:, :10].ravel(); tis[sn] = ti[ti >= 0]
        L(f"  {w}: fills quiet {len(tis['quiet'])}, 2 {len(tis['2'])}, crowded {len(tis['crowded'])}")
        for nm, ((val, tdec, knd), _) in P.items():
            pnl = d.pnl(val, 0)
            L(f"    {nm:30s} " + "  ".join(f"{1000 * pnl[tis[sn]].mean():+7.1f}" for sn, _ in segs))
    json.dump(out, open(f"{E.DATA}/e16_final.json", "w"), default=float)
    open(f"{E.DATA}/e16_final.txt", "w").write("\n".join(lines) + "\n")
