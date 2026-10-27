#!/usr/bin/env python3
"""PRESEND FILTER: the chain table (g2_build.py) with per-mint and per-wallet indexes. Read-only helpers.
All rows are successful pump.fun trades (TradeEvent), chain order (slot, idx, j). MEASURED."""
import json, numpy as np

B = "/home/moiz/sniper-data/presend_filter"
SUPPLY = 1e15


class Chain:
    def __init__(self, cols=None):
        z = np.load(f"{B}/chain.npz")
        keep = cols or ("s", "i", "j", "bt", "buy", "sol", "tok", "vsol", "vtok", "fbps", "cbps", "mint", "user", "signer", "cup", "tip", "prog", "ixn", "txfee", "cul")
        self.c = {k: z[k] for k in set(keep) | {"mint"}}
        I = json.load(open(f"{B}/ids.json"))
        self.wal = I["w"]; self.mints = I["m"]; self.progs = I["p"]; self.ixns = I["x"]
        self.wid = {s: k for k, s in enumerate(self.wal)}
        self.mid = {s: k for k, s in enumerate(self.mints)}
        m = self.c["mint"]
        self.morder = np.argsort(m, kind="stable")
        ms = m[self.morder]
        self.mstart = np.searchsorted(ms, np.arange(len(self.mints) + 1))
        self.n = len(m)

    def mint_rows(self, mint):
        """row numbers of one mint's trades, chain order"""
        k = self.mid.get(mint)
        if k is None: return np.zeros(0, np.int64)
        return self.morder[self.mstart[k]:self.mstart[k + 1]]

    def user_index(self):
        u = self.c["user"]
        self.uorder = np.argsort(u, kind="stable")
        us = u[self.uorder]
        self.ustart = np.searchsorted(us, np.arange(len(self.wal) + 1))

    def user_rows(self, wid):
        return self.uorder[self.ustart[wid]:self.ustart[wid + 1]]

    def find(self, rows, s, i, j=0):
        """position (in rows) of the trade at chain position (s, i, j), or None"""
        S = self.c["s"][rows]; Ii = self.c["i"][rows]; J = self.c["j"][rows]
        k = np.nonzero((S == s) & (Ii == i) & (J == j))[0]
        return int(k[0]) if len(k) else None

    def before(self, rows, s, i, j=0):
        """how many of rows are strictly before chain position (s, i, j)"""
        S = self.c["s"][rows].astype(np.int64); Ii = self.c["i"][rows].astype(np.int64); J = self.c["j"][rows].astype(np.int64)
        key = (S << 24) | (Ii << 6) | J
        return int(np.searchsorted(key, (s << 24) | (i << 6) | j))


def price(vsol, vtok):
    return vsol / np.maximum(vtok, 1)
