#!/usr/bin/env python3
# Parity vectors for the Rust port of the IMIT1 dip selector (src/dip.rs): for N tokens of the study data (R2, phaseA_sel, real
# limits not needed), the launch facts, the repaired trade tape (rp.read_bucket, RP_REPAIR=1), the block sizes of the slots
# involved (core/slotsize2.json), and for every dump event the 42 features (sel/sel_lib.py fv order, tgt_* and coh_* included)
# and the frozen IMIT1 score. -> testdata/imit1_parity.json   usage: python3 -I export_parity.py [N tokens]
import os, sys, json, random, collections
os.environ.update(RP_PHASEA_R2="phaseA_sel", SELL_LAT="75", SLIPIMP="1", DIP_REAL_SLIP="1", SEL_SLIP="1", DIP_LATS="35", DIP_B="0.5", DIP_HS="4",
                  DIP_BUSY="0", DIP_HLAG="0", DIP_MAX_AGE="1800", DIP_COHORT_FILE="/home/moiz/sniper/ops/overnight/sel/cohort_train.json")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import selexit2 as X
import numpy as np
import gbdt_np as G
M = json.load(open("/home/moiz/sniper/ops/overnight/sel/IMIT1.json")); FE = M["features"]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
random.seed(7)
r2 = [m for m, c in X.L.items() if c["run"] == "R2"]
random.shuffle(r2)
byb = collections.defaultdict(set)
for m in r2[:N * 6]: byb[("R2", X.rp.bucket(m))].add(m)
X.byb = byb
def fv(r, k):
    x = r["xf"]; t = r["tok"]
    if k == "drop_pct": return (1 - r["drop"]) * 100
    if k in ("first_big", "ins"): return float(r[k])
    if k in x: return x[k]
    if k == "prev_sell_ms": return r["prev_sell_ms"] if r["prev_sell_ms"] >= 0 else 1e9
    if k in ("n_tr", "vmax", "since_buy"): return t[k] if t[k] is not None and t[k] >= 0 else 1e9
    return r[k]
toks = []
for key in sorted(byb):
    if len(toks) >= N: break
    rows, _ = X.work(key)
    if not rows: continue
    tapes = X.rp.read_bucket(key[0], key[1], byb[key])
    ev = collections.defaultdict(list)
    for r in rows: ev[r["m"]].append(r)
    for m, rs in ev.items():
        rs.sort(key=lambda r: r["age"]); past = []
        for r in rs:                              # tgt features exactly as sel_lib (labels of earlier events on the token)
            t0 = r["age"] * 1000.0; b = [x for x in past if x < t0]
            r["tgt_n"] = len(b); r["tgt_since"] = (t0 - max(b)) / 1000.0 if b else 1e9
            for w, d in r["lab"].items(): past.append(t0 + d)
        tr = tapes[m]; c = X.L[m]; S0 = c["slot"]
        out_ev = []
        for r in rs:
            k = next((j for j, t in enumerate(tr) if (not t["buy"]) and t["sol"] >= X.MIN_SELL and not t.get("syn") and t["vsol"] < 100e9 and round((t["s"] - S0) * X.SMS / 1000, 2) == r["age"]), None)
            x = np.array([[fv(r, f) for f in FE]], float)
            B = np.zeros(x.shape, np.int16)
            for j, e in enumerate(M["edges"]):
                bb = np.searchsorted(np.array(e), x[:, j], side="right") + 1; bb[np.isnan(x[:, j])] = 0; B[:, j] = bb
            sc = M["F0"] + sum(M["lr"] * G.pred(t, B)[0] for t in M["trees"])
            out_ev.append(dict(k=k, age=r["age"], feats=[float(v) for v in x[0]], score=float(sc), lab=r["lab"]))
        slots = sorted({t["s"] for t in tr})
        toks.append(dict(mint=m, launch=dict(slot=c["slot"], idx=c.get("idx"), creator=c.get("creator"), user=c.get("user"), sig=c.get("sig"), bt=c.get("bt"),
                                             mayhem=bool(c.get("mayhem")) or "InitializeMayhemState" in (c.get("ixn") or [])),
                         trades=[dict(s=t["s"], i=t["i"], j=t["j"], sig=t["sig"], user=t["user"], buy=t["buy"], sol=t["sol"], tok=t["tok"], vsol=t["vsol"], vtok=t["vtok"],
                                      fbps=t["fbps"], cbps=t["cbps"], syn=bool(t.get("syn"))) for t in tr],
                         ss={str(s): X.SS.get(s) for s in slots if X.SS.get(s)}, events=out_ev))
        if len(toks) >= N: break
out = dict(model="IMIT1", features=FE, cohort=sorted(X.COH), targets=list(X.TARGETS), min_sell=X.MIN_SELL, max_age=X.MAX_AGE, tokens=toks)
json.dump(out, open("/home/moiz/sniper/testdata/imit1_parity.json", "w"))
print(f"tokens {len(toks)}, events {sum(len(t['events']) for t in toks)}, trades {sum(len(t['trades']) for t in toks)}")
