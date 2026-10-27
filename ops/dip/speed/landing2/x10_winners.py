#!/usr/bin/env python3
# Win / loss vs us on the dumps we fired: the first REACTIVE bot that landed ahead of us (pre-senders and seller tools excluded).
# What did it use that we did not? Split: leader client, late-in-block dumps (Q4), window slot 1, our spills (we missed the dump's block).
import sys, json, collections, statistics as st
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
import lib2
H = json.load(open(f"{lib2.D}/h2h.json"))
WAL = json.load(open(f"{lib2.D}/wallets.json"))
NONREACT = {w for w, v in WAL.items() if v["grp"] == "instant"} | {w for w in WAL if WAL[w]["name"] in (
    "A9KKBdLy", "5cbP5Qmj", "CatkiNiJ", "FikgyrtV", "CZ77onJz", "ssssswdk", "AFrSqSLk", "E2x1ewwX", "DqhDuYbR", "DV69fm8T", "BZQkcWXg", "ngh1mY9m", "EThWL9wo")}
med = lambda v: round(st.median(v), 1) if v else None
have = [r for r in H if "our_ms" in r]
for r in have:
    ahead = [x for x in r["rivals"] if x["w"] not in NONREACT and (x["s"], x["i"]) < (r["our_s"], r["our_i"])]
    r["win"] = ahead[0] if ahead else None
    r["n_react_ahead"] = len(ahead)
def our_route(r):
    s = r["our_svc"]
    return {"none": "staked-rpc (CK, no tip)", "nozomi": "nozomi", "helius": "helius", "landx": "landx", "jito": "jito-bundle"}.get(s, s)
def block(title, v):
    w = [r for r in v if r["win"]]
    print(f"\n== {title}: our fires {len(v)} | a reactive bot landed ahead of us in {len(w)} ({len(w)/max(1,len(v)):.0%})")
    if not v: return
    print(f"   ours: {med([r['our_ms'] for r in v])} ms, same-slot {sum(1 for r in v if r['our_ds']==0)/len(v):.0%}, filled {sum(1 for r in v if r['result']=='sold')/len(v):.0%} "
          f"| our landed copy: {collections.Counter(our_route(r) for r in v).most_common(5)}")
    if not w: return
    print(f"   first reactive bot ahead: {med([r['win']['ms'] for r in w])} ms, in the dump's slot {sum(1 for r in w if r['win']['ds']==0)/len(w):.0%} "
          f"| CU price med {med([r['win']['cup'] or 0 for r in w]):,.0f} µL (ours {med([r['our_cup'] or 0 for r in w]):,.0f}) | tip med {med([r['win']['tip'] for r in w])/1e9:.5f} (ours {med([r['our_tip'] for r in w])/1e9:.5f})")
    print(f"   its route: {collections.Counter(r['win']['svc'] for r in w).most_common(8)}")
    print(f"   who: {collections.Counter(WAL[r['win']['w']]['name'] for r in w).most_common(8)}")
    gap = [r["our_ms"] - r["win"]["ms"] for r in w]
    print(f"   our lag behind it: p25 {sorted(gap)[len(gap)//4]:.1f} / p50 {med(gap)} / p75 {sorted(gap)[3*len(gap)//4]:.1f} ms")
block("ALL", have)
for c in ("Jito-own", "Jito-relayer", "BAM", "Harmonic", "Firedancer", "Rakurai"):
    block(f"leader {c}", [r for r in have if r["cl"] == c])
block("dump in the LAST quarter of its block (Q4)", [r for r in have if r["q"] == 3])
block("dump in window slot 1 (short first block)", [r for r in have if r["k"] == 0])
block("WE SPILLED (our buy landed in a later slot than the dump)", [r for r in have if r["our_ds"] >= 1])
block("we spilled AND the dump was in Q1-Q3", [r for r in have if r["our_ds"] >= 1 and r["q"] <= 2])
block("Jito leaders (own+relayer), dump in window slot 1", [r for r in have if r["cl"].startswith("Jito") and r["k"] == 0])
json.dump([dict(dump=r["dump"], win_sig=r["win"]["sig"] if r["win"] else None, our_sig=r["our_sig"]) for r in have], open(f"{lib2.D}/winners.json", "w"))
