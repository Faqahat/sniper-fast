#!/usr/bin/env python3
"""VERIFY shared helpers (own code; only the recorded tape format is shared with the analysts).
Tape = presend/real build.py output (trades.npy, ids.json, creates.json, slots.npy). Chain clock cc(slot, idx) = slot*SMS +
idx/n_slot*SMS with n_slot = recorded block size (max idx + 1); 400 if the slot is missing."""
import json, time, hashlib
import numpy as np

SMS = 212.3
OUR_WALLETS = ("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR")
WHALE = 60_000_000_000_000


def pkt(t, f="%m-%d %H:%M"): return time.strftime(f, time.gmtime(int(t) + 18000))
def sh(s): return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "little")


class Tape:
    def __init__(self, tab, mints=None, load_ids=True):
        self.tab = tab
        T = np.load(f"{tab}/trades.npy", mmap_mode="r")
        self.ids = json.load(open(f"{tab}/ids.json")) if load_ids else None
        self.idm = {k: v for v, k in enumerate(self.ids)} if load_ids else None
        if mints is not None:
            mids = np.array(sorted(self.idm[m] for m in mints if m in self.idm), np.uint32)
            sel = np.isin(T["mint"], mids)
            T = np.array(T[sel])
        else:
            T = np.array(T)
        o = np.lexsort((T["j"], T["idx"], T["slot"], T["mint"]))
        self.T = T[o]
        m = self.T["mint"].astype(np.int64)
        b = np.flatnonzero(np.diff(m)) + 1
        st = np.concatenate([[0], b]); en = np.concatenate([b, [len(m)]])
        self.span = {int(m[a]): (int(a), int(e)) for a, e in zip(st, en)} if len(m) else {}
        S = np.load(f"{tab}/slots.npy")
        self.s0 = int(S["slot"].min()); n = int(S["slot"].max()) - self.s0 + 1
        self.bsz = np.zeros(n, np.float64); self.bsz[S["slot"].astype(np.int64) - self.s0] = S["maxi"].astype(np.float64) + 1
        self.sbt = np.zeros(n, np.int64); self.sbt[S["slot"].astype(np.int64) - self.s0] = S["bt"].astype(np.int64)
        self.our = {self.idm[w] for w in OUR_WALLETS if load_ids and w in self.idm}

    def nblk(self, s):
        k = s - self.s0
        if 0 <= k < len(self.bsz) and self.bsz[k] > 0: return self.bsz[k]
        return 400.0

    def cc(self, s, i):
        n = self.nblk(s)
        return s * SMS + min(i / max(n, i + 1.0), 0.999) * SMS

    def bt_of(self, s):
        k = s - self.s0
        if 0 <= k < len(self.sbt) and self.sbt[k] > 0: return int(self.sbt[k])
        # nearest recorded
        j = np.flatnonzero(self.sbt > 0)
        q = j[np.argmin(np.abs(j - k))]
        return int(self.sbt[q] + (k - q) * 0.4)

    def rows(self, mint):
        mid = self.idm.get(mint)
        if mid is None or mid not in self.span: return None
        a, e = self.span[mid]
        return self.T[a:e]


def fee_of(r):
    fb = int(r["fee_bps"]); cb = int(r["cfee_bps"])
    return ((fb if fb else 95) + (cb if cb else 30)) / 1e4


def load_runs(files):
    """our live pre-send records: windows (arm/disarm), landed tries, fills, sells, closes"""
    out = []
    for f in files:
        name = f.split("/")[-1].replace(".jsonl", "")
        for l in open(f, errors="ignore"):
            if '"presend_' not in l and '"buy_land"' not in l and '"sell_land"' not in l and '"fire"' not in l: continue
            try: r = json.loads(l)
            except Exception: continue
            r["_run"] = name; out.append(r)
    return out
