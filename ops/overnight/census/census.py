#!/usr/bin/env python3
# READ-ONLY wallet census over R1 (phaseA) + R2 (phaseA_dry): every wallet's bonding-curve PnL per launch.
# Per (wallet, mint): SOL spent on buys incl. pump fees, SOL received from sells net of fees, tx fees + tips once per
# signature, unsold tokens marked at the last curve price (net of the sell fee; flagged if the curve completed),
# first-buy delay (slots after the create), hold (slots first buy -> last sell), first-buy SOL.
# Standard SOL curves only (no mayhem / odd reserves). -> census/wm.jsonl.gz (one row per wallet-mint)
import sys, os, json, gzip, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
import rp
from multiprocessing import Pool
L = rp.load_launches()
byb = collections.defaultdict(set)
for m, c in L.items(): byb[(c["run"], rp.bucket(m))].add(m)
OUT = "/home/moiz/sniper/ops/overnight/census/parts"
os.makedirs(OUT, exist_ok=True)
def work(key):
    run, b = key; fn = f"{OUT}/{run}_{b:03d}.jsonl.gz"
    if os.path.exists(fn): return 0
    tra = rp.read_bucket(run, b, byb[key]); rows = []
    for m, tr in tra.items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]
        if c.get("mayhem"): continue
        S = c["slot"]; last = tr[-1]; p_last = last["vsol"] / last["vtok"] if last["vtok"] else 0
        done = last["vsol"] >= 110e9
        W = {}; seen_sig = set()
        for k, t in enumerate(tr):
            u = t["user"]; fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
            w = W.get(u)
            if w is None: w = W[u] = dict(spent=0, got=0, cost=0, tok=0, nb=0, ns=0, fb_s=None, fb_k=None, fb_sol=0, ls_s=None, fb_bt=None)
            if t["sig"] not in seen_sig:
                seen_sig.add(t["sig"]); w["cost"] += (t.get("fee") or 0) + int((t.get("tips") or 0) if isinstance(t.get("tips"), (int, float)) else 0)
            if t["buy"]:
                w["spent"] += t["sol"] * (1 + fr); w["tok"] += t["tok"]; w["nb"] += 1
                if w["fb_s"] is None: w["fb_s"] = t["s"] - S; w["fb_k"] = k; w["fb_sol"] = t["sol"]; w["fb_bt"] = t["bt"]
            else:
                w["got"] += t["sol"] * (1 - fr); w["tok"] -= t["tok"]; w["ns"] += 1; w["ls_s"] = t["s"] - S
        for u, w in W.items():
            if w["nb"] == 0: continue                      # sells only (tokens from elsewhere): skip
            rem = max(w["tok"], 0); mark = rem * p_last * (1 - 0.0125)
            pnl = (w["got"] + mark - w["spent"] - w["cost"]) / 1e9
            rows.append([u, m, run, c["bt"], w["fb_s"], w["fb_k"], round(w["fb_sol"] / 1e9, 4), round(w["spent"] / 1e9, 4), round(w["got"] / 1e9, 4),
                         round(mark / 1e9, 4), round(w["cost"] / 1e9, 5), round(pnl, 4), w["nb"], w["ns"], w["ls_s"], int(done), int(rem > 0)])
    with gzip.open(fn + ".tmp", "wt") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
    os.rename(fn + ".tmp", fn)
    return len(rows)
if __name__ == "__main__":
    n = 0
    with Pool(8) as p:
        for x in p.imap_unordered(work, sorted(byb), chunksize=2): n += x
    print("rows", n)
