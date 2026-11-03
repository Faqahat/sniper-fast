#!/usr/bin/env python3
"""CUSTOM37 step 8: EXACT replay of the chosen custom policies (per-window configs, mixed configs in one run: the one-position knock-on
between windows of different configs is simulated), paired with the current config on the same 8 worlds, 0% and -20% followers.
Tables: TRAIN (r34 r35 r36 f26 f27 f28) and TEST (r37), r37 halves, bootstrap 90% CI (windows resampled in (run, PKT hour) blocks),
without the top 5 windows, per run, SOL/day at 0.696, fills added / lost, delta loss / winners / failed-try fees, INFERRED share.
Out: stdout + /home/moiz/sniper-data/custom37/final.txt + final.json"""
import sys, pickle, json, datetime, numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/custom37")
import c37lib as L
from c4_grid import grid, armable

TRAIN = ["r34", "r35", "r36", "f26", "f27", "f28"]; TEST = ["r37"]; REPS = 8
CF = grid()
pkt = lambda t_ms: datetime.datetime.fromtimestamp(t_ms / 1e3, datetime.UTC) + datetime.timedelta(hours=5)


def seg_policy(fn):
    def f(P, F):
        name = fn(F)
        return None if name == "SKIP" else CF[name]
    return f


POLICIES = {
    # A: the custom quote picked on TRAIN (best TRAIN gain among the alpha / floor / cap quotes): limit drop = clip(0.7 x full-dump drop, 0.12, 0.16)
    "A_quote_0.7x_0.12-0.16": seg_policy(lambda F: "quote_a0.7_f0.12_c0.16"),
    # B: the best TRAIN policy of the limit / exit family (fulldrop segments)
    "B_trainbest_limit_exit": seg_policy(lambda F: "exit300" if F["fulldrop"] < 0.1781 else ("quote_a0.8_f0.12_c0.25" if F["fulldrop"] < 0.2455 else "dl2")),
    # C: the best TRAIN policy with size: size 1.0, except big-impact whales on tokens with >= 23.4% held by other >= 1% holders -> quote 0.8x
    "C_trainbest_size": seg_policy(lambda F: "quote_a0.8_f0.12_c0.18" if (F.get("other1") is not None and F["fulldrop"] >= 0.204 and F["other1"] >= 23.4097) else "size1.0"),
    # references
    "size0.85_all": seg_policy(lambda F: "size0.85"),
    "size1.0_all": seg_policy(lambda F: "size1.0"),
    "win15 (INFERRED)": seg_policy(lambda F: "win15"),
    "k12 (INFERRED)": seg_policy(lambda F: "k12"),
    # ORACLE: fitted on r37 itself (upper bound only)
    "ORACLE_r37_limit": seg_policy(lambda F: "drop0.20" if F["fulldrop"] < 0.1387 else ("quote_a0.8_f0.12_c0.18" if F["fulldrop"] < 0.2462 else "quote_a0.5_f0.12_c0.18")),
}

_ctx = {}


def init(runs):
    for run in runs:
        X, wins, R = L.load(run)
        if run != "r37": wins = [P for P in wins if armable(P)]
        H = pickle.load(open(f"{L.D}/holders_{run}.pkl", "rb"))
        F = {id(P): L.features(P, H) for P in wins}
        _ctx[run] = (X, wins, R, F)


def one(args):
    run, pname, cut = args
    X, wins, R, F = _ctx[run]
    pol = POLICIES.get(pname)
    lp = L.live_positions(wins)
    out = np.zeros((len(wins), 8))   # filled, pos_pnl, fees, pos_pos, pos_neg, phantom, cfg changed, skip
    for rep in range(REPS):
        if pol is None: cfg = dict(L.BASE, cut=cut)
        else: cfg = (lambda P, _p=pol: (lambda c: None if c is None else dict(c, cut=cut))(_p(P, F[id(P)])))
        res = L.run_sim(wins, R, cfg, rep=rep, livepos=lp)
        for n, P in enumerate(wins):
            r = res[id(P)]
            fee = -r["fails"] * L.FAIL
            pp = (r["pnl"] - fee) if r["filled"] else 0.0
            out[n] += [r["filled"], pp, fee, max(pp, 0), min(pp, 0), r.get("src", "") in ("ph", "phk"), 0, bool(r.get("skip"))]
    return run, pname, cut, out / REPS


def stats(rows, hours, seed=7):
    d = np.array([r["d"] for r in rows]) / 1e9
    blocks = {}
    for i, r in enumerate(rows): blocks.setdefault(r["blk"], []).append(i)
    keys = list(blocks); rng = np.random.default_rng(seed); bs = []
    for _ in range(4000):
        pick = rng.integers(0, len(keys), len(keys)); bs.append(sum(d[blocks[keys[q]]].sum() for q in pick))
    df = np.array([r["df"] for r in rows]); ph = np.array([r["ph"] for r in rows])
    return {"dnet": d.sum(), "day": d.sum() / hours * 24, "ci": np.percentile(bs, [5, 95]).tolist(), "no_top5": d.sum() - np.sort(d)[::-1][:5].sum(),
            "dloss": sum(r["dl"] for r in rows) / 1e9, "dwin": sum(r["dw"] for r in rows) / 1e9, "dfee": sum(r["dfee"] for r in rows) / 1e9,
            "added": float(df[df > 0].sum()), "lost": float(-df[df < 0].sum()), "infer": float(np.abs(d[ph > 0]).sum() / max(np.abs(d).sum(), 1e-12))}


if __name__ == "__main__":
    runs = TEST + TRAIN
    names = ["BASE"] + list(POLICIES)
    init(runs)
    jobs = [(r, p, c) for r in runs for p in names for c in (0.0, 0.2)]
    RES = {}
    with Pool(6, initializer=init, initargs=(runs,)) as pool:
        for run, pname, cut, A in pool.imap_unordered(one, jobs):
            RES[(run, pname, cut)] = A
    H = {}
    for r in runs:
        m = pickle.load(open(f"{L.D}/win_{r}.pkl", "rb"))["meta"]; H[r] = (m["t1"] - m["t0"]) / 3.6e12
    W = {r: _ctx[r][1] for r in runs}
    t37 = [P.t_trig for P in W["r37"]]; mid = (min(t37) + max(t37)) / 2
    out = []; J = {}
    def p(s=""): print(s); out.append(s)
    def rows_of(rs, pname, cut, sel=None):
        R_ = []
        for r in rs:
            b = RES[(r, "BASE", cut)]; k = RES[(r, pname, cut)]
            for n, P in enumerate(W[r]):
                if sel and not sel(P): continue
                R_.append({"d": (k[n, 1] + k[n, 2]) - (b[n, 1] + b[n, 2]), "dl": k[n, 4] - b[n, 4], "dw": k[n, 3] - b[n, 3], "dfee": k[n, 2] - b[n, 2],
                           "df": k[n, 0] - b[n, 0], "ph": k[n, 5], "blk": (r, pkt(P.t_trig).strftime("%m%d%H")), "run": r})
        return R_
    p(f"BASE (current r37 config) replayed: " + ", ".join(f"{r} {(RES[(r, 'BASE', 0.0)][:, 1].sum() + RES[(r, 'BASE', 0.0)][:, 2].sum()) / 1e9:+.3f} SOL / {H[r]:.1f} h" for r in runs))
    p(f"r37 halves split at {pkt(mid):%H:%M} PKT")
    p("")
    for pname in POLICIES:
        tr = stats(rows_of(TRAIN, pname, 0.0), sum(H[r] for r in TRAIN)); tr20 = stats(rows_of(TRAIN, pname, 0.2), sum(H[r] for r in TRAIN))
        te = stats(rows_of(TEST, pname, 0.0), H["r37"]); te20 = stats(rows_of(TEST, pname, 0.2), H["r37"])
        h1 = stats(rows_of(TEST, pname, 0.0, lambda P: P.t_trig < mid), H["r37"] / 2); h2 = stats(rows_of(TEST, pname, 0.0, lambda P: P.t_trig >= mid), H["r37"] / 2)
        per = {r: stats(rows_of([r], pname, 0.0), H[r])["dnet"] for r in runs}
        J[pname] = {"train": tr, "train20": tr20, "test": te, "test20": te20, "h1": h1["dnet"], "h2": h2["dnet"], "per_run": per}
        p(f"### {pname}")
        p("| set | d net SOL | SOL/day | 90% CI | w/o top 5 | -20% followers | d losers | d winners | d failed-try fees | fills +/- | INFERRED share |")
        p("|---|---|---|---|---|---|---|---|---|---|---|")
        for lab, a, a20 in (("TRAIN", tr, tr20), ("TEST r37", te, te20)):
            p(f"| {lab} | {a['dnet']:+.3f} | {a['day']:+.2f} | [{a['ci'][0]:+.2f}, {a['ci'][1]:+.2f}] | {a['no_top5']:+.3f} | {a20['dnet']:+.3f} | {a['dloss']:+.3f} | {a['dwin']:+.3f} | "
              f"{a['dfee']:+.3f} | +{a['added']:.1f} / -{a['lost']:.1f} | {a['infer']:.0%} |")
        p(f"r37 1st half {h1['dnet']:+.3f}, 2nd half {h2['dnet']:+.3f} | per run: " + ", ".join(f"{r} {v:+.3f}" for r, v in per.items()))
        p("")
    open(f"{L.D}/final.txt", "w").write("\n".join(out) + "\n")
    json.dump(J, open(f"{L.D}/final.json", "w"))
