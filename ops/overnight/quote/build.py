#!/usr/bin/env python3
# Quote-curve tapes (R2+R3) from raw lines, with a per-token SOL calibration. Event fields: tok @48, is_buy @56, user @57, vtok after @105.
# Calibration: buys where the signer paid SOL and swapped it into the quote token in the same tx -> u = SOL / (1/vtok_after - 1/vtok_before)
# (pump fee 1.25% removed). SOL-equivalent quote reserves V = u / vtok. Tokens without a stable calibration are dropped.
import json, glob, base64, pickle, gzip, collections, statistics
from multiprocessing import Pool
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238]); B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
QM = set(l.strip() for l in open("qmints.txt") if l.strip())
SWAPX = ("Swap", "Route", "WrapSol", "Jupiter", "SwapV2", "SwapV3", "SwapTob", "SwapByDex")
def parse(f):
    run = "R2" if "20261022" in f else "R3"; out = collections.defaultdict(list)
    for line in open(f):
        try: r = json.loads(line)
        except Exception: continue
        if str(r.get("err")) not in ("None", "null"): continue
        sg = (r.get("signers") or [None])[0]; sd = dict((a, d) for a, d in (r.get("sd") or []))
        ixn = r.get("ixn") or []; swap = any(any(x.startswith(p) or p in x for p in SWAPX) for x in ixn)
        evs = []
        for j, e in enumerate(r.get("ev") or []):
            try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
            except Exception: continue
            if raw[:8] == TD and len(raw) >= 129:
                m = b58(raw[8:40])
                if m in QM: evs.append((m, j, raw))
        for m, j, raw in evs:
            out[m].append((int(r["s"]), int(r["i"]), j, int(r.get("bt") or 0), r["sig"], b58(raw[57:89]), raw[56] == 1, int.from_bytes(raw[48:56], "little"),
                           int.from_bytes(raw[105:113], "little"), sg, sd.get(sg, 0), int(r.get("fee") or 0), swap and len(evs) == 1, run))
    return out
if __name__ == "__main__":
    T = collections.defaultdict(list)
    with Pool(8) as p:
        for o in p.imap_unordered(parse, sorted(glob.glob("raw/*.jsonl"))):
            for m, v in o.items(): T[m] += v
    tapes = {}; cal_ok = 0
    for m, v in T.items():
        v = sorted(set(v), key=lambda x: (x[0], x[1], x[2]))
        if len(v) < 5: continue
        us = []
        for k in range(1, len(v)):
            t = v[k]; vb = v[k - 1][8]; va = t[8]
            if t[6] and t[12] and t[5] == t[9] and va < vb:
                paid = (-t[10] - t[11]) / 1e9
                if paid >= 0.02: us.append(paid / 1.0125 / (1 / va - 1 / vb))
        if len(us) < 2: continue
        us.sort(); u = us[len(us) // 2]
        if us[len(us) // 4] < 0.7 * u or us[3 * len(us) // 4] > 1.3 * u: continue
        cal_ok += 1
        tapes[m] = dict(u=u, n_cal=len(us), rows=[dict(s=x[0], i=x[1], bt=x[3], sig=x[4], user=x[5], buy=x[6], tok=x[7], vtok=x[8], run=x[13]) for x in v])
    pickle.dump(tapes, gzip.open("qtapes.pkl.gz", "wb"))
    print(f"quote-curve tokens with trades: {len(T)} | calibrated (stable SOL value): {cal_ok}")
    v0 = sorted(t["u"] / 1.073e15 for t in tapes.values())
    print("implied starting SOL-equivalent reserves (u / 1.073e15) p10/p50/p90:", [round(v0[int(len(v0) * p)], 1) for p in (0.1, 0.5, 0.9)])
