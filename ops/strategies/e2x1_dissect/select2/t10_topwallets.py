#!/usr/bin/env python3
"""select2 t10: the wallets that trigger him most. Per wallet (whole tape, universe rows samp|y): his follow count, the wallet's
universe trades (weighted), his take rate, sim P&L (66 ms, 34 s, phi 0.2) of taken vs not-taken trades. Out: t10.json"""
import sys, json, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select2"); from lib import *
U = dict(np.load(f"{OUT}/U2.npz")); S = dict(np.load(f"{OUT}/sim_66.npz")); MN, US = names()
y = U["y"].astype(bool); samp = U["samp"].astype(bool); rows = samp | y; wt = np.where(y, 1.0, 25.0); u = U["user"]
TE = U["bt"] >= U["bt"].max() - 86400
cnt = np.bincount(u[y]); top = np.argsort(-cnt)[:25]
out = []
for ui in top:
    m = rows & (u == ui); tk = m & y; nt = m & ~y
    d = dict(wallet=US[ui], follows=int(cnt[ui]), trades_w=float(wt[m].sum()), take_rate=float(cnt[ui] / wt[m].sum()), buy_share_taken=float(U["is_buy"][tk].mean()),
             test_follows=int((tk & TE).sum()), test_take_rate=float((tk & TE).sum() / max(wt[m & TE].sum(), 1)),
             taken_sim34=float(1000 * S["tier|34s|0.2|pnl"][tk].mean()), not_taken_sim34=float(1000 * np.average(S["tier|34s|0.2|pnl"][nt], weights=wt[nt])) if nt.any() else None,
             taken_g94=float(100 * np.clip(U["g94"][tk], -1, 5).mean()), not_taken_g94=float(100 * np.average(np.clip(U["g94"][nt], -1, 5), weights=wt[nt])) if nt.any() else None,
             cw541=bool(U["u_cw541"][m][0]), census_tot=float(U["u_census_tot"][m][0]), taken_age_med=float(np.median(U["age_s"][tk])), taken_sol_med=float(np.median(U["sol"][tk])))
    out.append(d); print(f"{d['wallet'][:8]} follows {d['follows']:4d} take {100*d['take_rate']:5.2f}% (test {100*d['test_take_rate']:5.2f}%) buys {100*d['buy_share_taken']:3.0f}% | sim34 taken {d['taken_sim34']:+6.1f} not {d['not_taken_sim34'] if d['not_taken_sim34'] is None else round(d['not_taken_sim34'],1)} | g94 taken {d['taken_g94']:+5.1f} not {round(d['not_taken_g94'],1) if d['not_taken_g94'] is not None else None} | cw {d['cw541']} census {d['census_tot']:+.0f} age {d['taken_age_med']:.0f}s")
allw = rows & np.isin(u, top[:10]); print("top10 wallets: share of his picks", float(np.isin(u[y], top[:10]).mean()), "take rate", float((allw & y).sum() / wt[allw].sum()))
json.dump(out, open(f"{OUT}/t10.json", "w"), indent=1)
