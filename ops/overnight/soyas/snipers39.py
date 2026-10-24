# which of the Soyas-using top bots are launch SNIPERS? (R3 tapes, local) share of their buys within 0.5 s / 1 s of the token create
import os, sys, json, collections, statistics
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
R = json.load(open("soyas_usage.json")); per = collections.defaultdict(lambda: [0, 0])
for w, c, s in R:
    if c == "Jito": per[w][0] += 1; per[w][1] += "soyas" in s.split("+")
W = {w for w, v in per.items() if v[1] > 0}
L = rp.load_launches(); byb = collections.defaultdict(set)
for m, c in L.items():
    if c["run"] == "R3": byb[("R3", rp.bucket(m))].add(m)
def work(key):
    out = collections.defaultdict(list)
    for m, tr in rp.read_bucket(key[0], key[1], byb[key]).items():
        S0 = L[m]["slot"]
        for t in tr:
            if t["buy"] and t["user"] in W: out[t["user"]].append((t["s"] - S0) * 0.212)
    return out
if __name__ == "__main__":
    A = collections.defaultdict(list)
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=4):
            for k, v in o.items(): A[k] += v
    rows = []
    for w in W:
        v = A.get(w, [])
        if v: rows.append((sum(1 for a in v if a <= 0.5) / len(v), w, len(v), sum(1 for a in v if a <= 1.0) / len(v), statistics.median(v)))
    for s05, w, n, s1, med in sorted(rows, reverse=True):
        print(f"{w} buys {n:5d} | within 0.5 s of create {s05:4.0%} | within 1 s {s1:4.0%} | median age {med:7.1f} s | jito {per[w][0]} soyas {per[w][1]}")
