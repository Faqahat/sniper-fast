#!/usr/bin/env python3
"""Q5/Q1: decode the nonce-account seeds. Nonce accounts are createAccountWithSeed(base=wallet, seed, owner=System); address =
sha256(base || seed || owner). Brute-force seeds 'fbn-<region>-<nn>' over region names to map every sampled nonce account to its
region tag (which send region uses it). Out: x12.txt"""
import sys, hashlib, pickle, itertools, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/exec")
import xlib as X
A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n * 58 + A.index(c)
    b = n.to_bytes(32, "big"); return b
def b58e(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = A[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s
SYS = b58d("11111111111111111111111111111111") if False else bytes(32)
regs = ["fra", "ams", "lon", "nyc", "ny", "chi", "sea", "lax", "tyo", "sgp", "slc", "dal", "mia", "par", "waw", "zrh", "dub", "mad", "mil", "sto", "hel", "vie"] + \
       [f"{p}{k}" for p in ("euw", "eun", "euc", "use", "usw", "usc", "use", "asia", "ase", "asne", "ne", "eu", "us", "ap") for k in range(1, 13)]
seeds = [f"fbn-{r}-{n:02d}" for r in regs for n in range(0, 40)]
x = pickle.load(open(f"{X.R}/ixs.pkl", "rb"))
acc = collections.Counter(v["nonce"] for v in x.values() if v["nonce"])
acc.update({"4KBJQ6yDQPHTWGLVEp8aikUyJA2xCiJKVFBRu4kk5YSP": 0, "8yzgfZptfHPffRh4jKyYapUdBHmAfmWTM7n3ABFNgytk": 0})
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
for base in (X.WAL, X.SIB):
    bb = b58d(base); m = {}
    for sd in seeds:
        m[b58e(hashlib.sha256(bb + sd.encode() + SYS).digest())] = sd
    hits = {a: m[a] for a in acc if a in m}
    P(f"{base[:8]}: {len(hits)} of {len(acc)} sampled nonce accounts decoded")
    for a, sd in sorted(hits.items(), key=lambda kv: kv[1]): P(f"   {sd:14} {a}  (uses in RPC sample: {acc[a]})")
# landed relay per region tag (E2x1 sample)
TX = {t["sig"]: t for t in pickle.load(open(f"{X.R}/tx.pkl", "rb"))}
bb = b58d(X.WAL); m = {b58e(hashlib.sha256(bb + sd.encode() + SYS).digest()): sd for sd in seeds}
c = collections.Counter()
for s, v in x.items():
    if v["nonce"]:
        t = TX.get(s); c[(m.get(v["nonce"], "?").rsplit("-", 1)[0], v["side"], t and t["relay"])] += 1
P("E2x1 RPC sample: (region tag, side, landed relay) counts:")
for k, n in sorted(c.items(), key=lambda kv: -kv[1]): P(f"   {n:4} {k}")
open(f"{X.X}/x12.txt", "w").write("\n".join(out) + "\n")
# region engine vs the buy slot's leader location (leader_geo.json, epoch 1063 IP geo; MEASURED geo, INFERRED routing)
import json
G = {r["pk"]: (r.get("cc"), r.get("city")) for r in json.load(open("/home/moiz/sniper-data/leader_geo.json"))["rows"]}
def area(cc, city):
    if cc is None: return "?"
    if cc in ("US", "CA"): return "N.America"
    if cc in ("NL",): return "NL"
    if cc in ("DE",): return "DE"
    if cc in ("GB", "IE", "FR", "BE", "CH", "AT", "PL", "LT", "CZ", "FI", "SE", "IT", "ES", "LU", "DK", "NO", "RO", "BG", "UA", "HU", "PT", "LV", "EE"): return "EU-other"
    return "Asia/other"
c2 = collections.Counter()
for s, v in x.items():
    if v["nonce"] and v["side"] == "buy":
        t = TX.get(s)
        if not t: continue
        ld, cl = X.leader(t["s"]); cc, city = G.get(ld, (None, None))
        c2[(m.get(v["nonce"], "?").rsplit("-", 1)[0], area(cc, city))] += 1
P("E2x1 sampled BUYS: (engine region tag, leader location) counts:")
for k, n in sorted(c2.items()): P(f"   {n:4} {k}")
open(f"{X.X}/x12.txt", "w").write("\n".join(out) + "\n")
