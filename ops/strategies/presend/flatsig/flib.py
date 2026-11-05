"""FLATSIG common: periods, P&L classes, the named competitor cohort, loading the f2 run extracts and the f1 raw chain arrays."""
import pickle, collections, glob, os
from datetime import datetime, timezone, timedelta
import numpy as np

PKT = timezone(timedelta(hours=5))
D = "/home/moiz/sniper-data/flatsig"
RUNS = ["r37", "r38", "r39", "r40", "r41", "r42", "r43", "r44", "r45", "r46", "r47", "r48", "r49", "r50", "r51", "r52", "r53",
        "r54", "r55"]
CUT = datetime(2026, 11, 1, 12, 0, tzinfo=PKT).timestamp() * 1e9
ATT0 = datetime(2026, 11, 2, 8, 0, tzinfo=PKT).timestamp() * 1e9
ATT1 = datetime(2026, 11, 2, 8, 40, tzinfo=PKT).timestamp() * 1e9
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
PERS = ["DEV", "VAL", "HOLD"]
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58I = {c: i for i, c in enumerate(B58)}

# named competitor dip bots (owner's list + earlier dissections); several names = one operator
NAMED = {
    "haqq6qnVBCZt97amh9VUFZRFCkD6NJxoYifacCuqqqq": "haqq", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq": "haqq",
    "2VggYpPumR3sV4K9vBqDzsmKzpB3BgSM4woRwbqqzweg": "haqq",
    "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN": "9pQQ", "8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk": "8PgC",
    "8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3": "8yYM", "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb": "E2x1",
    "EMKY7r6UekmmR1hREwCaPy835tCDGXGCw8fqibybgqzc": "EMKY", "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d": "sssss",
    "ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E": "sssss", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ": "sssss",
    "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi": "sssss", "4ggJqUDDHB9uZMSyR485VgYLMGLotV7Ctm9NDURCpp6f": "4ggJ",
    "DL7cmioGVA7Y4QLnhGZN1zrcNYhqnGzZcrGec3WJJS7d": "DL7c", "6Z91Dgiz9E44bMW11rQuMBjt1NwwPoQGXFNZieGfVtAb": "6Z91",
    "5ZtzVYRuF7sEhot31S68xHRCKDMkDdFtTp1iujTRjowV": "5Ztz", "3qvuM3U5UZPVagL1spxmgVgUvzT3h49gyJZyagxRtqKr": "3qvu",
    "BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP": "BUkp", "Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ": "Groz",
    "EUkuD2J2KPcsbEFcSdm7SnkEXw6vAXr6XVB5FhFoziAo": "EUku", "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ": "HkQ7",
    "DF7eRXHnvRQ9QeVCrdfS56a7RpBD6se6mgPvzApHPNr9": "DF7e", "CZ77onJzkSCwZC51Gg7H8oEUUJhqcx8LLKqnsNXWZSBx": "CZ77",
    "6VzXcLk9rCLDHgRBmUGKK8HY2KvhHmR4pZPCxi4tA1kx": "6VzX", "ETwEAQPLnAMRbU9EXjXTYoq8msfLkaD8x1AD1Zcbnz6b": "ETwE",
    "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw": "DYXD",
}
CORE3 = {"haqq", "9pQQ", "8PgC"}


def pk64(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    return int.from_bytes(n.to_bytes(32, "big")[:8], "big")


NAMED64 = {pk64(k): v for k, v in NAMED.items()}
OURS64 = {pk64(k) for k in OURS}


def pkt(t): return datetime.fromtimestamp(t / 1e9, PKT).strftime("%m-%d %H:%M:%S")


def period(run, t):
    if run in ("r37", "r38", "r39", "r40", "r41"): return "DEV"
    if run == "r42": return "DEV" if t < CUT else "VAL"
    return "HOLD"


def cls(p):
    """P&L class of a live position (SOL): flat = -0.025..0, small win 0..+0.025, win >= +0.025, big loss < -0.025"""
    if p < -0.025: return "bigloss"
    if p <= 0: return "flat"
    if p < 0.025: return "small"
    return "win"


_X = {}
def load(run):
    if run not in _X: _X[run] = pickle.load(open(f"{D}/runs/ex_{run}.pkl", "rb"))
    return _X[run]


def all_positions():
    P = []
    for r in RUNS:
        for p in load(r)["pos"]:
            p = dict(p); p["per"] = period(r, p["t0"]); p["cls"] = cls(p["pnl"])
            p["attk"] = r == "r42" and ATT0 - 60e9 <= p["t0"] <= ATT1 + 60e9
            P.append(p)
    P.sort(key=lambda p: (p["t0"], p["buy_t"]))
    for i, p in enumerate(P): p["id"] = i
    return P


def q3a(p):
    """QUIET3-A exactly as the engine (T2; n_120s <= 15 and wh_dumps <= 3, QUIET's rule on)"""
    if p["kind"] != "T2": return False
    v, q = p.get("v2") or {}, p.get("quiet") or {}
    n, wd = v.get("n_120s"), q.get("wh_dumps")
    return n is not None and wd is not None and q.get("rule_on") is not False and n <= 15 and wd <= 3


def q3a_live(run):
    return bool((load(run)["cfg"] or {}).get("quiet3a"))


def run_hours():
    """hours of live trading per (period, run) = first..last position trigger"""
    by = collections.defaultdict(list)
    for p in all_positions(): by[(p["per"], p["run"])].append(p["t0"])
    return {k: (max(v) - min(v)) / 3.6e12 for k, v in by.items()}


# ---------------- raw chain (f1 arrays) ----------------
RAW = f"{D}/raw"


def raw_chunks():
    """[(t_first_bt, path)] for every extracted chunk, time ordered"""
    out = []
    for p in glob.glob(f"{RAW}/*/*.npz"):
        out.append((int(os.path.basename(p).split("_")[1].split(".")[0]), p))
    return sorted(out)
