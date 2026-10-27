#!/usr/bin/env python3
# Re-partition PumpSwap trades by mint into 64 buckets (compact tuples, dust < 0.001 SOL dropped except it is kept in the reserve fields).
# tuple: (s, i, bt, user, buy, base, q, user_sol, Bpre, Qpre, run)
import pickle, glob, os, zlib, collections
os.makedirs("bk", exist_ok=True)
NB = 64; buf = collections.defaultdict(list); n = 0
def flush():
    for b, v in buf.items():
        with open(f"bk/{b:02d}.pkl", "ab") as f: pickle.dump(v, f)
    buf.clear()
for f in sorted(glob.glob("parts/*.pkl")):
    run = "R3" if "20261023" in f else ("R2" if "20261022" in f else "R?")
    for r in pickle.load(open(f, "rb")):
        if r["q"] < 1_000_000: continue
        buf[zlib.crc32(r["m"].encode()) % NB].append((r["m"], r["s"], r["i"], r["bt"], r["user"], r["buy"], r["base"], r["q"], r["user_sol"], r["Bpre"], r["Qpre"], run)); n += 1
    if sum(len(v) for v in buf.values()) > 2_000_000: flush()
flush(); print("rows kept (>= 0.001 SOL):", n)
