#!/usr/bin/env python3
"""print the tape around an E2x1 row: show.py ROW [before] [after]"""
import sys, json
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
D = load(); w = int(D["wid"]); MN, US = names()
def show(R, nb=15, na=8):
    m = int(D["mint"][R]); a, e = span(D, m); cs = int(D["cr_slot"][m]); cu = int(D["cr_user"][m])
    print(f"== {MN[m]}  created slot {cs} {pkt(D['cr_bt'][m])} creator {(US[cu][:8] if cu >= 0 else '?')}")
    for r in range(max(a, R - nb), min(e, R + na + 1)):
        u = int(D["user"][r]); tag = "**E2X1**" if u == w else ("CREATOR" if u == cu else US[u][:8])
        v = D["vsol"][r] / 1e9; px = v / D["vtok"][r] * 1.073e15 / 30
        print(f"{'>' if r == R else ' '} s+{int(D['slot'][r]) - cs:5d} i{int(D['idx'][r]):4d} {'B' if D['buy'][r] else 'S'} {D['sol'][r]/1e9:7.3f} vsol {v:6.2f} px{px:6.2f} {tag}")
if __name__ == "__main__":
    a = [int(x) for x in sys.argv[1:]]; show(*a)
