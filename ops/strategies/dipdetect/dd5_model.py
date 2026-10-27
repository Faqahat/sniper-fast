#!/usr/bin/env python3
# Detectors trained on OUR replayed P&L over the WHOLE dump universe (in and out of the envelope). Train = R2 only (fit = first
# 70% of R2 by time, early stop + threshold choice on the last 30% = "R2-val"); test = R3, check = R1, forward = R4.
# Every variant run is appended to dd5_registry.jsonl (variant count for the multiple-testing haircut).
# Engine replay (dd_lib.sim): both servers (FRA + AMS near leaders), one position per server, 0.55 SOL, costs incl.
# usage: python3 dd5_model.py <variant names...>   (no args = all)
import sys, json, time
import numpy as np
from multiprocessing import get_context
import dd_lib as L
import dd_gbdt as GT
OUT = L.OUT
DAYS = ("R2", "R3", "R1", "R4")
DROP_F = {"ev_buy", "theme", "x", "eff", "fun", "rw", "cpy", "red", "bid", "top_n", "top_hold"}   # constant / launch-text labels (not live) / arbitrary ids
G = {}

def ylab(d, lat, e):
    st = d["st"][:, lat]
    return np.where(st == 0, d["pnl"][:, lat, e] - L.FIX, np.where(st == 1, -L.FAIL, np.nan))

VARIANTS = {
    "v3_reg4_top25": (("pnl", 0, "c4_tpnone_slnone"), "l2", "list:/home/moiz/sniper-data/strategies/dipdetect/top25_v3_reg4_nof1.json", {"seeds": 3}),
    "v3_reg13":      (("pnl", 0, "c6_tpnone_sl10"), "l2", "all", {"seeds": 3}),
    "v3_reg13_nof1": (("pnl", 0, "c6_tpnone_sl10"), "l2", "nof1", {"seeds": 3}),
    "v3_reg4_nof1":  (("pnl", 0, "c4_tpnone_slnone"), "l2", "nof1", {"seeds": 3}),
    "v3_reg13_env":  (("pnl", 0, "c6_tpnone_sl10"), "l2", "all", {"rows": "env", "seeds": 3}),
    "v3_reg4":       (("pnl", 0, "c4_tpnone_slnone"), "l2", "all", {"seeds": 3}),
    "v2_reg13":        (("pnl", 0, "c6_tpnone_sl10"), "l2", "all", {}),
    "v2_reg13_nof1":   (("pnl", 0, "c6_tpnone_sl10"), "l2", "nof1", {}),
    "v2_reg13_nohour": (("pnl", 0, "c6_tpnone_sl10"), "l2", "nof1_nohour", {}),
    "v2_reg13_50":     (("pnl", 1, "c6_tpnone_sl10"), "l2", "nof1", {}),
    "v2_reg13_env":    (("pnl", 0, "c6_tpnone_sl10"), "l2", "all", {"rows": "env"}),
    "v2_reg9_nof1":    (("pnl", 0, "c9_tpnone_sl10"), "l2", "nof1", {}),
    "v2_reg4_nof1":    (("pnl", 0, "c4_tpnone_slnone"), "l2", "nof1", {}),
    "v2_reg13_d4":     (("pnl", 0, "c6_tpnone_sl10"), "l2", "nof1", {"depth": 4, "min_n": 600, "lr": 0.03, "rounds": 1200}),
    # name: (label spec, loss, feature filter, params)
    "reg13_all":   (("pnl", 0, "c6_tpnone_sl10"), "l2", "all", {}),
    "reg13_nof1":  (("pnl", 0, "c6_tpnone_sl10"), "l2", "nof1", {}),
    "reg4s_all":   (("pnl", 0, "c19_tpnone_sl20"), "l2", "all", {}),
    "cls13_all":   (("win", 0, "c6_tpnone_sl10"), "log", "all", {}),
    "reg13_5050":  (("pnl2", None, "c6_tpnone_sl10"), "l2", "all", {}),          # mean of the 35 and 50 ms labels
    "reg13_d4":    (("pnl", 0, "c6_tpnone_sl10"), "l2", "all", {"depth": 4, "min_n": 500}),
    "reg4s_nof1":  (("pnl", 0, "c19_tpnone_sl20"), "l2", "nof1", {}),
    "reg13_env":   (("pnl", 0, "c6_tpnone_sl10"), "l2", "all", {"rows": "env"}),  # trained on in-envelope dumps only
}

def feats(spec):
    fn = [f for f in L.FN if f not in DROP_F]
    if spec.startswith("list:"):
        keep = json.load(open(spec[5:])); fn = [f for f in fn if f in keep]
    if "nof1" in spec: fn = [f for f in fn if f != "f1"]
    if "nohour" in spec: fn = [f for f in fn if f != "hour"]
    return [L.FNI[f] for f in fn], fn

def setup():
    D = {day: L.load(day) for day in DAYS}
    d2 = D["R2"]; t = d2["t"]; cut = np.quantile(t, 0.70)
    G["D"] = D; G["cut"] = cut

def run_variant(name):
    D = G["D"]; cut = G["cut"]; (kind, lat, exn), loss, fspec, prm = VARIANTS[name]
    e = L.EXI[exn]; cols, fn = feats(fspec); prm = dict(prm); rows_spec = prm.pop("rows", None)
    d2 = D["R2"]
    if kind == "pnl": y = ylab(d2, lat, e)
    elif kind == "pnl2": y = 0.5 * (ylab(d2, 0, e) + ylab(d2, 1, e))
    elif kind == "win": y = (ylab(d2, lat, e) > 0).astype(float); y[np.isnan(ylab(d2, lat, e))] = np.nan
    ok = np.isfinite(y)
    if rows_spec == "env": ok &= d2["env"]
    yc = np.clip(np.nan_to_num(y), -0.10, 0.20) if loss == "l2" else np.nan_to_num(y)
    fitm = ok & (d2["t"] < cut); valm = ok & (d2["t"] >= cut)
    E = GT.edges_of(d2["Xall"][:, cols], fitm)
    B = {day: GT.binize(D[day]["Xall"][:, cols], E) for day in DAYS}
    t0 = time.time(); seeds = int(prm.pop("seeds", 1))
    models = [GT.fit(B["R2"], yc, fitm, valm, loss=loss, seed=s, **prm) for s in range(seeds)]      # seed-averaged (bagged) ensemble
    model = models[0]
    P = {day: np.mean([GT.predict(m_, B[day]) for m_ in models], 0) for day in DAYS}
    if rows_spec == "env":
        for day in DAYS: P[day] = np.where(D[day]["env"], P[day], -np.inf)
    imp = np.mean([GT.importance(m_, len(cols)) for m_ in models], 0); top = [(fn[i], round(float(imp[i]), 3)) for i in np.argsort(-imp)[:15]]
    # threshold on R2-val: top q of R2-val predictions -> absolute cut; best engine P&L at 35 ms with the label's exit
    pv = P["R2"][valm]; cands = []
    for q in (0.001, 0.002, 0.003, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.05):
        c = float(np.quantile(pv, 1 - q))
        o = L.sim(d2, (P["R2"] >= c) & (d2["t"] >= cut), 0, e); o2 = L.sim(d2, (P["R2"] >= c) & (d2["t"] >= cut), 1, e)
        cands.append((o["pnl"] + o2["pnl"], q, c, o["fill"]))
    best = max(cands, key=lambda x: (round(x[0], 3), -x[1]))
    res = dict(name=name, label=[kind, lat, exn], loss=loss, feats=fspec, prm=prm, rows=rows_spec, best_round=[m_["best_round"] for m_ in models],
               fit_s=round(time.time() - t0), top_imp=top, val_curve=[(round(a, 3), q, round(c, 5), n) for a, q, c, n in cands], thr=best[2], q=best[1])
    # evaluation: every day, both latencies, the label exit + the other live exit; baseline (IMIT1 top4) alongside
    ev = {}
    for day in DAYS:
        d = D[day]; win = (d["t"] >= cut) if day == "R2" else np.ones(len(d["t"]), bool)
        sel = (P[day] >= best[2]) & win
        base = np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"]) & win
        for latx in (0, 1, 2):
            for ex in sorted({e, L.E_13, L.E_4S}):
                o = L.sim(d, sel, latx, ex); b = L.sim(d, base, latx, ex)
                ev[f"{day}|{(35, 50, 75)[latx]}|{L.EXN[ex]}"] = dict(new=[round(o["pnl"], 3), o["fill"], o["att"], round(o["per_fill"], 4), round(o["winr"], 3)],
                                                               base=[round(b["pnl"], 3), b["fill"], b["att"], round(b["per_fill"], 4), round(b["winr"], 3)])
    res["eval"] = ev
    sw = {}
    for c in (-0.004, -0.002, 0.0, 0.002, 0.004, 0.006, 0.008, 0.010, 0.013, 0.016, 0.020):
        for day in DAYS:
            d = D[day]; win = (d["t"] >= cut) if day == "R2" else np.ones(len(d["t"]), bool)
            for latx in (0, 1):
                o = L.sim(d, (P[day] >= c) & win, latx, e)
                sw[f"{c:+.3f}|{day}|{(35, 50)[latx]}"] = [round(o["pnl"], 2), o["fill"], o["att"], round(o["per_fill"], 4)]
    res["sweep"] = sw
    np.save(f"{OUT}/pred_{name}.npy", np.concatenate([P[day] for day in DAYS]))
    json.dump(dict(models=models, cols=cols, fn=fn, edges=[x.tolist() for x in E]), open(f"{OUT}/model_{name}.json", "w"))
    return res

if __name__ == "__main__":
    names = sys.argv[1:] or list(VARIANTS)
    setup()
    with get_context("fork").Pool(min(4, len(names))) as p:
        for res in p.imap_unordered(run_variant, names):
            with open(f"{OUT}/dd5_registry.jsonl", "a") as f: f.write(json.dumps(res) + "\n")
            print(f"\n### {res['name']} (label {res['label']}, {res['loss']}, feats {res['feats']}, rounds {res['best_round']}, {res['fit_s']} s) "
                  f"thr {res['thr']:+.4f} (R2-val top {100 * res['q']:.2f}%)", flush=True)
            print("  top features:", ", ".join(f"{a} {b}" for a, b in res["top_imp"][:10]))
            print("  R2-val curve (pnl, q, cut, fills):", res["val_curve"])
            for k, v in res["eval"].items():
                print(f"  {k:28s} NEW {v['new'][0]:+7.2f} SOL fills {v['new'][1]:4d}/{v['new'][2]:4d} {v['new'][3]:+.4f}/fill win {v['new'][4]:.2f} | "
                      f"BASE {v['base'][0]:+7.2f} fills {v['base'][1]:4d}/{v['base'][2]:4d} {v['base'][3]:+.4f}/fill", flush=True)
