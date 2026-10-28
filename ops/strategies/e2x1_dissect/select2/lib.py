"""select2 shared helpers (read-only on other agents' data)."""
import numpy as np, json, time, functools
OUT = "/home/moiz/sniper-data/e2x1_dissect/select2"
SCR = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/e2x1_select2"
SEL = "/home/moiz/sniper-data/e2x1_dissect/select"
TP = "/home/moiz/sniper-data/haqqml/fresh/tape"
W = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"
SIB = "Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ"
COPIERS = ["4mYySb7Z74EK9c6AzSmRRbsd5NjRKeU2yjMF6nfz8ctD", "Hj4uACn8Jp2QvbMFhkhWWCdHPzC2SEXg7fhpZayYVcyL",
           "2QGfyorL", "8T4XX", "6nH3j"]   # last three: prefixes from select/REPORT (resolved in s2)
SMS = 212.0
pkt = lambda t: time.strftime("%m-%d %H:%M:%S", time.gmtime(int(t) + 18000))
@functools.lru_cache(None)
def names():
    return json.load(open(f"{SCR}/mints.json")), json.load(open(f"{SCR}/users.json"))   # snapshot taken by t1 (source tape gets extended)
def load():
    Z = np.load(f"{SCR}/tape.npz")
    D = {k: Z[k] for k in Z.files}
    m = D["mint"]; um, st = np.unique(m, return_index=True); en = np.append(st[1:], len(m))
    D["span_m"], D["span_a"], D["span_b"] = um, st, en
    return D
