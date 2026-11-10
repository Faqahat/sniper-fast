#!/usr/bin/env python3
"""BOTREG step 0 [MEASURED, read-only on raw recordings]: decode recording chunks that no extract folder has yet
(10-27 run, newest 11-04 chunks, and in live use every new chunk) into /home/it/sniper-data/botreg/raw/<run>/<chunk>.npz.
Decoder = a verbatim copy of flatsig f1_extract.job (TradeEvent rows + failed buy/sell txs), so all three folders match.
usage: x0_extract.py [RUNDIR ...]   (default: every run under sniper-data/collect)   env NW = workers (default 4)"""
import sys, os, gzip, json, base64, struct, glob, time
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

OUT = f"{C.DATA}/raw"
DISC = bytes.fromhex("bddb7fd34ee661ee")
pk64 = C.pk64


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


def todo(rundirs):
    have = set()
    for d in C.RAWDIRS:
        for p in glob.glob(f"{d}/run_*/txs_*.npz"): have.add(os.path.basename(p)[:-4])
    jobs = []
    for rd in rundirs:
        if not os.path.isdir(f"{rd}/txs"): continue
        r = os.path.basename(rd.rstrip("/"))
        for fn in sorted(os.listdir(f"{rd}/txs")):
            if not fn.endswith(".jsonl.gz") or os.path.getmtime(f"{rd}/txs/{fn}") > time.time() - 240: continue
            base = fn[:-9]
            if base in have: continue
            os.makedirs(f"{OUT}/{r}", exist_ok=True)
            jobs.append((f"{rd}/txs/{fn}", f"{OUT}/{r}/{base}.npz"))
    return jobs


if __name__ == "__main__":
    rds = sys.argv[1:] or sorted(glob.glob(f"{C.COLLECT}/run_*/"))
    jobs = todo(rds)
    print("new chunks", len(jobs), flush=True)
    with Pool(int(os.environ.get("NW", "4"))) as p:
        for k, (d, a, b) in enumerate(p.imap_unordered(job, jobs)):
            if k % 20 == 0: print(k, len(jobs), os.path.basename(d), a, b, flush=True)
    print("done", len(jobs), flush=True)
