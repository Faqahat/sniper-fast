#!/usr/bin/env python3
# r11: WATERFALL from "the paper as it was made before" to our live-config forecast, same hours (10-24 16:59 -> 10-25 07:50 PKT).
#  S0  paper as before: dd20/dd_lib.sim style = IMIT1 top4 (live scores) in the study envelope, 0.55 SOL, exit c6 SL10,
#      BOTH servers trading the WHOLE window (FRA + AMS near lists, one position each), our own trades left in the tape
#  S1  only the hours each server was really running
#  S2  the engine's own picks (pass flag of that server's dump records) instead of the offline envelope + score
#  S3  the run's real size (0.35 / 0.55 / dev 0.75 ...)
#  S4  the run's exit as the paper models it (c19 SL20 / c6 SL10 / c4)
#  S5  our own trades removed from the tape
#  -> rows at 35 / 50 / 75 ms (and 0 / 20). The same engine code (r08.engine = dd_lib.sim rules) everywhere.
#  Check: S0 with rsim == dd_lib.sim on the dd1 arrays.
import sys, os, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import rlib as R, rsim as S
from r08_forecast import engine, paper_exit, load_dumps, FIX, FAIL

LATS = (0, 20, 35, 50, 75)
T_SPLIT = R.pk("10-24 19:26")
W0, W1 = R.pk("10-24 16:59"), R.pk("10-25 07:50")
THR4 = 0.21088520504965255

if __name__ == "__main__":
    F = json.load(open(f"{R.WORK}/fires.json")); runs = {(r["srv"], r["run"]): r for r in F["runs"]}
    TPS = {tag: S.Tapes(tag) for tag in ("NEW", "OLD")}
    meta = json.load(open(f"{R.WORK}/NEW/dd1_meta.json")); FN = meta["feats"] + meta["xf"]; FNI = {k: i for i, k in enumerate(FN)}
    # ---- candidate rows from both dd1 files (de-duplicated: NEW for tokens it has after the split, else OLD)
    cand = []
    newm = set(TPS["NEW"].mint2t)
    for tag in ("OLD", "NEW"):
        z = np.load(f"{R.WORK}/{tag}/dd1_{tag}.npz"); d = {k: z[k] for k in ("k", "tok", "s", "arr", "bt", "F", "X", "f1")}
        TP = TPS[tag]
        bt = d["bt"].astype(np.int64); ok = bt > 0
        a = np.polyfit(d["s"][ok].astype(float), bt[ok].astype(float), 1); t_ = np.where(ok, bt, np.round(np.polyval(a, d["s"].astype(float))))
        X = np.concatenate([d["F"], d["X"]], 1); f = lambda k: X[:, FNI[k]]
        env = (f("age_s") <= 343.67) & (f("drop_pct") >= 4.65) & (f("since_buy_s") <= 3.869) & (f("sol") >= 1.08)
        for r in np.flatnonzero(np.isfinite(d["f1"])).tolist():
            tt = float(t_[r])
            if not (W0 <= tt < W1): continue
            m = TP.meta[int(d["tok"][r])]["m"]
            if tag == "OLD" and tt >= T_SPLIT and m in newm: continue
            if tag == "NEW" and tt < T_SPLIT: continue
            tp = TP.token(int(d["tok"][r])); j0 = int(d["k"][r]) - tp["o"]
            cand.append(dict(tag=tag, t=tt, mint=m, tok=int(d["tok"][r]), j0=j0, slot=int(d["s"][r]), idx=int(tp["i"][j0]), arr=float(d["arr"][r]),
                             f1=float(d["f1"][r]), env=bool(env[r]), devtok=bool(f("dev_tok")[r] > 0), sell=float(f("sol")[r])))
    print(f"candidate rows with a live IMIT1 score in the window: {len(cand)}")
    # near flags + which run (per server) was live at the dump + that run's engine pass flag
    NLF = R.near_list("FRA"); NLA = R.near_list("AMS"); NLB = R.near_list("AMS_NOBAM")
    D = load_dumps(); passed = {}
    for (srv, rn), lst in D.items():
        for o in lst: passed[(srv, o["mint"], o["slot"], o["idx"])] = rn
    def live_run(srv, t):
        for (s_, rn), ru in runs.items():
            if s_ == srv and ru["start"] <= t <= (ru["end"] or W1): return rn
        return None
    for c in cand:
        ld = R.leader(c["slot"]); c["near"] = {"FRA": ld in NLF, "AMS": ld in NLA}
        for srv in ("FRA", "AMS"):
            rn = live_run(srv, c["t"]); c[f"run_{srv}"] = rn
            c[f"pass_{srv}"] = passed.get((srv, c["mint"], c["slot"], c["idx"])) == rn and rn is not None
            if srv == "AMS" and rn is not None and rn >= 14: c["near"]["AMS"] = ld in NLB
    cand.sort(key=lambda x: x["arr"])
    memo = {}
    def oc(c, L, size, cap, sl, drop):
        k = (id(c), L, size, cap, sl, drop)
        if k in memo: return memo[k]
        tp = TPS[c["tag"]].token(c["tok"])
        res = S.run_path(tp, c["j0"], size, L=L, drop_ours=drop)
        if res["st"] != 0: out = dict(st=res["st"])
        else:
            v, so, why = S.exits(res, cap, sl=sl)
            out = dict(st=0, gross=v - size, sell_arr=(res["s_in"] + so) * S.SMS + 75.0)
        memo[k] = out; return out
    def stage(name, sel, size_fn, exit_fn, drop, hours_fn):
        line = []
        for L in LATS:
            tot = 0.0; fl = 0; at = 0
            for srv in ("FRA", "AMS"):
                rows = [c for c in cand if c["near"][srv] and sel(c, srv) and hours_fn(c, srv)]
                e = engine(rows, lambda c, srv=srv: oc(c, L, size_fn(c, srv), *exit_fn(c, srv), drop))
                tot += e["pnl"]; fl += e["fill"]; at += e["att"]
            line.append((L, tot, fl, at))
        print(f"{name:62s} " + " | ".join(f"{L} ms {p:+6.2f} ({f}/{a})" for L, p, f, a in line), flush=True)
        return line
    allh = lambda c, srv: True
    liveh = lambda c, srv: c[f"run_{srv}"] is not None
    sel0 = lambda c, srv: c["f1"] >= THR4 and c["env"]
    selP = lambda c, srv: c[f"pass_{srv}"]
    def size_live(c, srv):
        cfg = runs[(srv, c[f"run_{srv}"])]["cfg"]
        return (cfg["dev_spend"] if c["devtok"] else cfg["spend"]) / 1e9
    def exit_live(c, srv): return paper_exit(runs[(srv, c[f"run_{srv}"])]["cfg"])
    out = {}
    out["S0"] = stage("S0 paper as before (both servers whole window, 0.55, c6 SL10)", sel0, lambda c, s: 0.55, lambda c, s: (6, 0.10), False, allh)
    out["S1"] = stage("S1 + only the hours each server ran", sel0, lambda c, s: 0.55, lambda c, s: (6, 0.10), False, liveh)
    out["S2"] = stage("S2 + the engine's own picks", selP, lambda c, s: 0.55, lambda c, s: (6, 0.10), False, liveh)
    out["S3"] = stage("S3 + the runs' real sizes", selP, size_live, lambda c, s: (6, 0.10), False, liveh)
    out["S4"] = stage("S4 + the runs' exits (paper mapping)", selP, size_live, exit_live, False, liveh)
    out["S5"] = stage("S5 + our own trades removed from the tape", selP, size_live, exit_live, True, liveh)
    json.dump(out, open(f"{R.WORK}/bridge.json", "w"))
    # ---- check S0 against dd_lib.sim on the dd1 arrays (NEW part only, near flags recomputed)
    import dd_lib as DL
    z = np.load(f"{R.WORK}/NEW/dd1_NEW.npz"); d = {k: z[k] for k in z.files}
    bt = d["bt"].astype(np.int64); ok = bt > 0; a = np.polyfit(d["s"][ok].astype(float), bt[ok].astype(float), 1)
    d["t"] = np.where(ok, bt, np.round(np.polyval(a, d["s"].astype(float))))
    m = (d["t"] >= T_SPLIT) & (d["t"] < W1); d = {k: v[m] for k, v in d.items()}
    ld = [R.leader(int(s)) for s in d["s"]]
    d["near_f"] = np.array([x in NLF for x in ld]); d["near_a"] = np.array([x in NLA for x in ld]); d["order"] = np.argsort(d["arr"], kind="stable")
    X = np.concatenate([d["F"], d["X"]], 1)
    env = (X[:, FNI["age_s"]] <= 343.67) & (X[:, FNI["drop_pct"]] >= 4.65) & (X[:, FNI["since_buy_s"]] <= 3.869) & (X[:, FNI["sol"]] >= 1.08)
    sel = np.isfinite(d["f1"]) & (d["f1"] >= THR4) & env
    for li, L in enumerate((35, 50, 75)):
        o = DL.sim(d, sel, li, DL.EXI["c6_tpnone_sl10"])
        print(f"  check dd_lib.sim on dd1_NEW (19:26-07:50, both servers): {L} ms {o['pnl']:+.2f} ({o['fill']}/{o['att']})")
    # same with rsim on NEW-only rows
    for L in (35, 50, 75):
        tot = 0; fl = 0; at = 0
        for srv in ("FRA", "AMS"):
            rows = [c for c in cand if c["tag"] == "NEW" and c["near"][srv] and sel0(c, srv)]
            e = engine(rows, lambda c: oc(c, L, 0.55, 6, 0.10, False)); tot += e["pnl"]; fl += e["fill"]; at += e["att"]
        print(f"  same window with rsim/r08.engine: {L} ms {tot:+.2f} ({fl}/{at})")
