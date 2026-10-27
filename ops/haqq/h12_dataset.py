#!/usr/bin/env python3
# haqq SELL study, step 12: slot-level hazard dataset per lot. Row = (lot, slot d after the trigger) while the lot is unsold;
# features use only information up to the END of slot d-1 (real-time computable); label = its first sell lands in slot d.
# -> sniper-data/haqq/ds.npz (X, y, lot index, d, run, profile) + ds_meta.json
# usage: h12_dataset.py [eval]  -- 'eval' keeps rows past the real exit up to exit+12 slots (for honest exit-slot match rates) -> ds_eval.npz
import sys, json, pickle, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
lots = json.load(open(f"{H.OUT}/lots.json")); P = pickle.load(open(f"{H.OUT}/lotpaths.pkl", "rb"))
_led = json.load(open(f"{H.OUT}/ledger.json")); _a = np.polyfit([r["s"] for r in _led], [r["bt"] for r in _led], 1)
def bt_of(slot): return float(np.polyval(_a, slot))
PROF = {0.25: 0, 0.27: 1, 0.3: 2, 0.4: 3, 0.49: 4, 0.01: 5}
def prof(sz): return PROF.get(round(sz, 2), 6 if sz >= 0.6 else 7)
F = ["d", "d_buy", "dmod8", "dmod5", "prof", "size", "dip", "trig_sol", "drop", "age_s", "vsol_in", "delay", "bi",
     "ret", "ret_peak", "ret_min", "dd", "dret1", "dret4", "dret8",
     "ob1", "ob2", "ob4", "ob8", "nb1", "nb4", "nb8", "os1", "os4", "os8", "ns4", "ns8", "ob_cum", "os_cum", "nb_cum",
     "since_b", "since_b03", "since_s03", "since_tr", "mb4", "ms4", "own4", "ntr4", "hour"]
FI = {k: i for i, k in enumerate(F)}
EVAL = len(sys.argv) > 1 and sys.argv[1] == 'eval'
X = []; y = []; L = []; Dd = []; RUN = []
RI = {"R1": 1, "R2": 2, "R3": 3, "R4": 4}
for p in P:
    l = lots[p["li"]]; b = l["buy"]
    if not b["dip"]: continue                       # reference slot = trigger slot (dip lots); non-dip handled separately
    first = p["first"]; D = p["D"]
    bs = p["bslot"]; pf = prof(b["sol"])
    re = p["ret_end"]; ob = p["ob"]; os_ = p["os"]; nb = p["nb"]; ns = p["ns"]; mb = p["mb"]; ms = p["ms"]; own = p["own"]; ntr = p["ntr"]
    peak = -9.0; mn = 9.0
    last_b = bs; last_b03 = bs; last_s03 = bs; last_tr = bs
    hr = H.pkth(bt_of(b["s"]))
    for d in range(bs + 1, (D if EVAL else min(first, D)) + 1):
        j = d - 1                                       # info up to the end of slot d-1
        r = re[j]
        if np.isnan(r): continue
        peak = max(peak, float(r)); mn = min(mn, float(r))
        if j > bs:
            if ob[j] > 0: last_tr = j
            if os_[j] > 0: last_tr = j
            if mb[j] >= 0.1: last_b = j
            if mb[j] >= 0.3: last_b03 = j
            if ms[j] >= 0.3: last_s03 = j
        def w(a, n): return float(a[max(bs + 1, j - n + 1):j + 1].sum())
        def rch(n):
            k0 = max(bs, j - n); v0 = re[k0]
            return float(r - v0) if not np.isnan(v0) else 0.0
        row = [d, d - bs, d % 8, d % 5, pf, b["sol"], 1, b["trig_sol"] or 0, b["drop"] or 0, b["age"] / 1000, b["vsol"], b["delay"] or 0, l["bi"],
               float(r), peak, mn, peak - float(r), rch(1), rch(4), rch(8),
               w(ob, 1), w(ob, 2), w(ob, 4), w(ob, 8), w(nb, 1), w(nb, 4), w(nb, 8), w(os_, 1), w(os_, 4), w(os_, 8), w(ns, 4), w(ns, 8),
               float(ob[bs + 1:j + 1].sum()), float(os_[bs + 1:j + 1].sum()), float(nb[bs + 1:j + 1].sum()),
               j - last_b, j - last_b03, j - last_s03, j - last_tr, float(mb[max(bs + 1, j - 3):j + 1].max()) if j > bs else 0.0,
               float(ms[max(bs + 1, j - 3):j + 1].max()) if j > bs else 0.0, w(own, 4), w(ntr, 4), hr]
        X.append(row); y.append(1 if d == first else 0); L.append(p["li"]); Dd.append(d); RUN.append(RI[l["run"]])
X = np.array(X, np.float32); y = np.array(y, np.int8); L = np.array(L, np.int32); Dd = np.array(Dd, np.int32); RUN = np.array(RUN, np.int8)
np.savez(f"{H.OUT}/{'ds_eval' if EVAL else 'ds'}.npz", X=X, y=y, L=L, d=Dd, run=RUN)
json.dump(dict(feats=F, prof=PROF), open(f"{H.OUT}/ds_meta.json", "w"))
print("rows", len(X), "positives", int(y.sum()), "lots", len(set(L.tolist())), "by run", collections.Counter(RUN.tolist()))
