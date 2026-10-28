#!/usr/bin/env python3
"""recon step 8 (read-only): evidence. Per bot 5 random closed lots opened in the window (seed 7) with GMGN + Solscan links;
every payout / unwrap / inbound transfer with Solscan links and destinations. Out: recon/r8.txt"""
import json, pickle, collections, sys, os, random, time
W0, W1 = 1793038500, 1793124900
OUT = "/home/moiz/sniper-data/haqq_dissect/recon"
H = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
LOTS = pickle.load(open(f"{OUT}/lots.pkl", "rb"))["lots"]
Z = pickle.load(open(f"{OUT}/r6.pkl", "rb"))
L = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); L.append(s)
def pkt(t): return time.strftime("%m-%d %H:%M:%S", time.gmtime(t + 18000))
random.seed(7)
by = collections.defaultdict(list)
for l in LOTS:
    if l["inw"] and l["close_bt"] is not None: by[l["code"]].append(l)
P("## Evidence: 5 random lots per bot (opened in the window, seed 7). Amounts exact (lamports -> SOL).")
for c in sorted(by, key=lambda c: -len(by[c])):
    v = by[c]; pick = random.sample(v, min(5, len(v)))
    P(f"\n### bot {c} ({len(v):,} closed lots in the window)")
    P("| buy time PKT | cost SOL | net proceeds | tx costs | lot P&L | hold s | token (GMGN, his trades) | buy tx | sell tx(s) |")
    P("|---|---|---|---|---|---|---|---|---|")
    for l in sorted(pick, key=lambda l: l["bt"]):
        sells = sorted({s for s, bt, t, cc in l["sells"]})
        P(f"| {pkt(l['bt'])} | {l['cost']:.4f} | {l['out_w'] + l['out_after']:.4f} | {l['btxc'] + l['stxc_w'] + l['stxc_after']:.5f} | {l['pnl']:+.4f} | {l['close_bt'] - l['bt']} | [{l['mint'][:6]}..](https://gmgn.ai/sol/token/{l['mint']}?maker={H}) | [buy](https://solscan.io/tx/{l['sig']}) | "
          + " ".join(f"[sell{k + 1}](https://solscan.io/tx/{s})" for k, s in enumerate(sells[:4])) + " |")
P("\n## Every non-bot money movement in the window")
for name, lst in (("PAYOUT (Jupiter route)", Z["pay"]), ("UNWRAP (WSOL -> SOL)", Z["unw"]), ("INBOUND", Z["inb"]), ("OTHER", Z["other"])):
    for r in lst:
        outs = collections.Counter()
        for lvl, src, dst, lam in r.get("transfers") or []:
            if src == H: outs[dst] += lam
        P(f"- {name} {pkt(r['bt'])} PKT, wallet {r['sd'] / 1e9:+.6f} SOL, WSOL acct {r['wsol_d'] / 1e9:+.6f}: https://solscan.io/tx/{r['sig']}")
        if outs: P("    SOL sent by haqq: " + ", ".join(f"{d[:8]}.. {v / 1e9:.6f}" for d, v in outs.most_common()))
open(f"{OUT}/r8.txt", "w").write("\n".join(L) + "\n")
