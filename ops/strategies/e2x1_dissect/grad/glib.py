"""grad agent: shared tape access (curve trades near graduation, PumpSwap events of migrated pools, block clock)."""
import json, pickle, datetime as dt
import numpy as np

G = "/home/moiz/sniper-data/e2x1_dissect/grad"
SLOT_MS = 212.07
PKT = dt.timezone(dt.timedelta(hours=5))
E2X1 = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"

def pkt(bt): return dt.datetime.fromtimestamp(int(bt), PKT)
def pday(bt): return pkt(bt).strftime("%m-%d")

class Tape:
    def __init__(self):
        Z = np.load(G + "/tape.npz"); M = pickle.load(open(G + "/meta.pkl", "rb"))
        self.T = Z["tr"]; self.P = Z["ps"]; sl = Z["slots"].astype(np.int64)
        self.M = M; self.mints = M["mints"]; self.pools = M["pools"]; self.users = M["users"]
        self.mid = {m: k for k, m in enumerate(self.mints)}; self.pid = {p: k for k, p in enumerate(self.pools)}
        self.uid = {u: k for k, u in enumerate(self.users)}
        n = len(self.mints)
        self.ms = np.searchsorted(self.T["mint"], np.arange(n), "left"); self.me = np.searchsorted(self.T["mint"], np.arange(n), "right")
        npl = len(self.pools)
        self.ps_ = np.searchsorted(self.P["pool"], np.arange(npl), "left"); self.pe_ = np.searchsorted(self.P["pool"], np.arange(npl), "right")
        self.slo = int(sl[0, 0]); self.shi = int(sl[-1, 0])
        self.N = np.zeros(self.shi - self.slo + 1, np.int64); self.BT = np.zeros_like(self.N)
        self.N[sl[:, 0] - self.slo] = sl[:, 2] + 1; self.BT[sl[:, 0] - self.slo] = sl[:, 1]
        self.mig = {}                                   # canonical migration only (MigrateV2 tx); user-created pools ignored
        for d in M["mig"]:
            if d.get("mig") and d["mint"] not in self.mig: self.mig[d["mint"]] = d
        self.cmp = M["cmp"]; self.cr = M["cr"]
    # block clock (slot units)
    def bsize(self, s):
        k = int(s) - self.slo
        return int(self.N[k]) if 0 <= k < len(self.N) else 0
    def clock(self, s, i):
        n = max(self.bsize(s), 1)
        return s + min(i / n, 0.999999)
    def position(self, c):
        s = int(np.floor(c)); f = c - s
        for _ in range(12):
            if self.bsize(s) > 0: break
            s += 1; f = 0.0
        return s, int(np.floor(f * max(self.bsize(s), 1)))
    def bt_of(self, s):
        k = int(s) - self.slo
        while 0 < k < len(self.BT) and self.BT[k] == 0: k -= 1
        return int(self.BT[max(k, 0)])
    # rows
    def trades(self, m):
        k = self.mid.get(m)
        return self.T[self.ms[k]:self.me[k]] if k is not None else self.T[:0]
    def pool_events(self, pool):
        k = self.pid.get(pool)
        return self.P[self.ps_[k]:self.pe_[k]] if k is not None else self.P[:0]

def last_before(rows, s, i):
    """index of the last row strictly before chain position (s, i), -1 if none (rows sorted by slot, idx, j)"""
    key = rows["slot"].astype(np.int64) * 100000 + rows["idx"].astype(np.int64)
    return int(np.searchsorted(key, s * 100000 + i, "left")) - 1

def q_eff(P, k):
    """effective pre-trade quote reserve of event k, from the trade's own amounts (the event's pool_quote field is
    offset by ~17.58 SOL on pump pools; measured, see REPORT)"""
    B, b, q, u = float(P["pbase"][k]), float(P["base"][k]), float(P["quote"][k]), float(P["uquote"][k])
    if b <= 0: return float(P["pquote"][k]) + 17.584e9
    if P["buy"][k] == 0: return q * (B + b) / b
    x = min(q, u); return B * x / b - x

def pool_state_after(P, k, mig):
    """effective pool reserves (base, quote) after event k (k = -1 -> opening reserves from the migration)"""
    if k < 0: return float(mig["pbase"]), float(mig["pquote"])
    B, b = float(P["pbase"][k]), float(P["base"][k]); Q = q_eff(P, k)
    B2 = B + b if P["buy"][k] == 0 else B - b
    return B2, Q * B / B2

def pool_fee(P, k):
    """total fee rate (lp + protocol + creator) of the nearest sell event at or before k (else nearest event)"""
    if len(P) == 0: return 0.0125
    k = min(max(k, 0), len(P) - 1)
    for j in range(k, max(k - 50, -1), -1):
        if P["buy"][j] == 0 and P["quote"][j] > 0:
            return (float(P["lpfee"][j]) + float(P["pfee"][j]) + float(P["ccfee"][j])) / float(P["quote"][j])
    q = float(P["quote"][k])
    return (float(P["lpfee"][k]) + float(P["pfee"][k]) + float(P["ccfee"][k])) / q if q > 0 else 0.0125
