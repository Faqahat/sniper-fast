#!/usr/bin/env python3
# CORRECTED dd1 build (model check, 10-25): runs ops/strategies/dipdetect/dd1_build.py UNCHANGED except that path() is replaced
# by the corrected replay (mc_corr.replay_corr, all 200 exits): measured per-wallet price tolerance for the 75 fast dip bots
# behind us (conditional on a competing buyer ahead), non-target followers kept (their success does not fall for pushes < ~10%),
# no phantom sells of dropped followers, our sell 93 ms into the exit slot (real median). Optional crowd-out: env MC_CROWD (0.4).
# Writes to /home/moiz/sniper-data/modelcheck/dd1corr/ (same file names as dd1_build). mx6/mn6 are left at the entry value.
# usage: nice python3 -I dd1_corr_build.py R4 [procs]
import sys, os, zlib
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import mc_lib as M, mc_corr as MC
import dd1_build as D
D.OUT = "/home/moiz/sniper-data/modelcheck/dd1corr"; os.makedirs(D.OUT, exist_ok=True)
CV = MC.Curves(f"{M.OUT}/curves_all.json"); CROWD = float(os.environ.get("MC_CROWD", "0"))
class _T: pass
def path_corr(Sl, Al, Bl, SOLl, TKl, Vl, Tl, FRl, SKl, UIDl, n, j0, L):
    tp = _T(); tp.S, tp.A, tp.B, tp.SOL, tp.TK, tp.V, tp.T, tp.FR, tp.SK, tp.U, tp.n = Sl, Al, Bl, SOLl, TKl, Vl, Tl, FRl, SKl, UIDl, n
    a0 = Al[j0]; ke = j0 + 1
    while ke < n and Al[ke] < a0 + L: ke += 1
    ahead = ke - j0 - 1; ab = sum(1 for x in range(j0 + 1, ke) if Bl[x]); ap = sum(1 for x in range(j0 + 1, ke) if Bl[x] and UIDl[x] in D.UPRO)
    key = zlib.crc32(f"{Sl[j0]}:{int(Al[j0] * 1000)}:{j0}".encode())
    o = MC.replay_corr(tp, j0, D.SIZE, L, guard=D.GUARD, follow="comp", others="keep", phantom=True, sell_lat=93.0, crowd=CROWD, CV=CV, rowkey=key, full=True)
    if o["status"] != 0: return (o["status"], o["ratio"], ahead, ab, ap, 0, None, None, 0.0, 0.0)
    pn = [o["pnl"][e] for e in range(len(M.EXITS))]; of = [o["off"][e] for e in range(len(M.EXITS))]
    return (0, o["ratio"], ahead, ab, ap, o["s_in"], pn, of, 1.0, 1.0)
D.path = path_corr
if __name__ == "__main__":
    D.main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 4)
