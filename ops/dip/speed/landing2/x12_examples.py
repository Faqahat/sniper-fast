#!/usr/bin/env python3
# Solscan-checkable examples: same dump, our landed copy vs the first reactive bot ahead of us (h2h.json), per situation.
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
import lib2
H = json.load(open(f"{lib2.D}/h2h.json")); WAL = json.load(open(f"{lib2.D}/wallets.json"))
NONREACT = {w for w, v in WAL.items() if v["grp"] == "instant"} | {w for w in WAL if WAL[w]["name"] in (
    "A9KKBdLy", "5cbP5Qmj", "CatkiNiJ", "FikgyrtV", "CZ77onJz", "ssssswdk", "AFrSqSLk", "E2x1ewwX", "DqhDuYbR", "DV69fm8T", "BZQkcWXg", "ngh1mY9m", "EThWL9wo")}
def pick(title, cond, want_svc=None, k=3):
    print(f"\n## {title}")
    n = 0
    for r in sorted(H, key=lambda r: -r["s0"]):
        if "our_ms" not in r or not cond(r): continue
        ahead = [x for x in r["rivals"] if x["w"] not in NONREACT and (x["s"], x["i"]) < (r["our_s"], r["our_i"])]
        if not ahead: continue
        w = ahead[0]
        if want_svc and not any(s in w["svc"] for s in want_svc): continue
        print(f"- {r['cl']} leader, dump {r['dump']} (block pos {r['i0']}/{r['n0']}, window slot {r['k']+1})\n"
              f"  - winner {WAL[w['w']]['name']} +{w['ms']} ms {'same slot' if w['ds']==0 else 'next slot'} via {w['svc']} (CU {(w['cup'] or 0):,} µL, tip {w['tip']/1e9:.4f}): {w['sig']}\n"
              f"  - us ({r['srv']} {r['run']}) +{r['our_ms']} ms {'same slot' if r['our_ds']==0 else 'slot +'+str(r['our_ds'])} via {r['our_svc']} ({'fill' if r['result']=='sold' else 'failed'}): {r['our_sig']}")
        n += 1
        if n >= k: break
pick("Jito leader behind a relayer: winner bypasses the 50 ms hold", lambda r: r["cl"] == "Jito-relayer")
pick("Jito leader with its own TPU", lambda r: r["cl"] == "Jito-own", ["helius", "glaive", "nozomi", "astralane"])
pick("Harmonic leader: winner via speedlanding / astralane", lambda r: r["cl"] == "Harmonic", ["speedlanding", "astralane"])
pick("BAM leader", lambda r: r["cl"] == "BAM")
pick("Firedancer leader", lambda r: r["cl"] == "Firedancer")
pick("Dump in the last quarter of its block, we spilled, winner made the slot", lambda r: r["q"] == 3 and r["our_ds"] >= 1)
pick("Dump in window slot 1 (short block), we spilled", lambda r: r["k"] == 0 and r["our_ds"] >= 1)
