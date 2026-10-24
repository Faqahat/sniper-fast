# load helpers for copy3 (read-only)
import os, json, gzip, pickle, glob, collections
HERE = os.path.dirname(os.path.abspath(__file__))
W3 = {"Fsb6Ns75": "Fsb6Ns75tgGRom5TJWK7ZA89XLPgCoyuhqeEdLgfbZfy", "pXGQ6J2z": "pXGQ6J2ziRCvmYSLTT55FASf2jSHeCD6gju5xka31yV", "4vw54BmA": "4vw54BmAogeRV3vPKWyFet5yf8DTLcREzdSzx4rw9Ud9"}
def load_tapes():
    T = {}; F = {}
    for f in sorted(glob.glob(os.path.join(HERE, "raw/tapes/*.pkl.gz"))):
        d = pickle.load(gzip.open(f, "rb")); T.update(d["tapes"]); F.update(d["fail"])
    return T, F
def load_launches():
    L = {}
    for tag, run in (("R1", "run_20261021_2207"), ("R2", "run_20261022_1543"), ("R3", "run_20261023_1426")):
        for l in open(f"/home/moiz/sniper-data/collect/{run}/launches.jsonl"):
            try: c = json.loads(l)
            except Exception: continue
            if c["mint"] not in L: c["run"] = tag; L[c["mint"]] = c
    return L
_SS = None
def slot_size(s):
    global _SS
    if _SS is None:
        _SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
        for run in ("R1", "R2", "R3"):
            p = os.path.join(HERE, f"raw/slotmax_{run}.json")
            if os.path.exists(p):
                for k, v in json.load(open(p)).items():
                    k = int(k)
                    if v > _SS.get(k, 0): _SS[k] = v
    return _SS.get(s)
def pkt(t):
    import time
    return time.strftime("%m-%d %H:%M", time.gmtime(t + 18000))
