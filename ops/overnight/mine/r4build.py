#!/usr/bin/env python3
# SECOND TEST DAY: R4 = live raw recording run_20261024_1425 (10-24 19:25 PKT ->). Builds SOL-curve tapes from raw trade events, then the SAME
# features/labels as build.py, with wallet reputation from R1+R2+R3 only (no look-ahead). Output mine_r4.pkl.
import os, sys, json, glob, gzip, base64, collections, pickle, numpy as np
sys.argv = ["build.py"]; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as Bd                     # reuses features/labels code (its module-level setup loads R1–R3 launches and REP)
from multiprocessing import Pool
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
def parse(f):
    out = collections.defaultdict(list)
    try:
        for line in gzip.open(f, "rt"):
            if "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P" not in line: continue
            try: r = json.loads(line)
            except Exception: continue
            if str(r.get("err")) not in ("None", "null"): continue
            for j, e in enumerate(r.get("ev") or []):
                try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
                except Exception: continue
                if raw[:8] != TD or len(raw) < 129: continue
                vsol = int.from_bytes(raw[97:105], "little")
                if vsol == 0: continue
                out[Bd_b58(raw[8:40])].append(dict(s=int(r["s"]), i=int(r["i"]), j=j, bt=int(r.get("bt") or 0), sig=r["sig"], user=Bd_b58(raw[57:89]), buy=raw[56] == 1,
                                                    sol=int.from_bytes(raw[40:48], "little"), tok=int.from_bytes(raw[48:56], "little"), vsol=vsol, vtok=int.from_bytes(raw[105:113], "little")))
    except (EOFError, OSError): pass
    return out
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def Bd_b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
if __name__ == "__main__":
    RUN = "/home/moiz/sniper-data/collect/run_20261024_1425"
    files = sorted(glob.glob(f"{RUN}/txs/*.jsonl.gz"))[:-1]          # skip the file still being written
    L4 = {}
    for l in open(f"{RUN}/launches.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        c["run"] = "R4"; L4[c["mint"]] = c
    T = collections.defaultdict(list)
    with Pool(8) as p:
        for o in p.imap_unordered(parse, files):
            for m, v in o.items():
                if m in L4: T[m] += v
    T = {m: sorted(v, key=lambda t: (t["s"], t["i"], t["j"])) for m, v in T.items()}
    print("R4 files", len(files), "| SOL-curve tokens with trades", len(T), flush=True)
    # reputation from R1+R2+R3 (same rule as rep.py)
    import gzip as gz
    HRS = {"R1": 14.88, "R2": 21.79, "R3": 24.0}; S = collections.defaultdict(lambda: [0, 0.0, 0])
    for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
        for line in gz.open(f, "rt"):
            r = json.loads(line)
            if r[16] or not r[13]: continue
            s = S[r[0]]; s[0] += 1; s[1] += r[11]; s[2] += r[11] > 0
    rep4 = {u: (v[1] / sum(HRS.values()) * 24, v[2] / v[0], v[0]) for u, v in S.items() if v[0] >= 10}
    Bd.REP["for_R3"] = rep4; Bd.L.update(L4)
    keys = collections.defaultdict(set)
    for m in T: keys[("R4", hash(m) % 64)].add(m)
    Bd.byb.clear(); Bd.byb.update(keys)
    Bd.rp.read_bucket = lambda run, b, ms_: {m: T[m] for m in ms_}
    X = []; Y = []; M = []
    for k in sorted(keys):
        x, y, m = Bd.work(k)
        if len(x): X.append(x); Y.append(y); M += m
    X = np.concatenate(X); Y = np.concatenate(Y)
    hrs = (max(m[3] for m in M) - min(m[3] for m in M)) / 3600
    pickle.dump(dict(X=X, Y=Y, M=M, F=Bd.FEAT, H=Bd.HOLDS, hours=hrs), open("mine_r4.pkl", "wb"))
    print("R4 rows", len(X), "| hours covered", round(hrs, 1))
