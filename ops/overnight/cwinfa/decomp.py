#!/usr/bin/env python3
# READ-ONLY, offline: is the early rise on CWiNFA's picks broad (generic flow) or made by fast sniper bots?
# Pool = SOL-quoted non-mayhem launches with dev buy >= 1 SOL + a glued bundle (the kind it buys), both runs.
# Price path vs the post-bundle price, re-simulated on the constant-product curve after removing, from the bundle on:
#   (0) nothing   (1) CWiNFA   (2) CWiNFA + all fast sniper wallets (fast_snipers.json)   (3) (2) + the top-10 most frequent
#   after-us buyers of our CWiNFA-copy fills (after_us_top10.json, written by rescore.py).
# A removed wallet loses all its trades after the bundle (its later sells too: it never bought). Insiders are never removed.
import os, sys, json, collections, statistics
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["RP_PHASEA_R2"] = os.path.join(HERE, "phaseA_snap")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
W = "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J"
L = rp.load_launches(); C = json.load(open(os.path.join(HERE, "coll_cw.json")))
ATT = {m for m, v in C.items() if v.get("buy") or v.get("failed")}
FAST = set(json.load(open(os.path.join(HERE, "fast_snipers.json"))))
TOP = set(json.load(open(os.path.join(HERE, "after_us_top10.json")))) if os.path.exists(os.path.join(HERE, "after_us_top10.json")) else set()
T = {x["mint"]: x for x in json.load(open(os.path.join(HERE, "table_slim.json"))) if x["quote_sol"] == 1 and x["mayhem"] == 0}
pool = {m for m, x in T.items() if (x["dev_buy"] or 0) >= 1 and (x["glued_n"] or 0) >= 1} | (ATT & set(T))
byb = collections.defaultdict(set)
for m in pool:
    if m in L: byb[(L[m]["run"], rp.bucket(m))].add(m)
OFF = (("2s", 2), ("5s", 5), ("10s", 10), ("30s", 30))
SETS = {"none": set(), "CWiNFA": {W}, "CWiNFA+fast": {W} | FAST, "CWiNFA+fast+top10": {W} | FAST | TOP}
def path(tr, g, S, rm, ins):
    V, T_ = tr[g - 1]["vsol"], tr[g - 1]["vtok"]; p_b = V / T_; res = {}; j = 0; nb = 0; nbsol = 0.0
    for t in tr[g:]:
        el = (t["s"] - S) * rp.SLOT_MS / 1000
        while j < len(OFF) and el >= OFF[j][1]: res[OFF[j][0]] = (V / T_) / p_b; j += 1
        if j >= len(OFF): break
        if t["user"] in rm and t["user"] not in ins: continue
        if t["buy"]:
            d = T_ * t["sol"] // (V + t["sol"]); V += t["sol"]; T_ -= d
            if el < 10 and t["user"] not in ins: nb += 1; nbsol += t["sol"] / 1e9
        else: so = V * t["tok"] // (T_ + t["tok"]); V -= so; T_ += t["tok"]
        if V >= rp.GRAD_VSOL: break
    while j < len(OFF): res[OFF[j][0]] = (V / T_) / p_b; j += 1
    res["buys10"] = nb; res["sol10"] = nbsol
    return res
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c); g = st["g_end"]
        if g < 1: continue
        out[m] = dict(att=m in ATT, run=run, dep=c["user"], **{k: path(tr, g, c["slot"], rm, st["insiders"]) for k, rm in SETS.items()})
    return out
if __name__ == "__main__":
    R = {}
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb)): R.update(o)
    json.dump(R, open(os.path.join(HERE, "decomp.json"), "w"))
    A = [v for v in R.values() if v["att"]]; S_ = [v for v in R.values() if not v["att"]]
    deps = {v["dep"] for v in A}; SD = [v for v in S_ if v["dep"] in deps]
    lines = [f"pool: {len(R)} launches (its attempts {len(A)}, skipped {len(S_)}, same deployers skipped {len(SD)}); fast sniper wallets removed: {len(FAST)}; top-10 after-us buyers: {len(TOP)}",
             "median price vs post-bundle price (share above 1.0) | non-insider buys in the first 10 s (median count / SOL):"]
    for k in SETS:
        for off, _ in OFF:
            f = lambda g: f"{statistics.median(x[k][off] for x in g):.3f} ({sum(x[k][off] > 1 for x in g) / len(g):.0%})"
            lines.append(f"  removed {k:18} +{off:3}: attempted {f(A)} | skipped pool {f(S_)} | same deployers skipped {f(SD)}")
        lines.append(f"  removed {k:18} buys in first 10 s: attempted {statistics.median(x[k]['buys10'] for x in A)} / {statistics.median(x[k]['sol10'] for x in A):.2f} SOL | skipped pool {statistics.median(x[k]['buys10'] for x in S_)} / {statistics.median(x[k]['sol10'] for x in S_):.2f} SOL")
    for run in ("R1", "R2"):
        a = [v for v in A if v["run"] == run]; s = [v for v in S_ if v["run"] == run]
        lines.append(f"  {run}: +10 s with CWiNFA+fast+top10 removed: attempted {statistics.median(x['CWiNFA+fast+top10']['10s'] for x in a):.3f} vs skipped {statistics.median(x['CWiNFA+fast+top10']['10s'] for x in s):.3f}")
    open(os.path.join(HERE, "decomp.txt"), "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
