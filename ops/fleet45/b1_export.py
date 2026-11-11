#!/usr/bin/env python3
"""dip46 B1: export the frozen B0 model (push-l5/opt2 FROZEN.md: decoder HGB classifier on the 25 F0 features + regressor HGB on the
"lite" features + the decoder score; FINAL train r65, r66, r71, r72fit, r72test) to the engine's JSON, and check the JSON scorer
against sklearn on the audit's rows.

  b1_export.py [--pkl ~/sniper-data/push4-audit/frozen_models.pkl] [--out testdata/dip46_b1_model.json]
               [--check ~/sniper-data/push4-audit/new/snap_all.parquet] [--n 20000]

Floats are stored as their IEEE-754 bit patterns (u64), so the engine reads exactly sklearn's thresholds and leaf values.
Prints the file's sha256 (the engine's built-in FROZEN_SHA256 must be this value).
"""
import argparse, os, sys, json, pickle, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b1_lib as B

ap = argparse.ArgumentParser()
ap.add_argument("--pkl", default=os.path.expanduser("~/sniper-data/push4-audit/frozen_models.pkl"))
ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../testdata/dip46_b1_model.json"))
ap.add_argument("--check", default=os.path.expanduser("~/sniper-data/push4-audit/new/snap_all.parquet"))
ap.add_argument("--n", type=int, default=20000)
a = ap.parse_args()

o = pickle.load(open(a.pkl, "rb"))["final"]
dec, reg = o["dec"], o["reg"]
assert list(dec.feature_names_in_) == B.F0 and list(reg.feature_names_in_) == B.LITE
j = dict(name="B0 frozen (push-l5/opt2 FINAL train; re-created by push4-audit/p4_models.py)", train=o["train"],
         rule=dict(dec_min=0.2, b0_thr=0.002, b1_thr=0.0, window=8, gate="fleet tries (signature) in slots S-2..S-1 (n2 > 0)", size_sol=0.8, dp=26, hold=3, drop=0.10,
                   cost_slot_sol=0.055e-3),
         schema=B.schema_hash(), dec=B.export_gbm(dec), reg=B.export_gbm(reg))
raw = json.dumps(j, separators=(",", ":")).encode()
open(a.out, "wb").write(raw)
sha = hashlib.sha256(raw).hexdigest()
print("wrote", os.path.abspath(a.out), len(raw), "bytes sha256", sha, "| dec trees", len(j["dec"]["trees"]), "reg trees", len(j["reg"]["trees"]))

if a.check and os.path.exists(a.check):
    import pandas as pd, numpy as np
    X = pd.read_parquet(a.check); X["last_buy"] = X.last_buy.astype(int)
    X = X.sample(min(a.n, len(X)), random_state=1)
    p = dec.predict_proba(X[B.F0])[:, 1]; X["score"] = p; r = reg.predict(X[B.LITE])
    M = B.Model(a.out); dp = dr = 0.0; nreg = 0
    for k, row in enumerate(X[B.F0].itertuples(index=False)):
        pp, rr = M.score([float(v) for v in row])
        dp = max(dp, abs(pp - p[k]))
        if rr is not None: dr = max(dr, abs(rr - r[k])); nreg += 1
    print(f"check vs sklearn on {len(X)} rows: max |dec diff| {dp:.3g}, max |reg diff| {dr:.3g} on {nreg} rows with dec >= 0.2")
    assert dp < 1e-12 and dr < 1e-12
