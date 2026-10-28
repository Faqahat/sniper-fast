import numpy as np, time
OUT = "/home/moiz/sniper-data/e2x1_dissect/select"
SMS = 212.0
pkt = lambda t: time.strftime("%m-%d %H:%M:%S", time.gmtime(int(t) + 18000))
def load():
    Z = np.load(f"{OUT}/tape.npz")
    D = {k: Z[k] for k in Z.files}
    m = D["mint"]; um, st = np.unique(m, return_index=True); en = np.append(st[1:], len(m))
    D["span_m"], D["span_a"], D["span_b"] = um, st, en
    return D
def span(D, mint):
    k = np.searchsorted(D["span_m"], mint); return int(D["span_a"][k]), int(D["span_b"][k])

import json, functools
TP = "/home/moiz/sniper-data/haqqml/fresh/tape"
@functools.lru_cache(None)
def names():
    return json.load(open(f"{TP}/mints.json")), json.load(open(f"{TP}/users.json"))
