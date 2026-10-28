#!/usr/bin/env python3
"""select2 t2: one pass over the raw recordings -> compact tx-shape record per successful pump.fun CURVE tx (progs has 6EF8):
sigh (blake2b-8 of the signature, same as the haqqml tape), slot, idx, cup, cul, cu, fee, nsign, ntips, tip_amt, relay (tipmap),
route (sorted set of non-standard program ids, dictionary id), ixh (hash of the ixn name tuple), flags.
Also per-slot block size (max tx index of ANY recorded line + 1) for the chain clock. Output: SCR/shape/<file>.npz, merged in t3."""
import sys, os, re, json, hashlib, subprocess, numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select2"); from lib import *
TIP = json.load(open("/home/moiz/sniper-data/e2x1_dissect/recon/tipmap.json"))
RELAYS = sorted(set(TIP.values())); RID = {r: i + 1 for i, r in enumerate(RELAYS)}
STD = {"11111111111111111111111111111111", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
       "ComputeBudget111111111111111111111111111111", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
       "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e"}
R = re.compile(rb'^\{"s":(\d+),"i":(\d+),"bt":(\d+),"sig":"([1-9A-HJ-NP-Za-km-z]+)","err":(null|\{)')
DT = np.dtype([("sigh", "<u8"), ("s", "<u4"), ("i", "<u2"), ("cup", "<u4"), ("cul", "<u4"), ("cu", "<u4"), ("fee", "<u4"), ("tip", "<u4"),
               ("route", "<u2"), ("ixh", "<u4"), ("relay", "u1"), ("nsign", "u1"), ("ntips", "u1"), ("flags", "u1")])
def sigh(sig): return int.from_bytes(hashlib.blake2b(sig.encode(), digest_size=8).digest(), "little")
def one(f):
    out = f"{SCR}/shape/{os.path.basename(f)}.npz"
    if os.path.exists(out): return f
    p = subprocess.Popen(["zcat", f], stdout=subprocess.PIPE, bufsize=1 << 20)
    rows = []; routes = {}; blocks = {}
    for ln in p.stdout:
        m = R.match(ln)
        if not m: continue
        s = int(m.group(1)); i = int(m.group(2))
        if s not in blocks or i > blocks[s]: blocks[s] = i
        if m.group(5) != b"null": continue
        if b"6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P" not in ln: continue
        try: r = json.loads(ln)
        except Exception: continue
        progs = r.get("progs") or []
        if "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P" not in progs: continue
        ixn = r.get("ixn") or []
        rt = ",".join(sorted(x for x in progs if x not in STD))
        rid = routes.setdefault(rt, len(routes))
        tips = r.get("tips") or []; tamt = sum(int(t[1]) for t in tips)
        rel = 0
        for t in tips:
            rel = RID.get(TIP.get(t[0]), 255)
            if rel != 255: break
        fl = 0
        if "ComputeBudget111111111111111111111111111111" in progs: fl |= 1
        if any("Nonce" in x for x in ixn): fl |= 2
        if any("Create" in x for x in ixn): fl |= 4            # create tx (dev buy)
        if "CloseAccount" in ixn: fl |= 8
        if not any(x in ("Buy", "Sell", "BuyV2", "SellV2", "BuyExactSolIn", "SellV3", "BuyV3") for x in ixn): fl |= 16   # routed (inner pump ix not named)
        if "ExtendAccount" in ixn: fl |= 32
        if any(x in ("BuyV2", "SellV2") for x in ixn): fl |= 64
        ixh = int.from_bytes(hashlib.blake2b("|".join(ixn).encode(), digest_size=4).digest(), "little")
        rows.append((sigh(m.group(4).decode()), s, min(i, 65535), min(int(r.get("cup") or 0), 2**32 - 1), min(int(r.get("cul") or 0), 2**32 - 1),
                     min(int(r.get("cu") or 0), 2**32 - 1), min(int(r.get("fee") or 0), 2**32 - 1), min(tamt, 2**32 - 1), rid, ixh, rel,
                     min(len(r.get("signers") or []), 255), min(len(tips), 255), fl))
    p.wait()
    a = np.array(rows, dtype=DT)
    b = np.array(sorted(blocks.items()), dtype=np.int64).reshape(-1, 2)
    rl = [None] * len(routes)
    for k, v in routes.items(): rl[v] = k
    np.savez(out, a=a, blocks=b, routes=np.array(rl, dtype=object))
    return f
if __name__ == "__main__":
    os.makedirs(f"{SCR}/shape", exist_ok=True)
    files = sorted(sys.argv[1:])
    with Pool(14) as P:
        for n, f in enumerate(P.imap_unordered(one, files, chunksize=2)):
            if n % 100 == 0: print(n, len(files), f, flush=True)
    print("done")
