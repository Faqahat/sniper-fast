#!/usr/bin/env python3
"""LIM step 19 (read-only): on the dumps where our live limit failed but haqq bots 247/248 bought within 2 slots (oracle dumps),
where did the bots land relative to our failed try / fire, and what did their lot make (pos/p1.pkl lots: out + left at mark
- cost, before tx costs; MEASURED) vs our no-limit fill at our position (wave, gross)?
Out: data/lim/l19.txt"""
import pickle, collections
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"; HD = "/home/moiz/sniper-data/haqq_dissect"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
P1 = pickle.load(open(f"{HD}/pos/p1.pkl", "rb"))
BOT = collections.defaultdict(list)
for b, lt in zip(P1["buys"], P1["lots"]):
    if lt.get("code") in (247, 248):
        BOT[b["mint"]].append(dict(s=b["slot"], i=b["idx"], code=lt["code"], cost=float(lt["cost"]), pnl=float(lt["out"]) - float(lt["cost"]) if lt.get("left", 0) <= 1 else None))
E = [e for e in pickle.load(open(f"{OUT}/sel_events.pkl", "rb")) if not e["mayhem"]]
for kind in ("ps", "reg"):
    rows = []
    for e in E:
        if e["kind"] != kind or e["live_fill"]: continue
        c = next((c for c in e["cands"] if c["crossed"] and c["dump"]["oracle"]), None)
        if c is None: continue
        ds, di = c["dump"]["d_slot"], c["dump"]["d_idx"]
        bots = [b for b in BOT[e["mint"]] if (b["s"], b["i"]) > (ds, di) and b["s"] <= ds + 2]
        rows.append((c, bots))
    P(f"\n## {kind}: not filled live, oracle dump: {len(rows)}")
    ahead = sum(1 for c, bots in rows for b in bots if b["s"] - c["dump"]["d_slot"] < c["dslots"] or (b["s"] - c["dump"]["d_slot"] == c["dslots"]))
    nb = sum(len(b) for c, b in rows)
    P(f"- bot buys on those dumps: {nb}; in our landing slot or earlier: {ahead} ({100*ahead/max(nb,1):.0f}%)")
    bp = [b["pnl"] / b["cost"] for c, bots in rows for b in bots if b["pnl"] is not None]
    P(f"- bot lots there: mean {100*np.mean(bp):+.2f}%/SOL (n {len(bp)}), sum {sum(b['pnl'] for c, bots in rows for b in bots if b['pnl'] is not None):+.3f} SOL (before his ~0.79 mSOL/lot)")
    ov = [c["val"][("wv", 1.0)] / 0.4 for c, bots in rows]
    sz = np.mean([1 for _ in rows])
    P(f"- our no-limit fill at our position: wave gross mean {1000*np.mean([c['val'][('wv',1.0)] for c, b in rows]):+.1f} mSOL; our try need p50 {np.median([c['need'] for c, b in rows]):.3f}; rows ahead p50 {np.median([c['nahead'] for c, b in rows]):.0f}")
open(f"{OUT}/l19.txt", "w").write("\n".join(out) + "\n")
# exact (slot, idx) order on our failed REGULAR fires (dv8 fires_tape 'us' = our first landed copy)
FT = pickle.load(open("/home/moiz/sniper-data/dv8/fires_tape.pkl", "rb"))
BB = collections.defaultdict(list)
for b, lt in zip(P1["buys"], P1["lots"]):
    if lt.get("code") in (247, 248): BB[b["mint"]].append((b["slot"], b["idx"], float(lt["out"]) - float(lt["cost"]), float(lt["cost"])))
ah, bh = [], []
for f in FT:
    if f["out"] != "fail" or f["us"] is None or f["ds"] is None: continue
    for b in BB[f["mint"]]:
        if (b[0], b[1]) > (f["ds"], f["di"]) and b[0] <= f["ds"] + 2: (ah if (b[0], b[1]) < tuple(f["us"]) else bh).append(b[2] / b[3])
P(f"\n## exact order, our FAILED regular fires: bot 247/248 buys AHEAD of our landed copy {len(ah)} lots, {100*np.mean(ah):+.2f}%/SOL | BEHIND us {len(bh)} lots, {100*np.mean(bh):+.2f}%/SOL (lot P&L before his ~0.24%/SOL tx cost)")
open(f"{OUT}/l19.txt", "w").write("\n".join(out) + "\n")
