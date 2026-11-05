#!/usr/bin/env python3
"""FLATSIG step 1 [MEASURED, read-only on the raw recordings]: decode every landed pump.fun TradeEvent of a recording into compact
numpy arrays, one .npz per 5-min chunk, plus every FAILED tx's (slot, idx, fee payer, first mint, buy/sell ix) so bot attempts can
be counted.
Trade row: slot, idx, j (event # in tx), mint (u64 = first 8 bytes of the pubkey, big-endian), user (u64, same), buy, sol (lamports),
tok (raw token units), vsol (virtual SOL reserve after the trade, lamports, from the event), bt (block time s).
Ids: u64 of the first 8 raw bytes of the base58 pubkey -> scripts map names with flib.pk64().
usage: f1_extract.py RUNDIR [RUNDIR ...]  -> /home/moiz/sniper-data/flatsig/raw/<run>/<chunk>.npz"""
import sys, os, gzip, json, base64, struct, glob
import numpy as np
from multiprocessing import Pool

OUT = "/home/moiz/sniper-data/flatsig/raw"
DISC = bytes.fromhex("bddb7fd34ee661ee")
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58I = {c: i for i, c in enumerate(B58)}


def pk64(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes(32, "big")
    return int.from_bytes(b[:8], "big")


def job(a):
    src, dst = a
    if os.path.exists(dst): return dst, -1, -1
    T = {k: [] for k in ("slot", "idx", "j", "mint", "user", "buy", "sol", "tok", "vsol", "bt")}
    F = {k: [] for k in ("slot", "idx", "payer", "mint", "kind")}
    pkc = {}
    def pk(s):
        v = pkc.get(s)
        if v is None: v = pkc[s] = pk64(s)
        return v
    try:
        with gzip.open(src, "rt", errors="replace") as f:
            for l in f:
                try: d = json.loads(l)
                except Exception: continue
                if d.get("err") is not None:
                    sg = d.get("signers") or []
                    ms = d.get("mints") or []
                    if not sg or not ms: continue
                    ixn = d.get("ixn") or []
                    k = 0
                    for x in ixn:
                        if x.startswith("Buy"): k = 1; break
                        if x.startswith("Sell"): k = 2; break
                    if k == 0: continue
                    F["slot"].append(d["s"]); F["idx"].append(d.get("i") or 0); F["payer"].append(pk(sg[0]))
                    F["mint"].append(pk(ms[0])); F["kind"].append(k)
                    continue
                evs = d.get("ev") or []
                j = 0
                for e in evs:
                    try: raw = base64.b64decode(e)
                    except Exception: continue
                    if raw[:8] != DISC or len(raw) < 129: continue
                    sol, tok = struct.unpack_from("<QQ", raw, 40)
                    ib = raw[56]
                    ts, = struct.unpack_from("<q", raw, 89)
                    vsol, = struct.unpack_from("<Q", raw, 97)
                    if ib not in (0, 1): continue
                    T["slot"].append(d["s"]); T["idx"].append(d.get("i") or 0); T["j"].append(j)
                    T["mint"].append(int.from_bytes(raw[8:16], "big")); T["user"].append(int.from_bytes(raw[57:65], "big"))
                    T["buy"].append(ib); T["sol"].append(sol); T["tok"].append(tok); T["vsol"].append(vsol); T["bt"].append(ts)
                    j += 1
    except (EOFError, OSError):
        pass
    np.savez(dst + ".tmp.npz",
             t_slot=np.array(T["slot"], np.int64), t_idx=np.array(T["idx"], np.int32), t_j=np.array(T["j"], np.int8),
             t_mint=np.array(T["mint"], np.uint64), t_user=np.array(T["user"], np.uint64), t_buy=np.array(T["buy"], np.int8),
             t_sol=np.array(T["sol"], np.uint64), t_tok=np.array(T["tok"], np.uint64), t_vsol=np.array(T["vsol"], np.uint64),
             t_bt=np.array(T["bt"], np.int64),
             f_slot=np.array(F["slot"], np.int64), f_idx=np.array(F["idx"], np.int32), f_payer=np.array(F["payer"], np.uint64),
             f_mint=np.array(F["mint"], np.uint64), f_kind=np.array(F["kind"], np.int8))
    os.rename(dst + ".tmp.npz", dst)
    return dst, len(T["slot"]), len(F["slot"])


if __name__ == "__main__":
    jobs = []
    nw = int(os.environ.get("NW", "13"))
    for rd in sys.argv[1:]:
        r = os.path.basename(rd.rstrip("/")); os.makedirs(f"{OUT}/{r}", exist_ok=True)
        for fn in sorted(os.listdir(f"{rd}/txs")):
            if fn.endswith(".gz") and os.path.getmtime(f"{rd}/txs/{fn}") < __import__("time").time() - 240: jobs.append((f"{rd}/txs/{fn}", f"{OUT}/{r}/{fn[:-9]}.npz"))
    if os.environ.get("ONE"): jobs = jobs[:1]
    nt = nf = 0
    with Pool(nw) as p:
        for k, (d, a, b) in enumerate(p.imap_unordered(job, jobs)):
            nt += max(a, 0); nf += max(b, 0)
            if k % 50 == 0: print(k, len(jobs), nt, nf, flush=True)
    print("done", len(jobs), nt, nf, flush=True)
