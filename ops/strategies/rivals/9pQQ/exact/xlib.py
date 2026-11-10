"""9pQQ exact-rules: shared loader. Read-only. Adds per-run state arrays on top of tlib9.load_tape:
own (row is 9pQQ), hold (9pQQ holds the token at this row, i.e. strictly between its buy row and its sell row),
trig_b (this outside row is the immediate trigger of a 9pQQ buy: next row on the mint is its buy, <=1 slot later, skipping nothing),
trig_s (same for its sell)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import tlib9 as L
RUNS = L.RUNS; DAY = L.DAY; W = L.W
XOUT = "/home/it/sniper-data/rivals/9pQQ/exact"

def load(run):
    t = L.load_tape(run)
    n = len(t.s); wid = t.user_ix[L.W]
    own = t.u == wid
    t.own = own; t.wid = wid; t.n = n
    # position in mint segment
    t.seg0 = t.mstart[t.m]; t.seg1 = t.mstart[t.m + 1]
    # hold mask: running own token balance per mint > 0 BEFORE this row
    otok = np.where(own, t.tok, 0)
    cs = np.cumsum(otok) - otok                          # global cumsum before row
    base = np.concatenate([[0], np.cumsum(otok)])[t.mstart[:-1]]
    bal_before = cs - base[t.m]
    t.hold = bal_before > 0
    # previous non-own row in the same mint (index) for every row
    idx = np.arange(n)
    lastoth = np.where(~own, idx, -1)
    lastoth = np.maximum.accumulate(lastoth)
    prev_oth = np.concatenate([[-1], lastoth[:-1]])
    prev_oth = np.where(prev_oth >= t.seg0, prev_oth, -1)
    t.prev_oth = prev_oth
    ob = np.where(own & (t.tok > 0))[0]; os_ = np.where(own & (t.tok < 0))[0]
    t.ob, t.os = ob, os_
    # immediate trigger: previous non-own row j of own buy k with S[k]-S[j] <= 1 and nothing own in between except ... (own rows in between allowed)
    t.trig_b = np.zeros(n, bool); t.trig_s = np.zeros(n, bool)
    j = prev_oth[ob]; ok = (j >= 0); ok[ok] &= (t.s[ob[ok]] - t.s[j[ok]] <= 1)
    t.trig_b[j[ok]] = True; t.ob_trig = np.where(ok, j, -1)
    j = prev_oth[os_]; ok = (j >= 0); ok[ok] &= (t.s[os_[ok]] - t.s[j[ok]] <= 1)
    t.trig_s[j[ok]] = True; t.os_trig = np.where(ok, j, -1)
    return t
