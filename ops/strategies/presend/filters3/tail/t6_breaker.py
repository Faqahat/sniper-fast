#!/usr/bin/env python3
"""TAIL t6: circuit breaker on real fills, sequential (only trades it lets through can trip it): after N realized losses <= -L SOL
known within the last W minutes, block new trades for P minutes from the last of them. Loss known = our sell landed + 2 s."""
import sys, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/tail")
import t5_guards as G
from tlib import load
P = {d["mint"] + str(d["t"]): d for d in load()}
def known(r):
    d = P[r["mint"] + str(r["t"])]
    sl = (d.get("close") or {}).get("sell_land") or [None, None, None]
    return (sl[2] or d["t"] + 1_000_000_000) + 2_000_000_000
class Brk:
    def __init__(s, N, L, W, Pm): s.N, s.L, s.W, s.P = N, L, W * 60e9, Pm * 60e9; s.ev = []; s.until = 0
    def decide(s, r):
        ts = r["F"]["_ts"]
        bad = [t for t, v in s.ev if t <= ts and t >= ts - s.W and v <= -s.L]
        if len(bad) >= s.N: s.until = max(s.until, max(bad) + s.P)
        return ts < s.until
    def taken(s, r): s.ev.append((known(r), r["pnl"]))
if __name__ == "__main__":
    for N, L, W, Pm in [(1, 0.15, 10, 30), (1, 0.2, 10, 30), (1, 0.3, 10, 30), (2, 0.1, 10, 30), (2, 0.15, 10, 30), (2, 0.2, 10, 30), (2, 0.25, 10, 30),
                        (2, 0.2, 10, 60), (2, 0.15, 5, 20), (3, 0.1, 15, 30), (3, 0.1, 10, 60), (3, 0.05, 10, 30), (4, 0.05, 10, 30), (2, 0.1, 5, 15), (2, 0.3, 15, 60)]:
        G.score(f"breaker {N}:{L}:{W}:{Pm}", None, need_ann=False, seq=lambda: Brk(N, L, W, Pm))
