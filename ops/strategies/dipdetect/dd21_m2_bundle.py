#!/usr/bin/env python3
# M2 engine bundle (agent 10-25 ~01:00 PKT): ONE file the engine loads with --dip-m2 FILE (src/dip_model.rs):
#   the 3-seed GBDT (trees flattened to arrays), its 25 feature names / bin edges, the default threshold (Stage A, chosen on
#   R2-val only by dd15_stageA.py) and the wallet sets the features use (cohort_train.json, the 3 IMIT1 wallets, botids.json).
# Every float is written as a STRING (Python repr = shortest round-trip): the engine parses it with Rust's correctly rounded
# str::parse::<f64>, so edges / leaf weights are bit-identical (serde_json's default float parser can be 1 ulp off).
# Verification: the flattened model is re-scored here on every dump row of R2/R3/R1/R4 and must equal pred_<name>.npy exactly.
# usage: python3 dd21_m2_bundle.py [name] [threshold]
import sys, json, hashlib, time
import numpy as np
import dd_lib as L
import dd_gbdt as GT
OUT = L.OUT
NAME = sys.argv[1] if len(sys.argv) > 1 else "v3_reg4_top25"
THR = float(sys.argv[2]) if len(sys.argv) > 2 else json.load(open(f"{OUT}/dd15_stageA.json"))["thr_top25"]
SRC = {"model": f"{OUT}/model_{NAME}.json", "botids": "/home/moiz/sniper-data/strategies/patterns/botids.json",
       "cohort": "/home/moiz/sniper/ops/overnight/sel/cohort_train.json"}
T3 = ["HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"]
DAYS = ("R2", "R3", "R1", "R4")
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
S = repr          # float -> exact string

def flatten(trees):
    f, b, l, r, w, roots = [], [], [], [], [], []
    def add(n):
        k = len(f); f.append(-1); b.append(0); l.append(-1); r.append(-1); w.append(0.0)
        if "w" in n: w[k] = float(n["w"]); return k
        f[k] = int(n["f"]); b[k] = int(n["b"])
        lk = add(n["l"]); rk = add(n["r"]); l[k] = lk; r[k] = rk
        return k
    for t in trees: roots.append(add(t))
    return dict(roots=roots, f=f, b=b, l=l, r=r, w=w)

def pred_flat(seed, B):
    f = np.array(seed["f"]); b = np.array(seed["b"]); l = np.array(seed["l"]); r = np.array(seed["r"]); w = np.array(seed["w"], np.float64)
    out = np.full(len(B), seed["F0"]); rows = np.arange(len(B))
    for root in seed["roots"]:
        idx = np.full(len(B), root)
        for _ in range(8):
            leaf = f[idx] < 0
            if leaf.all(): break
            fi = np.where(leaf, 0, f[idx]); go_l = B[rows, fi] <= b[idx]
            idx = np.where(leaf, idx, np.where(go_l, l[idx], r[idx]))
        out += seed["lr"] * w[idx]
    return out

if __name__ == "__main__":
    m = json.load(open(SRC["model"]))
    bots = json.load(open(SRC["botids"])); coh = json.load(open(SRC["cohort"]))
    assert all(v[0] != 0 for v in bots.values()), "bot id 0 would read as 'no bot' in p1_build"
    seeds = []
    for mm in m["models"]:
        fl = flatten(mm["trees"]); fl["F0"] = float(mm["F0"]); fl["lr"] = float(mm["lr"]); seeds.append(fl)
    # verify the flattened model against the study's predictions (exact)
    E = [np.array(e, dtype=np.float64) for e in m["edges"]]
    P = np.load(f"{OUT}/pred_{NAME}.npy"); o = 0; worst = 0.0
    for day in DAYS:
        d = L.load(day); B = GT.binize(d["Xall"][:, m["cols"]], E); n = len(B)
        ps = [pred_flat(s, B) for s in seeds]
        p = ((ps[0] + ps[1]) + ps[2]) / 3.0                     # np.mean over the 3 seeds, in numpy's own order
        p2 = np.mean(ps, 0)
        worst = max(worst, float(np.max(np.abs(p - P[o:o + n]))), float(np.max(np.abs(p2 - P[o:o + n]))))
        print(f"  {day}: {n} rows, max |flat - npy| {np.max(np.abs(p - P[o:o + n])):.3e}, picks >= thr {(p >= THR).sum()}", flush=True)
        o += n
    assert worst == 0.0, f"flattened model differs from pred_{NAME}.npy by {worst}"
    bundle = {
        "kind": "dip_m2_bundle", "format": 1, "name": NAME,
        "built": time.strftime("%Y-%m-%d %H:%M PKT", time.gmtime(time.time() + 5 * 3600)),
        "note": "Stage A dip detector (ops/strategies/dipdetect/PORT.md): score = mean of the seeds' GBDT predictions (F0 + lr * sum of leaf "
                "weights; bin = searchsorted(edges, float32(x), right) + 1, non-finite -> 0; left when bin <= b); predicted SOL per attempt at 35 ms, "
                "0.55 SOL, exit c4. Floats are strings (exact).",
        "sources": {k: {"path": p, "sha256": sha(p)} for k, p in SRC.items()},
        "fn": m["fn"], "thr_default": S(float(THR)), "combine": "mean",
        "edges": [[S(float(x)) for x in e] for e in m["edges"]],
        "seeds": [dict(F0=S(s["F0"]), lr=S(s["lr"]), roots=s["roots"], f=s["f"], b=s["b"], l=s["l"], r=s["r"], w=[S(x) for x in s["w"]]) for s in seeds],
        "cohort": sorted(coh), "t3": T3,
        "bots": {u: [int(v[0]), v[1]] for u, v in sorted(bots.items())},
        "consts": {"slot_ms": 212.0, "block_size_default": 400, "big_sell_lamports": 1000000000, "drop2_pct": 2.0, "coh20_trades": 80, "coh20_slots": 20,
                   "pro_after_ms": 1000.0, "bot_hold_frac": 0.01},
    }
    p = f"{OUT}/m2_{NAME}.json"
    json.dump(bundle, open(p, "w"), separators=(",", ":"))
    print(f"bundle {p}: {len(seeds)} seeds, {sum(len(s['roots']) for s in seeds)} trees, {sum(len(s['f']) for s in seeds)} nodes, {len(m['fn'])} features, "
          f"thr {THR!r}, cohort {len(coh)}, t3 {len(T3)}, bots {len(bots)} (family {sum(1 for v in bots.values() if v[1].startswith('F'))}), sha256 {sha(p)}")
