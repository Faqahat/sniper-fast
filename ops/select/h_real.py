#!/usr/bin/env python3
# STRATEGY AT OUR REAL LANDING (read-only, offline). Goal: >= 1 SOL/h when our buy lands ~74 ms after the create (behind
# the fast snipers). Train GBDTs (live-computable features only) on run 1 with PROXY entries behind k outside trades /
# after the create slot, for many exits; choose (entry proxy, exit, top-k) on VALIDATION (run 1 last 20%) by SOL/h; then
# TEST on the forward run's engine-watched launches with the REAL place in line: every outside tx the shadow engine saw
# before decide + LAND ms is ahead of us (exact curve replay, same sim as training).
# usage: python3 h_real.py <table_dump.jsonl.gz> <phaseA_fwd> <run2 launches.jsonl> <scores.jsonl,...> <run2 start bt> <out dir> [LAND ms]
import sys, os, json, gzip, glob, zlib, statistics, collections
import numpy as np
TAB, PA, LJ, SC, FWD0, OUT = sys.argv[1:7]; FWD0 = float(FWD0); LAND = float(sys.argv[7]) if len(sys.argv) > 7 else 74.0
os.makedirs(OUT, exist_ok=True); FIX, SIZE = 0.015, 0.5
H = os.path.dirname(os.path.abspath(__file__))
# ---- the training sim, verbatim from b_launch.py (exits, fees, our own curve impact)
bsrc = open(os.path.join(H, "b_launch.py")).read()
ns = {}; exec(bsrc[bsrc.index("X = 493827160"):bsrc.index("CK = {")] + bsrc[bsrc.index("EVX_DELAY = True"):bsrc.index("def feats_flow")], ns)
sim, HZ, TPSL, TRAIL, EVX = ns["sim"], ns["HZ"], ns["TPSL"], ns["TRAIL"], ns["EVX"]
EXITS = [("h", v) for v in HZ.values()] + [("tpsl",) + x[1:] for x in TPSL] + [("trail",) + x[1:] for x in TRAIL] + [("ev",) + x[1:] for x in EVX]
def outcome_cols(r):
    o = {}
    for nm, v in HZ.items(): o[f"h{nm}"] = r[("h", v)]
    for x in TPSL: o[x[0]] = r[("tpsl",) + x[1:]]
    for x in TRAIL: o[x[0]] = r[("trail",) + x[1:]]
    for x in EVX: o[x[0]] = r[("ev",) + x[1:]]; o[x[0] + "_eos"] = r[("eos",) + x[1:]]
    return o
EXN = list(outcome_cols({**{("h", v): 0 for v in HZ.values()}, **{("tpsl",) + x[1:]: 0 for x in TPSL}, **{("trail",) + x[1:]: 0 for x in TRAIL},
                         **{("ev",) + x[1:]: 0 for x in EVX}, **{("eos",) + x[1:]: 0 for x in EVX}}).keys())
# ---- model code (e_model's fit/binize/stats), live feature set (+ anti-dump history)
esrc = open(os.path.join(H, "e_model.py")).read()
sys.argv = [sys.argv[0], TAB, OUT]
exec(esrc[:esrc.index("REPORT = {}")])
fk = [k for k, (tt, _) in cols.items() if tt in ("T0", "T0b", "H") and not k.startswith("h_fd") and k not in ("create_cu", "create_idx", "create_fee")]
Xf = np.column_stack([cols[k][1] for k in fk])
run1 = bt < FWD0; n1 = run1.sum(); TRN = run1 & (idx < int(n1 * .8)); VAL = run1 & (idx >= int(n1 * .8)); FWD = ~run1
Bm = binize(Xf, TRN)
hrs = lambda m: (bt[m].max() - bt[m].min()) / 3600 if m.any() else 1e-9
print(f"rows {N}: train {TRN.sum()} ({hrs(TRN):.1f} h)  val {VAL.sum()} ({hrs(VAL):.1f} h)  forward {FWD.sum()} ({hrs(FWD):.1f} h); features {len(fk)}", flush=True)
# ---- REAL place in line for the engine-watched forward launches
dec, obs = {}, {}
for p in SC.split(","):
    if not os.path.exists(p): continue
    for l in open(p):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("type") == "decide": dec[r["mint"]] = r
        elif r.get("type") == "obs": obs[r["mint"]] = r
L = {}
for l in open(LJ):
    try: c = json.loads(l)
    except Exception: continue
    L.setdefault(c["mint"], c)
def bucket(m): return zlib.crc32(m.encode()) % 256
want = {R[i]["mint"]: i for i in np.where(FWD)[0] if R[i]["mint"] in dec and R[i]["mint"] in obs and R[i]["mint"] in L}
byb = collections.defaultdict(set)
for m in want: byb[bucket(m)].add(m)
REAL = {}; grad_out = 0
for b, ms in byb.items():
    tr_by = collections.defaultdict(list); seen = set()
    for f in glob.glob(os.path.join(PA, f"b{b:03d}", "*.jsonl.gz")):
        try:
            for line in gzip.open(f, "rt"):
                if line[2] != "T": continue
                r = json.loads(line)
                if r[1] not in ms or (r[5], r[13]) in seen: continue
                seen.add((r[5], r[13]))
                tr_by[r[1]].append(dict(s=r[2], i=r[3], j=r[13], sig=r[5], user=r[14], buy=r[15] == 1, sol=r[16], tok=r[17], vsol=r[18], vtok=r[19], fbps=r[22], cbps=r[23]))
        except (EOFError, OSError, zlib.error): pass
    for m, tr in tr_by.items():
        tr.sort(key=lambda t: (t["s"], t["i"], t["j"])); c = L[m]; S = c["slot"]; creator = c.get("creator") or c.get("user")
        ci = c.get("idx"); gl = []; prev = ci; gi = 0
        for k, t in enumerate(tr):
            if t["sig"] == c.get("sig"): gi = k + 1; continue
            if t["s"] == S and t["i"] in (prev, prev + 1) and t["buy"]: gl.append(t); prev = t["i"]; gi = k + 1
            elif t["s"] == S and t["i"] > prev + 1: break
            elif t["s"] > S: break
        busers = {t["user"] for t in gl}; outside = lambda t: t["user"] != creator and t["user"] not in busers
        land = float(dec[m].get("at_ms", 0)) + LAND
        ahead = [x for x in (obs[m].get("outs") or "-").split(",") if x and x != "-" and float(x.split(":")[0]) < land]
        k0 = gi; n_o = 0
        while k0 < len(tr) and n_o < len(ahead):
            if outside(tr[k0]): n_o += 1
            k0 += 1
        st = tr[k0 - 1] if k0 > 0 else None
        if not st or not st["vtok"] or st["vsol"] >= 114e9: continue
        if any(t["vsol"] >= 114e9 for t in tr[k0:] if t["s"] - S <= 150): grad_out += 1; continue   # curve fills while we hold: no AMM price in our data
        fb, cb = (tr[0]["fbps"] or 95), (tr[0]["cbps"] or 30)
        REAL[m] = dict(ahead=len(ahead), **outcome_cols(sim(tr, k0, st["vsol"], st["vtok"], fb, cb, S, EXITS, outside)))
print(f"forward watched launches with a real place in line: {len(REAL)} (left out {grad_out} that graduate while held)", flush=True)
TEST = np.array([R[i]["mint"] in REAL for i in range(N)]) & FWD
# ---- search: entry proxy x exit x top-k, chosen on VALIDATION by SOL/h (0.5 SOL per trade, val launch volume)
EXS = ["fsell_30s", "fsell_30s_eos", "sk1_10s", "sk1_10s_eos", "sk2_10s", "sk2_10s_eos", "sv1_10s", "sv1_10s_eos", "h3s", "h5s", "h10s", "h30s", "tp20_sl10_30s", "trail20_10_s15_2m"]
def job(a):
    en, ex = a; out = []
    r = g(f"{en}_{ex}")
    if np.isnan(r).all(): return out
    net = r - FIX / SIZE; ok = ~np.isnan(net); y = (net > 0).astype(float)
    trees, f = fit(Bm, y, TRN & ok, VAL & ok)
    rt = np.array([REAL[R[i]["mint"]][ex] - FIX / SIZE if TEST[i] else np.nan for i in range(N)])
    for q in (0.01, 0.02, 0.05, 0.10, 0.20):
        thr = np.quantile(f[VAL & ok], 1 - q); sv = VAL & ok & (f >= thr); st = TEST & (f >= thr) & ~np.isnan(rt); sp = FWD & ok & (f >= thr)
        v, t, p = net[sv], rt[st], net[sp]
        out.append(dict(entry=en, exit=ex, q=q, thr=float(thr), n_val=len(v), val_mean=float(v.mean()) if len(v) else np.nan, val_solh=float(v.sum() * SIZE / hrs(VAL)) if len(v) else np.nan,
                        val_win=float((v > 0).mean()) if len(v) else np.nan,
                        n_test=len(t), test_mean=float(t.mean()) if len(t) else np.nan, test_med=float(np.median(t)) if len(t) else np.nan,
                        test_win=float((t > 0).mean()) if len(t) else np.nan, test_solh=float(t.sum() * SIZE / hrs(TEST)) if len(t) else np.nan,
                        test_top5=float(np.sort(t)[-5:].sum() / t.sum()) if len(t) >= 5 and t.sum() > 0 else np.nan,
                        proxy_n=len(p), proxy_mean=float(p.mean()) if len(p) else np.nan, proxy_solh=float(p.sum() * SIZE / hrs(FWD)) if len(p) else np.nan))
    return out
from multiprocessing import Pool
with Pool(12) as pool: res = [x for part in pool.imap_unordered(job, [(en, ex) for en in ("E_k1", "E_k2", "E_k3", "E_slot") for ex in EXS]) for x in part]
json.dump(res, open(os.path.join(OUT, "h_real.json"), "w"))
ok = [r for r in res if r["n_val"] >= 30 and r["val_mean"] > 0]
ok.sort(key=lambda r: -r["val_solh"])
print(f"\nTOP 15 chosen on VALIDATION by SOL/h (our 0.5 SOL buy; TEST = real place in line at {LAND:.0f} ms on {TEST.sum()} watched forward launches, {hrs(TEST):.1f} h):")
for r in ok[:15]:
    print(f"  {r['entry']:6} exit {r['exit']:20} top {r['q']:.0%} | VAL n={r['n_val']:3} mean {r['val_mean']:+.1%} win {r['val_win']:.0%} {r['val_solh']:+.2f} SOL/h"
          f" | TEST(real) n={r['n_test']:3} mean {r['test_mean']:+.1%} med {r['test_med']:+.1%} win {r['test_win']:.0%} {r['test_solh']:+.2f} SOL/h (top5 {r['test_top5']:.0%})"
          f" | forward proxy n={r['proxy_n']} mean {r['proxy_mean']:+.1%} {r['proxy_solh']:+.2f} SOL/h")
