#!/usr/bin/env python3
# HOW PROS LAND, pass 2 (read-only, local files only). From the x1 compact files (R3 + R4 = 10-23 19:26 -> 10-25 19:02 PKT):
#   1. dumps   = successful bonding-curve sells >= 0.5 SOL (drop = 1 - (vsol_after / vsol_before)^2, constant product)
#   2. followers = every successful buy on the same mint within 3 slots after the latest dump (seller excluded), first 40
#   3. landings  = every tx of a target wallet (wallets.json; failed txs too) on a mint with a dump <= 3 slots before it
# Output: /home/moiz/sniper-data/landing2/reactions.json.gz  {dumps: {key: [...]}, followers: {key: [...]}, landings: [...], blk: {...}}
import json, gzip, glob, bisect, collections, os, time
D = "/home/moiz/sniper-data/landing2"
WAL = json.load(open(f"{D}/wallets.json"))
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
t0 = time.time()
def chunks(kind):
    fs = []
    for r in ("x_r3", "x_r4"): fs += glob.glob(f"{D}/{r}/{kind}_*")
    return sorted(fs, key=lambda f: int(os.path.basename(f).split("_")[1].split(".")[0]))
# block stats: slot -> [max index, txs seen, bt]
BLK = {}
for f in chunks("B"):
    for k, (mx, cnt, bt) in json.load(open(f)).items():
        s = int(k); b = BLK.get(s)
        if b is None: BLK[s] = [mx, cnt, bt]
        else:
            b[0] = max(b[0], mx); b[1] += cnt; b[2] = min(x for x in (b[2], bt) if x is not None) if (b[2] or bt) else None
print(f"blocks {len(BLK)} ({time.time()-t0:.0f}s)", flush=True)
# pass 1: dumps
DUMPS = collections.defaultdict(list)      # mint -> [(s, i, sol, drop, user, sig, signer0, leader-free)]
nT = 0
for f in chunks("T"):
    for l in gzip.open(f, "rt"):
        r = json.loads(l); nT += 1
        if r[6] == 0 and r[7] >= 500_000_000:
            vsol = r[8]; sol = r[7]
            drop = 1.0 - (vsol / (vsol + sol)) ** 2 if vsol > 0 else 0.0
            DUMPS[r[5]].append((r[0], r[1], sol, round(drop, 4), r[4], r[2], r[3]))
for m in DUMPS: DUMPS[m].sort()
KEYS = {m: [(d[0], d[1]) for d in v] for m, v in DUMPS.items()}
print(f"trades {nT}, dumps {sum(len(v) for v in DUMPS.values())} on {len(DUMPS)} mints ({time.time()-t0:.0f}s)", flush=True)
def latest_dump(m, s, i):
    ks = KEYS.get(m)
    if not ks: return None
    j = bisect.bisect_left(ks, (s, i)) - 1
    if j < 0: return None
    d = DUMPS[m][j]
    if s - d[0] > 3: return None
    return d
# pass 2: followers (all buyers)
FOL = collections.defaultdict(list)
for f in chunks("T"):
    for l in gzip.open(f, "rt"):
        r = json.loads(l)
        if r[6] != 1: continue
        d = latest_dump(r[5], r[0], r[1])
        if d is None or r[4] == d[4] or r[3] == d[4]: continue
        k = f"{d[5]}"
        v = FOL[k]
        if len(v) < 60: v.append([r[0], r[1], r[4], r[3], r[7], r[11], r[12], r[13], r[10], r[14], r[15], r[2], r[16]])
for k in FOL: FOL[k] = sorted(FOL[k])[:40]
print(f"dumps with followers {len(FOL)} ({time.time()-t0:.0f}s)", flush=True)
# pass 3: target-wallet landings (failed too)
LAND = []; TOT = collections.defaultdict(collections.Counter)
for f in chunks("W"):
    for l in gzip.open(f, "rt"):
        s, i, sig, sg, err, fee, cup, cul, cu, mints, progs, ixn, tips, sdp = json.loads(l)
        w = sg[0] if sg else None
        if w not in WAL: continue
        ispump = PUMP in progs
        kind = "buy" if any(x.startswith("Buy") for x in ixn) else ("sell" if any(x.startswith("Sell") for x in ixn) else "other")
        TOT[w]["tx"] += 1; TOT[w]["fail"] += err is not None; TOT[w][f"{kind}{'_fail' if err else ''}"] += 1
        if not ispump or kind == "sell" or (kind == "other" and err is None): continue      # failed-early txs (guard before pump) kept as "other"
        best = None
        for m in mints:
            d = latest_dump(m, s, i)
            if d and (best is None or (d[0], d[1]) > (best[0], best[1])): best = d; bm = m
        if best is None: continue
        LAND.append(dict(w=w, s=s, i=i, sig=sig, err=err, fee=fee, cup=cup, cul=cul, cu=cu, mint=bm, tips=tips, sdp=sdp[:8], progs=progs,
                         ixn=ixn[:8], nsig=len(sg), dump=best[5], kind=kind))
print(f"landings {len(LAND)} ({time.time()-t0:.0f}s)", flush=True)
need = {x["dump"] for x in LAND} | set(FOL)
DOUT = {}
for m, v in DUMPS.items():
    for d in v:
        if d[5] in need: DOUT[d[5]] = [d[0], d[1], d[2], d[3], d[4], m, d[6]]
slots = {d[0] for d in DOUT.values()} | {x["s"] for x in LAND} | {r[0] for v in FOL.values() for r in v}
out = dict(dumps=DOUT, followers=FOL, landings=LAND, totals={w: dict(c) for w, c in TOT.items()},
           blk={str(s): BLK[s] for s in slots if s in BLK})
with gzip.open(f"{D}/reactions.json.gz", "wt") as fo: json.dump(out, fo)
print(f"DONE dumps {len(DOUT)} ({time.time()-t0:.0f}s)", flush=True)
