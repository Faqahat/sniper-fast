#!/usr/bin/env python3
"""GUARDS step 11 [MEASURED live fills, DIRECT only]: STATE's lead as a guard - the dump seller's (re-arm) / creator's remaining balance at
our landing position must be < Z% of supply. Re-arm = r38 only (no other live re-arm run); creator variant also on T2 fills where the
create record is on a local decoded table (r37 / r38 era tables).
usage: g11_dumper.py"""
import pickle, json, collections, sys
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/prevent/guards")
import glib as G
OUT = "/home/it/sniper-data/prevent/guards"
R = pickle.load(open(f"{OUT}/feats.pkl", "rb"))
tapes = pickle.load(open(f"{OUT}/tapes_fills.pkl", "rb"))
cre = {}
for tab in ("/home/it/sniper-data/presend_quiet4/tab37", "/home/it/sniper-data/prevent/guards/tab_tail", "/home/it/sniper-data/multiarm/tab38", "/home/it/sniper-data/prevent/guards/tab_t38"):
    for m, c in json.load(open(f"{tab}/creates.json")).items(): cre[m] = c.get("creator")
FIXC = 0.003524
def sc(o): return (o["pnl"] + FIXC) * 0.696 / (o["spend"] / 1e9) - FIXC
lines = []
for Z in (0.5, 1.0, 2.0, 3.0):
    for kind in ("rearm",):
        v = [o for o in R if o["kind"] == kind]
        blk = [o for o in v if o["wh_L"] >= Z / 100 * G.SUP]
        lines.append(f"dumper bag >= {Z}% at landing ({kind}, r38 live): fills {len(v)}, blocked {len(blk)}, blocked P&L {sum(sc(o) for o in blk):+.3f} -> gain {-sum(sc(o) for o in blk):+.3f}; "
                     f"blocked = {', '.join(o['mint'][:8] + f' {o[chr(112)+chr(110)+chr(108)]:+.3f}' for o in sorted(blk, key=lambda o: o['pnl'])[:8])}")
for Z in (1.0, 3.0):
    for kind in ("t2", "rearm"):
        for runs, lab in ((("A37",), "r37"), (("A38",), "r38")):
            v = [o for o in R if o["kind"] == kind and o["run"] in runs and cre.get(o["mint"])]
            blk = []
            for o in v:
                H = G.Hold(tapes[o["mint"]]); b = H.bal_before(cre[o["mint"]], H.key(o["slot"], o["idx"], 0))
                if b >= Z / 100 * G.SUP: blk.append(o)
            if v: lines.append(f"creator bag >= {Z}% at landing ({kind}, {lab}): fills with creator known {len(v)}, blocked {len(blk)}, gain {-sum(sc(o) for o in blk):+.3f}")
open(f"{OUT}/dumper.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
