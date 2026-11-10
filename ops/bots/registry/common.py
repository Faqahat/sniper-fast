"""BOTREG common: paths, ids, time helpers, chunk index and the hour-window loader.
Raw trade/fail arrays come from three extract folders (same decoder, flatsig f1 format, read-only for the first two):
  /home/it/sniper-data/flatsig/raw, /home/it/sniper-data/flatperfect/raw, /home/it/sniper-data/botreg/raw (ours).
Ids: u64 = first 8 raw bytes of the base58 pubkey (big endian), as in flatsig. Times: PKT (UTC+5)."""
import os, glob, json
from datetime import datetime, timezone, timedelta
import numpy as np

PKT = timezone(timedelta(hours=5))
DATA = "/home/it/sniper-data/botreg"
COLLECT = "/data/tapes/collect"
RAWDIRS = ["/home/it/sniper-data/flatsig/raw", "/home/it/sniper-data/flatperfect/raw", f"{DATA}/raw"]
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR": "AMS", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE": "FRA"}
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58I = {c: i for i, c in enumerate(B58)}
SUP = 1e15                       # pump.fun token supply in raw units
H = 3600


def pk64(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    return int.from_bytes(n.to_bytes(32, "big")[:8], "big")


OURS64 = {pk64(k): v for k, v in OURS.items()}

# seed labels: owner list + earlier dissections (flatsig flib.NAMED), full 43/44-char strings only.
# Used ONLY to name operators and to score the backtest; discovery never reads this list.
SEED_NAMES = {
    "haqq6qnVBCZt97amh9VUFZRFCkD6NJxoYifacCuqqqq": "haqq", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq": "haqq",
    "2VggYpPumR3sV4K9vBqDzsmKzpB3BgSM4woRwbqqzweg": "haqq",
    "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN": "9pQQ", "8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk": "8PgC",
    "8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3": "8yYM", "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb": "E2x1",
    "EMKY7r6UekmmR1hREwCaPy835tCDGXGCw8fqibybgqzc": "EMKY", "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d": "sssss",
    "ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E": "sssss", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ": "sssss",
    "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi": "sssss", "4ggJqUDDHB9uZMSyR485VgYLMGLotV7Ctm9NDURCpp6f": "4ggJ",
    "DL7cmioGVA7Y4QLnhGZN1zrcNYhqnGzZcrGec3WJJS7d": "DL7c", "6Z91Dgiz9E44bMW11rQuMBjt1NwwPoQGXFNZieGfVtAb": "6Z91",
    "5ZtzVYRuF7sEhot31S68xHRCKDMkDdFtTp1iujTRjowV": "5Ztz", "3qvuM3U5UZPVagL1spxmgVgUvzT3h49gyJZyagxRtqKr": "3qvu",
    "BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP": "BUkp", "Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ": "E2x1",
    "EUkuD2J2KPcsbEFcSdm7SnkEXw6vAXr6XVB5FhFoziAo": "E2x1", "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ": "HkQ7",
    "DF7eRXHnvRQ9QeVCrdfS56a7RpBD6se6mgPvzApHPNr9": "DF7e", "CZ77onJzkSCwZC51Gg7H8oEUUJhqcx8LLKqnsNXWZSBx": "CZ77",
    "6VzXcLk9rCLDHgRBmUGKK8HY2KvhHmR4pZPCxi4tA1kx": "6VzX", "ETwEAQPLnAMRbU9EXjXTYoq8msfLkaD8x1AD1Zcbnz6b": "ETwE",
    "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw": "DYXD",
}
# operator groups known BEFORE this study (for link scoring only): haqq (3 wallets, owner + haqq6 report),
# E2x1/Grozoe/EUku (euku dissect: same operator), sssss (4 vanity wallets, owner list)
SEED64 = {pk64(k): v for k, v in SEED_NAMES.items()}


def pkt(t):
    return datetime.fromtimestamp(t, PKT).strftime("%m-%d %H:%M")


def hour_of(t):
    return int(t // H) * H


def b58enc(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = B58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


def chunk_index():
    """{chunk_start_epoch: [npz paths]} over all extract folders (one recording chunk may exist in two overlapping runs)"""
    idx = {}
    for d in RAWDIRS:
        for p in glob.glob(f"{d}/run_*/txs_*.npz"):
            t = int(os.path.basename(p)[4:-4])
            idx.setdefault(t, []).append(p)
    return dict(sorted(idx.items()))


def covered_hours(idx=None):
    """hours (epoch, PKT-aligned since 5 h offset is whole hours) that have >= 6 recording chunks starting in them"""
    idx = idx or chunk_index()
    c = {}
    for t in idx: c[hour_of(t)] = c.get(hour_of(t), 0) + 1
    return sorted(h for h, n in c.items() if n >= 6)


def load_window(t0, t1, idx=None):
    """trades + fails from chunks starting in [t0 - 300, t1); de-duplicated; trades sorted (mint, slot, idx, j);
    fails get a block time interpolated from the trade (slot, bt) map. Returns dict of arrays (T_*, F_*)."""
    idx = idx or chunk_index()
    T = {}; F = {}
    for t, ps in idx.items():
        if t < t0 - 300 or t >= t1: continue
        z = np.load(ps[0])
        for k in z.files:
            (T if k.startswith("t_") else F).setdefault(k[2:], []).append(z[k])
    if not T: return None
    T = {k: np.concatenate(v) for k, v in T.items()}; F = {k: np.concatenate(v) for k, v in F.items()}
    key = T["slot"].astype(np.int64) * (1 << 20) + T["idx"].astype(np.int64) * 64 + T["j"].astype(np.int64)
    _, u = np.unique(key, return_index=True); T = {k: v[u] for k, v in T.items()}
    o = np.lexsort((T["j"], T["idx"], T["slot"], T["mint"])); T = {k: v[o] for k, v in T.items()}
    keyf = F["slot"].astype(np.int64) * (1 << 20) + F["idx"].astype(np.int64)
    _, u = np.unique(keyf, return_index=True); F = {k: v[u] for k, v in F.items()}
    # slot -> block time for fails
    so = np.argsort(T["slot"], kind="stable"); ss, bb = T["slot"][so], T["bt"][so]
    F["bt"] = np.interp(F["slot"], ss, bb).astype(np.int64) if len(ss) else np.zeros(len(F["slot"]), np.int64)
    return T, F


_DISC = bytes.fromhex("bddb7fd34ee661ee")


def _ev_users(a):
    """one chunk -> {u64: b58} for the wanted ids found in TradeEvent user fields"""
    import gzip, base64
    fn, want = a; found = {}
    try:
        with gzip.open(fn, "rt", errors="replace") as f:
            for l in f:
                k = l.find('"ev":["')
                if k < 0: continue
                for e in l[k + 7:l.find('"]', k)].split('","'):
                    try: raw = base64.b64decode(e)
                    except Exception: continue
                    if raw[:8] != _DISC or len(raw) < 89: continue
                    u = int.from_bytes(raw[57:65], "big")
                    if u in want and u not in found: found[u] = b58enc(raw[57:89])
    except (EOFError, OSError):
        pass
    return found


def resolve_b58(us, max_files=600, nw=8):
    """u64 ids -> base58, read from TradeEvent user fields (the full 32-byte key from the chain, never from text) in the
    newest raw chunks, newest first, in parallel batches. Returns {u64: b58} for the ids found."""
    from multiprocessing import Pool
    want = set(int(u) for u in us); found = {}
    files = sorted(glob.glob(f"{COLLECT}/run_*/txs/txs_*.jsonl.gz"), key=lambda f: int(os.path.basename(f)[4:-9]), reverse=True)[:max_files]
    with Pool(nw) as p:
        for i in range(0, len(files), nw * 2):
            left = want - set(found)
            if not left: break
            for r in p.map(_ev_users, [(fn, left) for fn in files[i:i + nw * 2]]):
                for u, b in r.items(): found.setdefault(u, b)
    return found
