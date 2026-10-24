#!/usr/bin/env python3
# Claim 4: "HkQ7hMjy reacts ~8 ms slower to routed triggers (36.6 vs 44.2 ms median, n 58 / 80)".
# (1) reproduce on the claim's set (trig_sigs.jsonl src=all, labels = RPC truth in trig_tx.jsonl);
# (2) bootstrap / permutation of the median difference;
# (3) confounders: trigger slot position (a SAME-SLOT follower of a trigger at position p can only show delays < (1-p) x 212 ms),
#     block size, age, sell size; stratified and regression-adjusted differences;
# (4) the same on ALL 44.5k triggers (trig_sigs_all.jsonl; label = truth if fetched, else direct_rule.py flag), same-slot and
#     same-or-next-slot. Local files only.
import json, collections, statistics, random, math
import numpy as np
SH = "/home/moiz/sniper/ops/overnight/dipshadow"
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
TX = {}
for l in open(f"{SH}/trig_tx.jsonl"):
    r = json.loads(l); TX[r["sig"]] = r["kind"]
FL = json.load(open("/home/moiz/sniper/ops/overnight/verify_dip/v2_snap/direct_flags_prelim.json"))
HK = "HkQ7hMjy"
def hk(e, same_slot=True):
    for x in e.get("fol", []):
        if x[0] == HK and x[1] == 1 and (x[4] == 0 or (not same_slot and x[4] <= 1)): return x[3]
    return None
def rows(EV, label, same_slot=True):
    out = []
    for e in EV:
        lab = label(e)
        if lab is None: continue
        d = hk(e, same_slot)
        out.append(dict(direct=lab, d=d, pos=e.get("slotpos"), ss=SS.get(e["s"], 400), age=e["age"], sol=e["sol"] / 1e9, nfol=len(e.get("fol", []))))
    return out
def boot_med_diff(a, b, n=4000, seed=7):
    rnd = random.Random(seed); out = []
    for _ in range(n):
        x = [rnd.choice(a) for _ in a]; y = [rnd.choice(b) for _ in b]
        out.append(statistics.median(y) - statistics.median(x))
    out.sort(); return out[int(0.025 * n)], out[int(0.975 * n)], sum(1 for v in out if v <= 0) / n
def perm_p(a, b, n=4000, seed=8):
    rnd = random.Random(seed); obs = statistics.median(b) - statistics.median(a); z = a + b; k = 0
    for _ in range(n):
        rnd.shuffle(z); x, y = z[:len(a)], z[len(a):]
        if abs(statistics.median(y) - statistics.median(x)) >= abs(obs): k += 1
    return k / n
def report(R, name):
    D = [r for r in R if r["direct"] == 1]; T = [r for r in R if r["direct"] == 0]
    dd = [r["d"] for r in D if r["d"] is not None]; dr = [r["d"] for r in T if r["d"] is not None]
    print(f"\n== {name}: triggers direct {len(D)} routed {len(T)} | HkQ7 same-slot buys: direct {len(dd)} ({len(dd) / max(len(D), 1):.1%}) routed {len(dr)} ({len(dr) / max(len(T), 1):.1%})")
    if len(dd) < 5 or len(dr) < 5: return
    lo, hi, pneg = boot_med_diff(dd, dr)
    print(f"   median delay direct {statistics.median(dd):.1f} ms, routed {statistics.median(dr):.1f} ms, diff {statistics.median(dr) - statistics.median(dd):+.1f}"
          f" | bootstrap 95% [{lo:+.1f}, {hi:+.1f}], P(diff<=0) {pneg:.3f} | permutation p {perm_p(dd, dr):.3f} | means {statistics.mean(dd):.1f} vs {statistics.mean(dr):.1f}")
    # confounders: where the trigger sits in its block, block size, age, size (all triggers, and those HkQ7 followed)
    for k in ("pos", "ss", "age", "sol"):
        a = [r[k] for r in D if r[k] is not None]; b = [r[k] for r in T if r[k] is not None]
        a2 = [r[k] for r in D if r["d"] is not None and r[k] is not None]; b2 = [r[k] for r in T if r["d"] is not None and r[k] is not None]
        print(f"   {k:4s}: all triggers median direct {statistics.median(a):8.3f} routed {statistics.median(b):8.3f} | HkQ7-followed direct {statistics.median(a2):8.3f} routed {statistics.median(b2):8.3f}")
    # censoring window: a same-slot buy can only show delay < (1 - pos) x 212
    W = lambda r: (1 - r["pos"]) * 212
    for lo_, hi_ in ((0, 0.25), (0.25, 0.5), (0.5, 1.01)):
        a = [r["d"] for r in D if r["d"] is not None and lo_ <= r["pos"] < hi_]; b = [r["d"] for r in T if r["d"] is not None and lo_ <= r["pos"] < hi_]
        if len(a) >= 5 and len(b) >= 5:
            print(f"   trigger slot position {lo_:.2f}-{hi_:.2f}: direct n {len(a):4d} median {statistics.median(a):5.1f} | routed n {len(b):4d} median {statistics.median(b):5.1f} | diff {statistics.median(b) - statistics.median(a):+5.1f}")
    # regression (OLS on delay, and on log delay) with controls
    X = []; y = []; yl = []
    for r in D + T:
        if r["d"] is None or r["pos"] is None: continue
        X.append([1.0, 1.0 - r["direct"], r["pos"], math.log(r["ss"]), r["age"] / 60, math.log(r["sol"])]); y.append(r["d"]); yl.append(math.log(max(r["d"], 0.5)))
    X = np.array(X); y = np.array(y); yl = np.array(yl)
    for nm, Y in (("delay ms", y), ("log delay", yl)):
        b, *_ = np.linalg.lstsq(X, Y, rcond=None); res = Y - X @ b; s2 = res @ res / (len(Y) - X.shape[1]); se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
        print(f"   OLS {nm}: routed coef {b[1]:+.3f} (se {se[1]:.3f}) | slotpos {b[2]:+.2f} | log blocksize {b[3]:+.2f} | age/min {b[4]:+.2f} | log sell {b[5]:+.2f}  (n {len(Y)})")
    # unadjusted but uncensored-ish: only triggers in the first quarter of their block (window >= 159 ms)
if __name__ == "__main__":
    EV = [json.loads(l) for l in open(f"{SH}/trig_sigs.jsonl")]
    ALLS = [e for e in EV if e["src"] == "all" and e.get("sig") in TX and TX[e["sig"]] in ("top", "routed")]
    report(rows(ALLS, lambda e: 1 if TX[e["sig"]] == "top" else 0), "claim set (trig_sigs.jsonl src=all, RPC truth)")
    EA = [json.loads(l) for l in open(f"{SH}/trig_sigs_all.jsonl")]
    lab = lambda e: (1 if TX[e["sig"]] == "top" else 0) if e.get("sig") in TX and TX[e["sig"]] in ("top", "routed") else FL.get(f'{e["m"]}|{e["age"]}')
    report(rows(EA, lab), "ALL triggers (trig_sigs_all.jsonl, truth else rule), same slot")
    report(rows(EA, lab, same_slot=False), "ALL triggers, same or next slot")
    # all fast backrunners, not only HkQ7: first same-slot buy by ANY wallet (the claim's 33 vs 40 ms), stratified by position
    R = []
    for e in EA:
        l_ = lab(e)
        if l_ is None: continue
        f = next((x for x in e.get("fol", []) if x[1] == 1), None)
        if f and f[4] == 0: R.append((l_, f[3], e.get("slotpos")))
    print("\n== first same-slot buy by ANY wallet, ALL triggers, by trigger slot position:")
    for lo_, hi_ in ((0, 0.25), (0.25, 0.5), (0.5, 1.01)):
        a = [d for l_, d, p in R if l_ == 1 and lo_ <= p < hi_]; b = [d for l_, d, p in R if l_ == 0 and lo_ <= p < hi_]
        print(f"   position {lo_:.2f}-{hi_:.2f}: direct n {len(a):5d} median {statistics.median(a):5.1f} | routed n {len(b):5d} median {statistics.median(b):5.1f}")
