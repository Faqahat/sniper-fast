#!/usr/bin/env python3
"""FRONT step 12 (read-only): example paying dumps with links (GMGN token, Solscan txs): dump, front buyers #1-#3, our first landed tx.
Out: sniper-data/haqq_dissect/front/f12_examples.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
R = pickle.load(open(f"{OUT}/f8_rows.pkl", "rb")); W = pickle.load(open(f"{OUT}/f7.pkl", "rb")); F10 = pickle.load(open(f"{OUT}/f10.pkl", "rb"))
ids, _ = L.ids_map()
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
pick = []
seen = set()
def add(cond, n, label):
    g = sorted([r for r in R if cond(r) and r["i"] in W and r["i"] not in seen], key=lambda r: -r["v"])
    for r in g[:n]: pick.append((label, r)); seen.add(r["i"])
add(lambda r: r["st"].startswith("6c") and r["client"] == "bam" and r["region"] == "EU", 2, "pre-send behind, BAM, EU")
add(lambda r: r["st"].startswith("6c") and r["client"] == "harmonic", 1, "pre-send behind, Harmonic")
add(lambda r: r["st"].startswith("7 ") and r["client"] == "jito", 1, "regular behind, Jito")
add(lambda r: r["st"].startswith(("6c", "7 ")) and r["region"] == "US-East", 1, "attempted, US-East leader")
add(lambda r: r["st"].startswith(("6c", "7 ")) and F10.get(r["i"], {}).get("any"), 1, "pre-sender first")
add(lambda r: r["st"].startswith("6a"), 1, "pre-send tries all landed before the dump")
for label, r in pick:
    w = W[r["i"]]; aft = [a for a in w["after"] if a["s"] in (r["ds"], r["ds"] + 1)]
    buys = [a for a in aft if a["buy"] and a["ok"]]
    ours = next((a for a in aft if a["ours"]), None)
    P(f"\n### {label}: {L.pkt(L.slot_time(r['ds']))} PKT, leader {r['client']} / {r['region']}, front value {1000*r['v']:+.0f} mSOL (0.40 SOL, wave)")
    P(f"- token: https://gmgn.ai/sol/token/{r['mint']}")
    P(f"- dump (slot {r['ds']}, idx {r['di']}, sell {R and 0 or 0}): https://solscan.io/tx/{w['dump']['sig']}  [{'+'.join(w['dump']['paths'])}]")
    for k, a in enumerate(buys[:3]):
        P(f"- buy #{k+1}: {a['signer'][:8]}{' (OURS)' if a['ours'] else ''} slot +{a['s']-r['ds']} idx {a['i']} [{'+'.join(a['sh']['paths'])}, CU price {a['sh']['cup']}, "
          f"router {a['sh']['router']}, pre-send txs before dump {a['pre_fail']}] https://solscan.io/tx/{a['sh']['sig']}")
    if ours:
        nb = sum(1 for a in buys if (a['s'], a['i']) < (ours['s'], ours['i']))
        P(f"- OUR first tx after the dump: slot +{ours['s']-r['ds']} idx {ours['i']}, {'filled' if ours['ok'] else 'FAILED ' + str(ours['err'])}, {nb} outside buys ahead "
          f"[{'+'.join(ours['sh']['paths'])}, CU price {ours['sh']['cup']}] https://solscan.io/tx/{ours['sh']['sig']}")
    else:
        bt = [t for t in r["tries"]]
        P(f"- OUR tries: " + ", ".join(f"slot {t['slot']-r['ds']:+d} idx {t['idx']} {t.get('res')}" for t in bt[:6]))
open(f"{OUT}/f12_examples.txt", "w").write("\n".join(out) + "\n")
