#!/usr/bin/env python3
# How fast does the profitable bot cohort (census consistent winners, R1-defined) react, by trigger type? For each cohort buy
# in R2, the proxy delay (block position x 212 ms) since: the create, the last >=1 SOL sell, the last >=2 SOL buy (by others)
# before it in the same launch (within 10 slots). Where they are slow (>100 ms), a 75 ms bot could be first.
import sys, os, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
import rp
from multiprocessing import Pool
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/dip/cohort_R1.json")))
L = rp.load_launches()
byb = collections.defaultdict(set)
for m, c in L.items():
    if c["run"] == "R2" and rp.bucket(m) % 4 == 0: byb[rp.bucket(m)].add(m)
def arr(s, i): return s * rp.SLOT_MS + i / max(SS.get(s, 400), i + 1) * rp.SLOT_MS
def work(b):
    out = collections.defaultdict(list)
    for m, tr in rp.read_bucket("R2", b, byb[b]).items():
        c = L[m]; S = c["slot"]; a_c = arr(S, c.get("idx") or 0)
        last_sell = None; last_bbuy = None
        for t in tr:
            a = arr(t["s"], t["i"])
            if t["buy"] and t["user"] in COH:
                if t["s"] - S <= 10: out["since_create"].append(a - a_c)
                if last_sell and t["s"] - last_sell[1] <= 10: out["since_big_sell"].append(a - last_sell[0])
                if last_bbuy and t["s"] - last_bbuy[1] <= 10 and last_bbuy[2] != t["user"]: out["since_big_buy"].append(a - last_bbuy[0])
            if not t["buy"] and t["sol"] >= 1e9: last_sell = (a, t["s"])
            if t["buy"] and t["sol"] >= 2e9 and t["user"] not in COH: last_bbuy = (a, t["s"], t["user"])
    return out
if __name__ == "__main__":
    R = collections.defaultdict(list)
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb)):
            for k, v in o.items(): R[k] += v
    for k, v in R.items():
        v.sort(); n = len(v)
        print(f"{k:15s} n {n:6d} | proxy delay ms p10 {v[n // 10]:6.1f} p25 {v[n // 4]:6.1f} median {v[n // 2]:6.1f} p75 {v[3 * n // 4]:6.1f} | share > 75 ms {sum(1 for x in v if x > 75) / n:.0%} | share > 150 ms {sum(1 for x in v if x > 150) / n:.0%}")
