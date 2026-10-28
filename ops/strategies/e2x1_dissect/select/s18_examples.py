#!/usr/bin/env python3
"""SELECT s18: 6 example buys per family (seeded random, 3 winners + 3 losers where possible) with GMGN token links, solscan links for
his buy and his closing sell (signatures looked up in the raw recorder chunks by slot+index), the trigger and the outcome.
Out: examples.md, examples.json"""
import sys, pickle, json, glob, os, gzip, re, bisect
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
from tl import cols
D = load(); w = int(D["wid"]); MN, US = names()
X = cols(pickle.load(open(f"{OUT}/buys.pkl", "rb"))); S = pickle.load(open(f"{OUT}/speed.pkl", "rb")); fam = np.load(f"{OUT}/family.npy")
NM = json.load(open(f"{OUT}/creates_all.json"))
files = sorted(glob.glob("/home/moiz/sniper-data/collect/run_2026102*/txs/txs_*.jsonl.gz"), key=lambda f: int(os.path.basename(f)[4:14]))
starts = [int(os.path.basename(f)[4:14]) for f in files]
def sig_of(row):
    s, i, t = int(D["slot"][row]), int(D["idx"][row]), int(D["bt"][row])
    k = bisect.bisect_right(starts, t) - 1
    pat = f'{{"s":{s},"i":{i},'
    for f in files[max(k - 1, 0):k + 2]:
        try:
            with gzip.open(f, "rt") as fh:
                for line in fh:
                    if line.startswith(pat):
                        m = re.search(r'"sig":"([^"]+)"', line); return m.group(1) if m else None
        except EOFError: pass
    return None
rng = np.random.default_rng(7)
out = {}; md = []
us = D["user"]; bu = D["buy"].astype(bool); mi = D["mint"]
for f in sorted(set(fam.tolist())):
    idx = np.flatnonzero(fam == f)
    win = idx[X["lot_pnl"][idx] > 0]; los = idx[X["lot_pnl"][idx] <= 0]
    pick = list(rng.choice(win, min(3, len(win)), replace=False)) + list(rng.choice(los, min(3, len(los)), replace=False))
    md.append(f"\n### {f}\n| time PKT | token | age s | trigger (3 slots before) | lag | buy SOL | lot P&L | hold s | buy tx | sell tx |\n|---|---|---|---|---|---|---|---|---|---|")
    out[f] = []
    for k in pick:
        R = int(X["row"][k]); m = int(mi[R]); a, e = span(D, m)
        q = np.flatnonzero((us[R + 1:e] == w) & ~bu[R + 1:e]); Sr = R + 1 + int(q[0]) if len(q) else None
        sb = sig_of(R); ss = sig_of(Sr) if Sr is not None else None
        s5 = S[k]; nm = NM.get(MN[m], {})
        trig = f"{'buy' if s5.get('trg_buy') else 'sell'} {s5.get('trg_sol', 0):.2f} SOL ({100*s5.get('trg_imp', 0):+.0f}%)"
        lag = f"{s5.get('lag_trg_sl', '?')} sl / {s5.get('lag_trg_ms', float('nan')):.0f} ms"
        tok = f"[{(nm.get('symbol') or MN[m][:6])[:12]}](https://gmgn.ai/sol/token/{MN[m]})"
        bl = f"[buy](https://solscan.io/tx/{sb})" if sb else "n/a"; sl_ = f"[sell](https://solscan.io/tx/{ss})" if ss else "none"
        md.append(f"| {pkt(X['bt'][k])} | {tok} | {X['age_s'][k]} | {trig} | {lag} | {X['sol'][k]:.3f} | {X['lot_pnl'][k]:+.4f} | {X['hold_s'][k]} | {bl} | {sl_} |")
        out[f].append(dict(mint=MN[m], buy_sig=sb, sell_sig=ss, bt=int(X["bt"][k]), pnl=float(X["lot_pnl"][k])))
open(f"{OUT}/examples.md", "w").write("\n".join(md)); json.dump(out, open(f"{OUT}/examples.json", "w"))
print("\n".join(md))
