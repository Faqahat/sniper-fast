#!/usr/bin/env python3
"""Parity fixture for the Rust port: ~200 r55 positions (deterministic: every k-th chain-covered position by trigger time),
the 153-input vector at EVERY send slot t from the trigger slot to fill slot - 1 (inputs use data up to slot t - 1; the send at
fill-1 is the decided one = what fp6 scored), per-seed and mean scores, thr, block. No P&L in the file.
Out: /home/moiz/sniper-data/flatperfect/parity_r55.jsonl (line 1 = meta)"""
import os, sys, json, pickle, math
os.environ.setdefault("CHAIN_DIR", "/home/moiz/sniper-data/flatperfect/chain")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatperfect")
import numpy as np, lightgbm as lgb
import fp1_chain as C, fp2_own
OUTD = "/home/moiz/sniper-data/flatperfect"
FR = json.load(open("FROZEN_FLAT.json")); FEATS = FR["features"]
B = {k: [lgb.Booster(model_file=f"{OUTD}/{fn}") for fn in sorted(v["models"])] for k, v in FR["kinds"].items()}
ex = pickle.load(open(f"{OUTD}/runs/ex_r55.pkl", "rb")); own = fp2_own.run_feats(ex)
sc = {r["key"]: r for r in json.load(open(f"{OUTD}/r55_score_c2352.json"))["rows"]}
pos = sorted(ex["pos"], key=lambda p: p["t0"])
for p in pos: p["key"] = f'{p["run"]}|{p["mint"]}|{p["pid"]}|{p["kind"]}|{p["w"]}'
cov = [p for p in pos if sc[p["key"]]["cov"] and sc[p["key"]]["elig"]]
step = max(1, len(cov) // 200); sel = cov[::step][:200]
out = open(f"{OUTD}/parity_r55.jsonl", "w")
out.write(json.dumps({"meta": {"features": FEATS, "thr": {k: v["thr"] for k, v in FR["kinds"].items()}, "models": {k: sorted(v["models"]) for k, v in FR["kinds"].items()},
                      "score": "mean over seeds of sigmoid(sum of leaf values) = LightGBM predict(); NaN inputs = null",
                      "send_rule": "send at slot t uses data with slot <= t-1; the landing at fill slot F was decided at t = F-1",
                      "source": "r55 copy 11-04 07:00-23:58 PKT (dip_ams_r55_2352.jsonl), chain = /home/moiz/sniper-data/flatperfect/chain"}}) + "\n")
nl = 0; mism = 0
for p in sel:
    q = dict(p); q["whale64"] = C.L.pk64(p["whale"]) if p.get("whale") else None
    F = p["buy_slot"]; s0 = p["trig_slot"]
    for t in range(s0, F):
        q["buy_slot"] = t + 1
        f = C.feats(q)
        if f is None: break
        x = dict(own[p["key"]]); x.update(f)
        v = [x.get(c, np.nan) for c in FEATS]
        arr = np.array([v], float)
        ss = [float(b.predict(arr)[0]) for b in B[p["kind"]]]; s = float(np.mean(ss))
        thr = FR["kinds"][p["kind"]]["thr"]
        rec = {"key": p["key"], "mint": p["mint"], "kind": p["kind"], "trig_slot": s0, "trig_idx": p["trig_idx"], "fill_slot": F,
               "send_slot": t, "data_upto_slot": t - 1, "decided": t == F - 1,
               "x": [None if (isinstance(a, float) and math.isnan(a)) else (float(a) if not isinstance(a, (int, np.integer)) else int(a)) for a in v],
               "seed_scores": ss, "score": s, "thr": thr, "block": s >= thr}
        if t == F - 1 and abs(s - sc[p["key"]]["score"]) > 1e-9: mism += 1
        out.write(json.dumps(rec) + "\n"); nl += 1
print("positions", len(sel), "lines", nl, "decided-score mismatches vs fp6", mism,
      "T2", sum(p["kind"] == "T2" for p in sel), "blocked", sum(sc[p["key"]]["blocked"] for p in sel))
