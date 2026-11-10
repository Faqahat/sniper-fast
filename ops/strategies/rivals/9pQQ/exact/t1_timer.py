#!/usr/bin/env python3
"""Reactive vs timer test. For each of its sells: is there an outside trade on the mint in slot s or s-1 (and in the same slot before it)?
Same for a random slot drawn uniformly inside the same hold window [buy+2, sell] (what a timer exit would show), and for buys a random
slot in [buy-50, buy+50] while flat.  Also: share of buys/sells whose immediately preceding outside trade is in the same slot."""
import numpy as np, xlib as X, json
rng = np.random.default_rng(0); out = {}
for r in X.RUNS:
    t = X.load(r)
    S = t.s; M = t.m; oth = ~t.own
    ko = np.where(oth)[0]; kk = (M[ko].astype(np.int64) << 32) | S[ko]
    def has_trade(m, lo, hi):  # any outside trade on mint m with slot in [lo, hi]
        a = np.searchsorted(kk, (m.astype(np.int64) << 32) | lo, "left"); b = np.searchsorted(kk, (m.astype(np.int64) << 32) | hi, "right")
        return b > a
    ob, os_ = t.ob, t.os
    # pair buys and sells in order per mint (one buy + one sell)
    bm = M[ob]; sm = M[os_]
    # match each sell to the latest buy on same mint before it
    bk = (bm.astype(np.int64) << 40) | (S[ob] * 0 + ob); sk = (sm.astype(np.int64) << 40) | os_
    j = np.searchsorted(bk, sk) - 1; ok = (j >= 0) & (bm[np.maximum(j, 0)] == sm)
    bs = S[ob[j[ok]]]; ss = S[os_[ok]]; mm = sm[ok]
    real = has_trade(mm, ss - 1, ss)
    real0 = has_trade(mm, ss, ss)
    lo = bs + 2; rs = lo + (rng.random(len(lo)) * (ss - lo + 1)).astype(np.int64)
    rnd = has_trade(mm, rs - 1, rs); rnd0 = has_trade(mm, rs, rs)
    # buys
    b_real = has_trade(bm, S[ob] - 1, S[ob]); b_real0 = has_trade(bm, S[ob], S[ob])
    rb = S[ob] + rng.integers(-50, 51, len(ob)); b_rnd = has_trade(bm, rb - 1, rb); b_rnd0 = has_trade(bm, rb, rb)
    out[r] = dict(sell_trade_in_s_or_s1=float(real.mean()), sell_same_slot=float(real0.mean()), timer_random_slot=float(rnd.mean()), timer_same=float(rnd0.mean()),
                  buy_trade_in_s_or_s1=float(b_real.mean()), buy_same=float(b_real0.mean()), buy_random=float(b_rnd.mean()), buy_random_same=float(b_rnd0.mean()))
    print(r, {k: round(v, 3) for k, v in out[r].items()}, flush=True)
json.dump(out, open("t1_timer.json", "w"), indent=1)
