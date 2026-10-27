#!/usr/bin/env python3
# MODEL CHECK step 7: re-state what our picks earn under the corrected model. Picks and scoring as
# ops/strategies/dipdetect/dd24_guard_eval.py: IMIT1 top4 and M2 (>= its live threshold) inside the study envelope, IMIT1 windows
# of R1..R4, 0.35 SOL, guard +5%, exits c4 (c4_tpnone_slnone) and c6_tpnone_sl10, dd_lib.sim engine limits (one position per
# server, FRA + AMS near-leader slots, FIX 0.0051 per fill, FAIL 0.0005 per blocked buy), landing 35 / 50 / 75 ms.
# Variants (mc_corr.replay_corr): see VARS. "model" must reproduce dd24's guard +5% row exactly.
# usage: nice python3 -I m7_restate.py build R2   (per day -> m7_<day>.pkl)   |   nice python3 -I m7_restate.py sum
import sys, os, json, pickle, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import mc_lib as M, mc_corr as MC
OUT = M.OUT; LATS = (35, 50, 75); SIZE = 0.35
VARS = {
    "model":            dict(follow="model", others="model", phantom=False, sell_lat=75.0),
    "tol":              dict(follow="tol", others="model", phantom=False, sell_lat=75.0),
    "tol+others":       dict(follow="tol", others="keep", phantom=False, sell_lat=75.0),
    "tol+others+ph":    dict(follow="tol", others="keep", phantom=True, sell_lat=75.0),
    "comp+others+ph":   dict(follow="comp", others="keep", phantom=True, sell_lat=75.0),
    "comp+o+ph+s93":    dict(follow="comp", others="keep", phantom=True, sell_lat=93.0),
    "tol+o+ph+s93":     dict(follow="tol", others="keep", phantom=True, sell_lat=93.0),
    "drop_tg_win":      dict(follow="drop", others="model", phantom=True, sell_lat=75.0),
    "CORR+crowd0.4":    dict(follow="comp", others="keep", phantom=True, sell_lat=93.0, crowd=0.4),
    "tol(r12)+o+ph+s93": dict(follow="tol", others="keep", phantom=True, sell_lat=93.0, curves="r12"),
}

def build(day):
    import dd24_guard_eval as G, dd_lib as L, dd20_shadow_eval as D20
    t0 = time.time()
    d = G.load_ng(day)
    B0 = json.load(open(G.BUNDLE)); cols = [L.FNI[f] for f in B0["fn"]]
    P, B = D20.bundle_scores(G.BUNDLE, d["Xall"][:, cols]); MIN = float(B["thr_default"])
    top4 = d["env"] & (d["f1"] >= L.THR["top4"]); m2 = d["env"] & (P >= MIN)
    sel = (top4 | m2) & (d["near_f"] | d["near_a"])
    rows = np.flatnonzero(sel)
    dy = M.load_day(day)
    CV = {"all": MC.Curves(f"{OUT}/curves_all.json"), "r12": MC.Curves(f"{OUT}/curves_r12.json")}
    res = {v: dict(st=np.zeros((len(rows), 3), np.int8), p4=np.full((len(rows), 3), np.nan), p6=np.full((len(rows), 3), np.nan),
                   o4=np.zeros((len(rows), 3), np.int8), o6=np.zeros((len(rows), 3), np.int8), sin=np.zeros((len(rows), 3), np.int64),
                   nd=np.zeros((len(rows), 3), np.int16)) for v in VARS}
    chk = 0
    for n_, r in enumerate(rows.tolist()):
        k = int(d["k"][r]); t = int(dy["tok"][k]); tp = M.Tape(dy, t); j0 = k - tp.o
        for li, Lm in enumerate(LATS):
            for v, opt in VARS.items():
                o = dict(opt); cv = CV[o.pop("curves", "all")]
                x = MC.replay_corr(tp, j0, SIZE, Lm, guard=1.05, CV=cv, rowkey=k, **o)
                R = res[v]; R["st"][n_, li] = x["status"]
                if x["status"] == 0:
                    R["p4"][n_, li] = x["pnl"][M.E4]; R["p6"][n_, li] = x["pnl"][M.E6]; R["o4"][n_, li] = x["off"][M.E4]; R["o6"][n_, li] = x["off"][M.E6]
                    R["sin"][n_, li] = x["s_in"]; R["nd"][n_, li] = x["ndrop"]
            # self-check: variant "model" == stored dd1 (no-guard file, guard re-applied)
            st0 = 2 if d["st_ng"][r, li] == 2 else (0 if d["ratio"][r, li] <= 1.05 else 1)
            if res["model"]["st"][n_, li] != st0: chk += 1
            elif st0 == 0 and (abs(res["model"]["p4"][n_, li] - d["pnl"][r, li, M.E4]) > 1e-6 or abs(res["model"]["p6"][n_, li] - d["pnl"][r, li, M.E6]) > 1e-6): chk += 1
        if (n_ + 1) % 500 == 0: print(f"  {day}: {n_ + 1}/{len(rows)} rows ({time.time() - t0:.0f} s)", flush=True)
    meta = dict(rows=rows, top4=top4[rows], m2=m2[rows], arr=d["arr"][rows], tok=d["tok"][rows], s=d["s"][rows], near_f=d["near_f"][rows],
                near_a=d["near_a"][rows], k=d["k"][rows], hours=float((d["t"].max() - d["t"].min()) / 3600.0), t=d["t"][rows])
    pickle.dump(dict(meta=meta, res=res), open(f"{OUT}/m7_{day}.pkl", "wb"))
    print(f"{day}: {len(rows)} pick rows, model self-check mismatches {chk} ({time.time() - t0:.0f} s)", flush=True)

def summarize():
    import dd_lib as L
    out = {}; hrs = 0.0
    for day in ("R1", "R2", "R3", "R4"):
        Z = pickle.load(open(f"{OUT}/m7_{day}.pkl", "rb")); mt = Z["meta"]; hrs += mt["hours"]
        n = len(mt["rows"])
        for v, R in Z["res"].items():
            pnl = np.full((n, 3, len(M.EXITS)), np.nan, np.float32); off = np.zeros((n, 3, len(M.EXITS)), np.int64)
            pnl[:, :, M.E4] = R["p4"]; pnl[:, :, M.E6] = R["p6"]; off[:, :, M.E4] = R["o4"]; off[:, :, M.E6] = R["o6"]
            dd = dict(st=R["st"], pnl=pnl, off=off, sin=R["sin"], arr=mt["arr"], tok=mt["tok"], s=mt["s"], near_f=mt["near_f"], near_a=mt["near_a"],
                      order=np.argsort(mt["arr"], kind="stable"))
            for pn, sel in (("IMIT1 top4", mt["top4"]), ("M2", mt["m2"])):
                for en, ex in (("c4", M.E4), ("c6_sl10", M.E6)):
                    for li in range(3):
                        o = L.sim(dd, sel, li, ex)
                        a = out.setdefault((v, pn, en, li), [0.0, 0, 0, 0, 0.0])
                        a[0] += o["pnl"]; a[1] += o["fill"]; a[2] += o["att"]; a[3] += o["win"]
                        a[4] += sum(R["nd"][rr[0], li] for rr in [(x,) for x in []])
    print(f"RE-STATED PICKS, R1..R4 IMIT1 windows ({hrs:.1f} h), 0.35 SOL, guard +5%, all costs (FIX 0.0051/fill), FRA + AMS near leaders")
    print("SOL total (fills/attempts) at 35 / 50 / 75 ms; per fill in mSOL")
    for pn in ("IMIT1 top4", "M2"):
        for en in ("c4", "c6_sl10"):
            print(f"\n== {pn}, exit {en}")
            for v in VARS:
                cells = []
                for li in range(3):
                    a = out[(v, pn, en, li)]
                    cells.append(f"{a[0]:+7.2f} ({a[1]:4d}/{a[2]:4d}) {1000 * a[0] / max(a[1], 1):+6.1f}")
                print(f"  {v:20s} " + " | ".join(cells))
    json.dump({f"{k[0]}|{k[1]}|{k[2]}|{k[3]}": v for k, v in out.items()}, open(f"{OUT}/m7_summary.json", "w"))

if __name__ == "__main__":
    if sys.argv[1] == "build": build(sys.argv[2])
    else: summarize()
