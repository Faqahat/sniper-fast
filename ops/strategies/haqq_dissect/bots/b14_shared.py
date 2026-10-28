#!/usr/bin/env python3
"""BOTS step 14 (read-only): the MEASURED shared-dump test. Dumps where our live engine fired a regular buy (fires_tape) AND bot 247/248 bought:
where did WE really land vs him (chain order), and what would OUR REAL landed position have made (exact replay, no landing model) with
no limit / +5 % guard and each exit, vs the rank model on the same fires, vs his own lot. Size 0.40 for us. 90 % bootstrap.
Also our real k distribution on his picks (for weighting the b8b proxy). Out: bots/b14.txt"""
import pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
from plib import boot_mean, Out
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
P = Out(f"{OUT}/b14.txt")
Z = pickle.load(open(f"{OUT}/b4_res.pkl", "rb")); meta, res, PL = Z["meta"], Z["res"], [str(p) for p in Z["PL"]]
lot_by_d = collections.defaultdict(list)
for i, m in meta.items():
    if m["kind"] == "lot" and res.get(i): lot_by_d[(m["mint"], m["dslot"], m["didx"])].append(i)
F = pickle.load(open("/home/moiz/sniper-data/dv8/fires_tape.pkl", "rb"))
fid = {(meta[i]["run"], meta[i]["t"]): i for i, m in meta.items() if m["kind"] == "fire"}
rows = []
for f in F:
    Ls = lot_by_d.get((f["mint"], f["ds"], f["di"]))
    i = fid.get((f["run"], f["t"]))
    if not Ls or f["us"] is None or i is None or not res.get(i): continue
    for li in Ls:
        m = meta[li]
        rows.append(dict(code=m["code"], ahead=(f["us"][0], f["us"][1]) < (m["hslot"], m["hidx"]), k=res[i][0]["k"], fill=f["out"] == "fill", his=m["net"] * 0.40 / m["size"],
                         real=res[i][0], rank=res[i][1:]))
P("# Shared dumps: our live regular fire AND the bot's lot on the same dump (MEASURED positions; exact replay at 0.40 SOL, curve P&L, tx costs excluded)")
for c in (247, 248):
    v = [r for r in rows if r["code"] == c]
    ks = np.array([r["k"] for r in v])
    P(f"\n## bot {c}: {len(v)} shared dumps; we landed AHEAD of his buy on {100 * np.mean([r['ahead'] for r in v]):.0f}%; our live fill (+5 % guard) {100 * np.mean([r['fill'] for r in v]):.0f}%")
    P("- our REAL k (outside trades ahead) distribution: " + ", ".join(f"k {a}-{b}: {100 * np.mean((ks >= a) & (ks <= b)):.0f}%" for a, b in ((0, 0), (1, 1), (2, 3), (4, 7), (8, 12), (13, 10 ** 6))))
    P(f"- his own lot on these dumps (scaled to 0.40 SOL, after his costs): {1000 * np.mean([r['his'] for r in v]):+.2f} mSOL/lot")
    P("| exit | guard | OUR REAL position mSOL [90%] | rank model on the same fires | real - rank |"); P("|---|---|---|---|---|")
    for a, pol in enumerate(PL):
        if pol == "('HIS',)": continue
        for g in ("none", "g5"):
            re = np.array([(r["real"]["pn"][0, a] if (g == "none" or r["real"]["fill5"]) else 0.0) for r in v])
            rk = np.array([np.mean([(e["pn"][0, a] if (g == "none" or e["fill5"]) else 0.0) for e in r["rank"]]) for r in v])
            lo, hi = boot_mean(re)
            P(f"| {pol} | {g} | {1000 * re.mean():+.2f} [{1000 * lo:+.2f}..{1000 * hi:+.2f}] | {1000 * rk.mean():+.2f} | {1000 * (re - rk).mean():+.2f} |")
P.save()
