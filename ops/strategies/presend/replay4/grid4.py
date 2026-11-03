#!/usr/bin/env python3
"""CUSTOM37 step 4: every knob ALONE over every window of every run (paired with the current r37 config = BASE), with the
one-position knock-on, REPS possible worlds each (phantom tries, sell-latency draws for new fills, follower cut seeds), at 0% and
-20% followers. TRAIN windows are restricted to what the r37 config would arm (token age >= 2 slots, QUIET all-4 skip recomputed
with fol 4.0 / no follower-bot list).
Out: /home/moiz/sniper-data/custom37/grid.pkl {"cfgs": {name: cfg}, "runs": {run: {"wins": [meta], "res": {name: {cut: array}}}}}
array columns (means over reps): filled, pos_pnl (position P&L, cash, without failed-try fees), fees (failed tries, <= 0),
pos_pos (positive part), pos_neg (negative part), live_try (fill = the live fill try), phantom (fill by a phantom try),
fails (count), nph (phantom tries made)"""
import sys, pickle, time, numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/custom37")
import c37lib as L

RUNS_TRAIN = []
RUNS_TEST = ["r37", "r38", "r39", "r40"]
REPS = 8
COLS = ["filled", "pos_pnl", "fees", "pos_pos", "pos_neg", "live_try", "phantom", "fails", "nph"]


def grid():
    G = {"base": {}}
    for d in (0.08, 0.10, 0.15, 0.18, 0.20, 0.25): G[f"drop{d:.2f}"] = {"drop": d}
    for a in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        for lo in (0.08, 0.10, 0.12):
            for hi in (0.18, 0.25):
                G[f"quote_a{a}_f{lo:.2f}_c{hi:.2f}"] = {"quote": (a, lo, hi)}
    for s in (0.35, 0.5, 0.85, 1.0): G[f"size{s}"] = {"size": s}
    G["k4"] = {"k": 4}; G["k12"] = {"k": 12}
    for w in (4, 6, 15): G[f"win{w}"] = {"win": w}
    G["dl2"] = {"dl": 2}
    G["exit100"] = {"exit_ms": 100}; G["exit300"] = {"exit_ms": 300}; G["exit300s3"] = {"exit_ms": 300, "exit_slots": 3}
    G["exit500s3"] = {"exit_ms": 500, "exit_slots": 3}; G["exit500"] = {"exit_ms": 500}
    G["tp_off"] = {"tp": None}; G["tp10"] = {"tp": 0.10}; G["tp30"] = {"tp": 0.30}
    G["sl30"] = {"sl": 0.30}; G["sl50"] = {"sl": 0.50}; G["sl_off"] = {"sl": None}
    for f in (600, 1000, 2000): G[f"flat{f}"] = {"flat": f}
    for n in (3, 4, 6): G[f"q{n}:2"] = {"qstop": (n, 2)}
    G["q_off"] = {"qstop": None}
    # second pass (after the first tables): a finer custom-quote grid, a tighter SL (known failure check), combos
    for a in (0.7, 0.8, 0.9, 1.0, 1.2):
        for hi in (0.15, 0.16, 0.20, 0.22):
            G[f"quote_a{a}_f0.12_c{hi:.2f}"] = {"quote": (a, 0.12, hi)}
    G["sl10"] = {"sl": 0.10}; G["sl15"] = {"sl": 0.15}
    G["k12_win15"] = {"k": 12, "win": 15}
    return {k: dict(L.BASE, **v) for k, v in G.items()}


def armable(P):
    """would the r37 config arm this trigger? (age >= 2 slots; QUIET all-4 with fol 4.0 and no follower-bot list)"""
    tg = P.W["trig"]
    if tg.get("age_slots", 99) < 2: return False
    q = P.W.get("quiet") or {}
    if "since_last" in q:
        if q["since_last"] >= 1 and q["coh_hold"] == 0 and (q["wh_dumps"] == 0 or q["wh_fol"] < 4.0): return False
    return True


_ctx = {}


def init(runs):
    for run in runs:
        X, wins, R = L.load(run)
        if run != "r37": wins = [P for P in wins if armable(P)]
        _ctx[run] = (X, wins, R)


def one(args):
    run, name, cfg, cut = args
    X, wins, R = _ctx[run]
    c = dict(cfg, cut=cut)
    A = np.zeros((len(wins), len(COLS)))
    lp = L.live_positions(wins)
    for rep in range(REPS):
        out = L.run_sim(wins, R, c, rep=rep, livepos=lp)
        for n, P in enumerate(wins):
            r = out[id(P)]
            fee = -r["fails"] * L.FAIL
            pp = (r["pnl"] - fee) if r["filled"] else 0.0
            A[n] += [r["filled"], pp, fee, max(pp, 0), min(pp, 0), bool(r.get("live_try")), r.get("src", "") in ("ph", "phk"), r["fails"], r["nph"]]
    return run, name, cut, A / REPS


def meta(P):
    tg = P.W["trig"]; q = P.W.get("quiet") or {}; v2 = P.W.get("v2") or {}
    return {"run": P.run, "ses": P.W["ses"], "w": P.W["w"], "mint": P.mint, "t": P.t_trig, "age": tg.get("age_slots"), "pct": tg["pct"], "wsol": tg["sol"] / 1e9,
            "vsol": tg["vsol"] / 1e9, "fulldrop": L.full_drop(P), "wh_dumps": q.get("wh_dumps"), "wh_fol": q.get("wh_fol"), "since_last": q.get("since_last"),
            "coh_hold": q.get("coh_hold"), "fb_n": q.get("fb_n"), "n_tr_60s": v2.get("n_tr_60s"), "at_high": v2.get("at_120s_high"), "maxdd": v2.get("maxdd_120s"),
            "live_fill": P.fill is not None, "live_pnl": P.live_pnl, "dis": (P.dis or {}).get("why")}


if __name__ == "__main__":
    args = sys.argv[1:]
    merge = "--merge" in args
    if merge: args.remove("--merge")
    runs = args or (RUNS_TEST + RUNS_TRAIN)
    G = grid()
    old = pickle.load(open(f"{L.D}/grid4.pkl", "rb")) if merge else None
    todo = {k: v for k, v in G.items() if not (old and k in old["cfgs"])} if merge else G
    if merge and "base" not in todo: todo["base"] = G["base"]
    init(runs)
    jobs = [(run, name, cfg, cut) for run in runs for name, cfg in todo.items() for cut in (0.0, 0.2)]
    t0 = time.time()
    res = {run: {"wins": [meta(P) for P in _ctx[run][1]], "res": {}} for run in runs}
    with Pool(6, initializer=init, initargs=(runs,)) as pool:
        for k, (run, name, cut, A) in enumerate(pool.imap_unordered(one, jobs, chunksize=2)):
            res[run]["res"].setdefault(name, {})[cut] = A
            if k % 100 == 0: print(k, len(jobs), f"{time.time() - t0:.0f}s", flush=True)
    if merge:
        for run in runs:
            for name, v in res[run]["res"].items():
                if name == "base":
                    assert np.allclose(v[0.0], old["runs"][run]["res"]["base"][0.0]), "base changed: rerun the whole grid"
                    continue
                old["runs"][run]["res"][name] = v
        for k in todo: old["cfgs"][k] = G[k]
        res = old["runs"]
        pickle.dump(old, open(f"{L.D}/grid4.pkl", "wb"))
    else:
        pickle.dump({"cfgs": G, "cols": COLS, "runs": res, "reps": REPS}, open(f"{L.D}/grid4.pkl", "wb"))
    for run in runs:
        b = res[run]["res"]["base"][0.0]
        print(run, "windows", len(b), "base fills", round(b[:, 0].sum(), 1), "net", round((b[:, 1].sum() + b[:, 2].sum()) / 1e9, 3))
