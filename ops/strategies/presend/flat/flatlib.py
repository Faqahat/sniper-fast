#!/usr/bin/env python3
"""FLAT study: shared helpers (read-only). The chain table of f1_extract.py (every successful pump.fun trade, chain order) with a
per-mint index and the chain clock; pump's integer math (real/r065/pmath.py, MEASURED lamport-exact); the window table of
f3_base.py. Nothing here sends or changes anything."""
import sys, json, pickle, collections
import numpy as np

sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import pmath as PM          # noqa: E402  (buy_tok, sell_sol, fees, cost_exact_tok, net_of_budget)

D = "/home/moiz/sniper-data/presend_flat"
AMS = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"
FRA = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
SMS = 212.0                 # ms per slot (the chain clock of real/r065)
PKT = 18000
COHORT = "/home/moiz/sniper/ops/overnight/sel/cohort_train.json"
FBOTS = "/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json"
AMS_RUNS = "/home/moiz/sniper-data/runs/ams/runs"
PF_LIVE = "/home/moiz/sniper-data/presend_filter/live"
# every live pre-send run: its records, its OWN wallet (the engine's rule: "others" = not the whale, not this wallet), chain phases
RUNS = {
    "a19": dict(file=f"{AMS_RUNS}/dip_ams_r19.jsonl", wallet=AMS, phases=(0, 1), name="AMS r19"),
    "a20": dict(file=f"{AMS_RUNS}/dip_ams_r20.jsonl", wallet=AMS, phases=(0, 1), name="AMS r20"),
    "f21": dict(file=f"{PF_LIVE}/fra_dip_r21.jsonl", wallet=FRA, phases=(0, 1), name="FRA r21"),
    "f22": dict(file=f"{PF_LIVE}/fra_dip_r22.jsonl", wallet=FRA, phases=(0, 1), name="FRA r22"),
    "f23": dict(file=f"{PF_LIVE}/fra_dip_r23.jsonl", wallet=FRA, phases=(0, 1), name="FRA r23"),
    "f24": dict(file=f"{PF_LIVE}/fra_dip_r24.jsonl", wallet=FRA, phases=(0, 1), name="FRA r24"),
    "r24": dict(file=f"{AMS_RUNS}/dip_ams_r24.jsonl", wallet=AMS, phases=(1,), name="AMS r24"),
    "r25": dict(file=f"{AMS_RUNS}/dip_ams_r25.jsonl", wallet=AMS, phases=(1,), name="AMS r25"),
    "r26": dict(file=f"{AMS_RUNS}/dip_ams_r26.jsonl", wallet=AMS, phases=(1,), name="AMS r26"),
    "r27": dict(file=f"{AMS_RUNS}/dip_ams_r27.jsonl", wallet=AMS, phases=(1,), name="AMS r27"),
    "r28": dict(file=f"{D}/r28/dip_ams_r28.jsonl", wallet=AMS, phases=(1, 2), name="AMS r28"),
}
import os as _os
if _os.path.exists(f"{D}/chain_p3.npz"): RUNS["r28"]["phases"] = (1, 2, 3)
RUN_PHASES = {k: v["phases"] for k, v in RUNS.items()}
QUIET_LIVE = {"r27", "r28"}


def hm(ns, f="%m-%d %H:%M:%S"):
    import time
    return time.strftime(f, time.gmtime(int(ns / 1e9) + PKT))


class Chain:
    """the chain table (phases concatenated, chain order, duplicates removed) + indexes"""
    def __init__(self, phases=(1,)):
        cols = collections.defaultdict(list); ids_all = {"m": {}, "w": {}, "x": {}}; sig_tab = []
        blocks = []
        for ph in phases:
            z = np.load(f"{D}/chain_p{ph}.npz")
            I = json.load(open(f"{D}/ids_p{ph}.json"))
            remap = {}
            for tab in ("m", "w", "x"):
                d = ids_all[tab]; r = np.empty(len(I[tab]), np.uint32)
                for k, s in enumerate(I[tab]):
                    v = d.get(s)
                    if v is None: v = d[s] = len(d)
                    r[k] = v
                remap[tab] = r
            for c in z.files:
                a = z[c]
                if c == "mint": a = remap["m"][a]
                elif c in ("user", "signer"): a = remap["w"][a]
                elif c == "ixn": a = remap["x"][a]
                elif c == "sig_ix":
                    a = np.where(a >= 0, a + len(sig_tab), -1)
                cols[c].append(a)
            sig_tab += I["sig"]
            b = np.load(f"{D}/blocks_p{ph}.npz"); blocks.append(np.stack([b["slot"], b["maxi"], b["bt"]], 1))
        T = {c: np.concatenate(v) for c, v in cols.items()}
        o = np.lexsort((T["j"], T["i"], T["s"]))
        T = {c: v[o] for c, v in T.items()}
        dup = np.zeros(len(T["s"]), bool)
        dup[1:] = (T["s"][1:] == T["s"][:-1]) & (T["i"][1:] == T["i"][:-1]) & (T["j"][1:] == T["j"][:-1])
        self.c = {c: v[~dup] for c, v in T.items()}
        self.n = len(self.c["s"])
        self.mints = list(ids_all["m"]); self.wal = list(ids_all["w"]); self.ixns = list(ids_all["x"]); self.sigs = sig_tab
        self.mid = ids_all["m"]; self.wid = ids_all["w"]
        m = self.c["mint"]
        self.morder = np.argsort(m, kind="stable")
        self.mstart = np.searchsorted(m[self.morder], np.arange(len(self.mints) + 1))
        B = np.concatenate(blocks); ob = np.lexsort((B[:, 1], B[:, 0])); B = B[ob]
        last = np.ones(len(B), bool); last[:-1] = B[1:, 0] != B[:-1, 0]; B = B[last]
        self.b_slot = B[:, 0]; self.b_n = B[:, 1] + 1; self.b_bt = B[:, 2]
        self.ams = self.wid.get(AMS, -1); self.fra = self.wid.get(FRA, -1)
        self.key = (self.c["s"].astype(np.int64) << 24) | (self.c["i"].astype(np.int64) << 6) | self.c["j"].astype(np.int64)

    def mint_rows(self, mint):
        k = self.mid.get(mint)
        if k is None: return np.zeros(0, np.int64)
        return self.morder[self.mstart[k]:self.mstart[k + 1]]

    def nblk(self, s):
        k = np.searchsorted(self.b_slot, s)
        if k < len(self.b_slot) and self.b_slot[k] == s: return int(self.b_n[k])
        return 0

    def cc(self, s, i):
        """chain clock (ms): slot x 212 + the tx's share of its block"""
        n = self.nblk(s) or 400
        return s * SMS + i / max(float(n), i + 1.0) * SMS

    def inv(self, a):
        """chain clock -> (slot, fractional tx index)"""
        s = int(a // SMS); f = a / SMS - s
        n = self.nblk(s) or 400
        return s, f * n

    def sig(self, row):
        k = int(self.c["sig_ix"][row])
        return self.sigs[k] if k >= 0 else None


def poskey(s, i, j=0):
    return (int(s) << 24) | (int(i) << 6) | int(j)


def load_base(run):
    return pickle.load(open(f"{D}/base_{run}.pkl", "rb"))
