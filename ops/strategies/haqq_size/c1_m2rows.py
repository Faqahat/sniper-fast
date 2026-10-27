#!/usr/bin/env python3
"""HAQQ_SIZE step C1 (read-only): M2 picks on the held-out 24 h at each built size (haqq_model/m3_m2.py's selection: M2 >= the
live threshold inside the envelope; exit c4; dd_lib.sim engine limits, AMS main server; FIX 0.0051 per fill, FAIL 0.0005 per
guard-blocked buy). For each size: the engine's tried rows and their P&L at 35 / 50 / 75 ms; plus per-row sizing features
(curve SOL at the dump, the haqq_model score). Small output; the big per-size npz can then be deleted.
usage: c1_m2rows.py <npz> <size>  -> OUT/m2/rows_s<size>.pkl"""
import sys, json, pickle
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd_lib as L
import dd20_shadow_eval as D20
OUT = "/home/moiz/sniper-data/haqq_size"; HQS = "/home/moiz/sniper-data/haqq_sel"; HM = "/home/moiz/sniper-data/haqq_model"
W0 = 1793038500; W1 = 1793124900
E4 = L.EXI["c4_tpnone_slnone"]
BUNDLE = f"{L.OUT}/m2_v3_reg4_top25.json"

if __name__ == "__main__":
    path, size = sys.argv[1], float(sys.argv[2])
    d = D20.load_dd1(path, W0, W1)
    meta = json.load(open(f"{HQS}/m2/work/day_HQ_meta.json"))["meta"]
    mint = np.array([meta[t]["m"] for t in d["tok"]])
    B0 = json.load(open(BUNDLE)); cols = [L.FNI[f] for f in B0["fn"]]
    P, B = D20.bundle_scores(BUNDLE, d["Xall"][:, cols]); MIN = float(B["thr_default"])
    sel = d["env"] & (P >= MIN)
    out = dict(size=size, MIN=MIN, n_sel=int(sel.sum()))
    for lat in (35, 50, 75):
        o = L.sim(d, sel, (35, 50, 75).index(lat), E4, servers=("a",), detail=True)
        out[lat] = [(int(r), float(p), int(f)) for r, sv, p, f in o["rows"]]
        print(f"size {size}: {lat} ms att {o['att']} fills {o['fill']} P&L {o['pnl']:+.3f}", flush=True)
    rr = sorted({r for lat in (35, 50, 75) for r, _, _ in out[lat]})
    X = d["Xall"]
    # haqq_model score: +14-slot model if the dump is >= create + 14 slots, else the create-slot model
    SC = {}
    for n in (0, 14):
        Z = pickle.load(open(f"{HM}/model_n{n}.pkl", "rb")); SC[n] = {m: (float(s), int(sl)) for m, s, sl in zip(Z["mint"], Z["score"], Z["slot"])}
    feats = {}
    for r in rr:
        m = mint[r]; s_ = int(d["s"][r])
        if m in SC[14] and s_ >= SC[14][m][1] + 14: sc = SC[14][m][0]
        elif m in SC[0]: sc = SC[0][m][0]
        else: sc = np.nan
        feats[r] = dict(mint=m, s=s_, t=int(d["t"][r]), curve=float(X[r, L.FNI["curve"]]), drop=float(X[r, L.FNI["drop_pct"]]),
                        sol=float(X[r, L.FNI["sol"]]), score=sc, key=(m, s_, int(d["k"][r])))
    out["feats"] = feats
    pickle.dump(out, open(f"{OUT}/m2/rows_s{size:g}.pkl", "wb"))
