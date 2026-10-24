#!/usr/bin/env python3
# READ-ONLY, offline: are CWiNFA's picks better than comparable launches, once ITS OWN trades are taken out of the price path?
# Pool = SOL-quoted, non-mayhem launches with a dev buy >= 1 SOL and >= 1 glued bundle tx (the kind it buys), both runs.
# Price path re-simulated on the constant-product curve WITHOUT CWiNFA's trades: spot price at +2 / +5 / +10 / +30 / +60 s
# and the peak within 60 s, relative to the post-bundle price. Plus our guarded quick flip (replay tables) on R2.
import os, sys, json, collections, statistics
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["RP_PHASEA_R2"] = os.path.join(HERE, "phaseA_snap")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
W = "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J"
L = rp.load_launches(); C = json.load(open(os.path.join(HERE, "coll_cw.json")))
ATT = {m for m, v in C.items() if v.get("buy") or v.get("failed")}
T = {x["mint"]: x for x in json.load(open(os.path.join(HERE, "table_slim.json"))) if x["quote_sol"] == 1 and x["mayhem"] == 0}
pool = {m for m, x in T.items() if (x["dev_buy"] or 0) >= 1 and (x["glued_n"] or 0) >= 1} | (ATT & set(T))
byb = collections.defaultdict(set)
for m in pool:
    if m in L: byb[(L[m]["run"], rp.bucket(m))].add(m)
OFF = {"2s": 2, "5s": 5, "10s": 10, "30s": 30, "60s": 60}
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c); g = st["g_end"]
        if g < 1: continue
        V, T_ = tr[g - 1]["vsol"], tr[g - 1]["vtok"]; p_b = V / T_; S = c["slot"]
        res = {}; peak = 1.0; nxt = sorted(OFF.items(), key=lambda kv: kv[1]); j = 0
        for t in tr[g:]:
            el = (t["s"] - S) * rp.SLOT_MS / 1000
            while j < len(nxt) and el >= nxt[j][1]: res[nxt[j][0]] = round((V / T_) / p_b, 4); j += 1
            if j >= len(nxt): break
            if t["user"] == W: continue
            if t["buy"]: d = T_ * t["sol"] // (V + t["sol"]); V += t["sol"]; T_ -= d
            else: so = V * t["tok"] // (T_ + t["tok"]); V -= so; T_ += t["tok"]
            if V >= rp.GRAD_VSOL: break
            peak = max(peak, (V / T_) / p_b)
        while j < len(nxt): res[nxt[j][0]] = round((V / T_) / p_b, 4); j += 1
        res["peak60"] = round(peak, 4); res["att"] = m in ATT; res["run"] = run; res["dep"] = c["user"]
        out[m] = res
    return out
if __name__ == "__main__":
    R = {}
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb)): R.update(o)
    json.dump(R, open(os.path.join(HERE, "picks_vs_pool.json"), "w"))
    A = [v for v in R.values() if v["att"]]; S_ = [v for v in R.values() if not v["att"]]
    deps = {v["dep"] for v in A}; SD = [v for v in S_ if v["dep"] in deps]
    lines = [f"pool (dev >= 1 SOL + glued bundle, SOL-quoted, non-mayhem): {len(R)} launches; its attempts {len(A)}; skipped {len(S_)} (of which by the same deployers {len(SD)})",
             "price vs post-bundle price, CWiNFA's own trades REMOVED from the path (median / mean / share > 1.0):"]
    for k in ("2s", "5s", "10s", "30s", "60s", "peak60"):
        f = lambda g: f"med {statistics.median(x[k] for x in g):.3f} mean {statistics.mean(x[k] for x in g):.3f} up {sum(x[k] > 1 for x in g) / len(g):.0%}"
        lines.append(f"  {k:7} attempted: {f(A)} | skipped pool: {f(S_)} | same deployers skipped: {f(SD)}")
    for run in ("R1", "R2"):
        a = [v for v in A if v["run"] == run]; s = [v for v in S_ if v["run"] == run]
        lines.append(f"  {run}: +2 s attempted med {statistics.median(x['2s'] for x in a):.3f} (n {len(a)}) vs skipped med {statistics.median(x['2s'] for x in s):.3f} (n {len(s)}); "
                     f"+10 s {statistics.median(x['10s'] for x in a):.3f} vs {statistics.median(x['10s'] for x in s):.3f}")
    open(os.path.join(HERE, "picks_vs_pool.txt"), "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
