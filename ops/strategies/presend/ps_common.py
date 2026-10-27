#!/usr/bin/env python3
# Shared loader for the PRE-SENT conditional-buy study (read-only; owner OK 10-25 ~00:55 PKT).
# Tapes: patterns/day_R1..R3.npz, dipdetect/day_R4.npz (p1_build.py columns). Only successful trades are in the tapes.
import json, time, calendar, zlib
import numpy as np
PO = "/home/moiz/sniper-data/strategies/patterns"; DD = "/home/moiz/sniper-data/strategies/dipdetect"
OUT = "/home/moiz/sniper-data/strategies/presend"
DAYS = {"R1": PO, "R2": PO, "R3": PO, "R4": DD}
RUNDIR = {"R1": "run_20261021_2207", "R2": "run_20261022_1543", "R3": "run_20261023_1426", "R4": "run_20261024_1425"}
SMS = 212.0
COLS = ("tok", "s", "i", "arr", "buy", "sol", "tokn", "vsol", "vtok", "fr", "slack", "wt", "bt", "uid")
pk = lambda s: calendar.timegm(time.strptime("2026-" + s, "%Y-%m-%d %H:%M")) - 18000
# evaluation windows = dd_lib.WIN (baseline fully defined there; R3/R4 do not overlap)
WIN = {"R1": ("10-22 03:07", "10-22 18:05"), "R2": ("10-22 20:43", "10-23 18:19"), "R3": ("10-23 19:26", "10-24 16:27"),
       "R4": ("10-24 19:25", "10-24 22:41")}
PRE = {"2KtcBCfhU3LRB31M6pwdDAtmceqGMrUx5AnajQUANBou": "2KtcBC", "CVPz447tBYu35RvN6qyySxJFVCXn7ULwGef3y2bWybvA": "CVPz447t"}
crc = lambda w: zlib.crc32(w.encode())

def load(day, cols=COLS, with_F=False):
    z = np.load(f"{DAYS[day]}/day_{day}.npz"); M = json.load(open(f"{DAYS[day]}/day_{day}_meta.json"))
    d = {k: z[k] for k in cols}
    if with_F: d["F"] = z["F"]
    d["meta"] = M["meta"]; d["feats"] = M["feats"]; d["FI"] = {k: i for i, k in enumerate(M["feats"])}
    nt = len(M["meta"]); cnt = np.bincount(d["tok"], minlength=nt); off = np.concatenate([[0], np.cumsum(cnt)[:-1]]).astype(np.int64)
    d["off"] = off; d["cnt"] = cnt; d["day"] = day
    if all(k in d for k in ("buy", "vsol", "vtok", "sol", "tokn")):
        b = d["buy"].astype(bool); V = d["vsol"]; T = d["vtok"]
        Vpre = np.where(b, V - d["sol"], V + d["sol"]); Tpre = np.where(b, T + d["tokn"], T - d["tokn"])
        d["p"] = V / T; d["ppre"] = Vpre / np.maximum(Tpre, 1.0)
        d["move"] = (d["p"] / d["ppre"] - 1) * 100
    # block time: fill zeros from the slot clock
    if "bt" not in d: return d
    bt = d["bt"].astype(np.int64); ok = bt > 0
    if (~ok).any() and ok.sum() > 100:
        a = np.polyfit(d["s"][ok].astype(float), bt[ok].astype(float), 1)
        bt = np.where(ok, bt, np.round(np.polyval(a, d["s"].astype(float))).astype(np.int64))
    d["t"] = bt
    return d

def in_win(d, t):
    a, b = WIN[d["day"]]; return (t >= pk(a)) & (t < pk(b))

def pkt(t): return time.strftime("%m-%d %H:%M", time.gmtime(int(t) + 18000))
