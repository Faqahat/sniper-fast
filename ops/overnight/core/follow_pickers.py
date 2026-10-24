#!/usr/bin/env python3
# FOLLOW the picker wallets (tradable): our 0.5 SOL buy lands right after the leader's buy + D other trades (D = 1 or 3:
# our reaction ~ seeing its tx then landing ~75 ms later), then hold 10 / 30 / 60 / 120 s or sell right after the
# leader's first sell (+1 trade). Exact curve replay, our costs. Leader's own trades stay in the path.
import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches()
AT = collections.defaultdict(dict)
for f in ("attempts_pick.json", "attempts_top8.json"):
    for m, v in json.load(open(f)).items(): AT[m].update(v)
FULL = {}
for f in ("/home/moiz/sniper/ops/overnight/wallets/wallets.json",):
    W = json.load(open(f)); items = W["wallets"] if "wallets" in W else [v for v in W.values() if isinstance(v, dict) and "w" in v]
    for x in items: FULL[x["w"][:6]] = x["w"]
FULL.setdefault("4Yy3xB", "4Yy3xBZnJfhkmFAcV6hgdjWgkkc9oCoWEtcUiXNq5AeY")
WAL = ["2maW7x", "4Yy3xB", "retAum", "FYHggF", "HnFPB3", "6Kj5Ch", "FeCAXC", "A21wCG", "3yrJE1", "5g8bvi"]
todo = [(m, w) for m, v in AT.items() for w in v if w in WAL and v[w][0] == 1 and m in L and "InitializeMayhemState" not in (L[m].get("ixn") or [])]
byb = collections.defaultdict(set)
for m, w in todo: byb[(L[m]["run"], rp.bucket(m))].add(m)
HOLDS = {"h10": 47, "h30": 141, "h60": 283, "h120": 566}
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); out = []
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        for w in WAL:
            if w not in AT.get(m, {}) or not AT[m][w][0]: continue
            full = FULL.get(w)
            kb = next((k for k, t in enumerate(tr) if t["buy"] and t["user"] == full), None)
            if kb is None: continue
            ks = next((k for k, t in enumerate(tr) if k > kb and not t["buy"] and t["user"] == full), None)
            r = dict(m=m, w=w, run=run, bt=c["bt"], res={})
            for D in (1, 3):
                ib = kb + 1 + D
                if ib > len(tr): continue
                rules = [rp.R(k, [(1.0, ("slot", v))], v * 0.22 + 2) for k, v in HOLDS.items()]
                o = rp.sim(tr, c, st, ib, 0.5, rules, fill_pen=0.015)
                if not o: continue
                for k in HOLDS: r["res"][f"D{D}_{k}"] = o[k]["pnl"]
                if ks is not None and ks + 1 >= ib:
                    # sell right after the leader's first sell + 1 trade
                    r["res"][f"D{D}_mirror"] = rp.flip(tr, ib, min(len(tr), ks + 2), 0.5)
            out.append(r)
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    json.dump(res, open("follow_res.json", "w"))
    cols = [f"D{D}_{k}" for D in (1, 3) for k in list(HOLDS) + ["mirror"]]
    print(f"{'leader':7} {'n':>4} | " + " ".join(f"{c:>13}" for c in cols))
    for w in WAL:
        v = [r for r in res if r["w"] == w]
        if not v: continue
        line = []
        for c in cols:
            a = [r["res"][c] for r in v if c in r["res"] and r["run"] == "R1"]; b = [r["res"][c] for r in v if c in r["res"] and r["run"] == "R2"]
            line.append(f"{sum(a):+5.1f}/{sum(b):+5.1f}")
        print(f"{w:7} {len(v):4} | " + " ".join(f"{x:>13}" for x in line))
    print("(cells: total SOL at 0.5 SOL per follow, old run R1 / replay run R2)")
