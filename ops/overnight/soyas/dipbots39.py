# which Soyas-using top bots play OUR strategy (buy right after a >= 1 SOL dump on a young token, quick exit)? R3 tapes, local.
import os, sys, json, collections, statistics
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def arr(t): return t["s"] * 212.0 + t["i"] / max(SS.get(t["s"], 400), t["i"] + 1) * 212.0
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
        for k, t in enumerate(tr):
            if not t["buy"] or t["user"] not in W: continue
            dump = None
            for j in range(k - 1, max(-1, k - 6), -1):                       # a >= 1 SOL sell among the last 5 trades within 300 ms
                x = tr[j]
                if arr(t) - arr(x) > 300: break
                if not x["buy"] and x["sol"] >= 1e9: dump = x; break
            ks = next((j for j in range(k + 1, len(tr)) if tr[j]["user"] == t["user"] and not tr[j]["buy"]), None)
            out[t["user"]].append(((t["s"] - S0) * 0.212, dump is not None, arr(t) - arr(dump) if dump else None, (tr[ks]["s"] - t["s"]) * 0.212 if ks else None))
    return out
if __name__ == "__main__":
    A = collections.defaultdict(list)
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=4):
            for k, v in o.items(): A[k] += v
    med = lambda v: statistics.median(v) if v else float("nan")
    rows = []
    for w in W:
        v = A.get(w, [])
        if not v: continue
        d = [x for x in v if x[1]]
        rows.append((len(d) / len(v), w, len(v), med([x[2] for x in d]), med([x[0] for x in d]), med([x[3] for x in d if x[3] is not None])))
    print("wallet | buys | share right after a >=1 SOL dump | delay after dump (ms) | token age at those buys (s) | hold (s) | soyas/jito")
    for share, w, n, dl, age, hold in sorted(rows, reverse=True):
        print(f"{w} {n:5d} | dip {share:4.0%} | {dl:5.0f} ms | age {age:6.1f} s | hold {hold:5.1f} s | {per[w][1]}/{per[w][0]}")
