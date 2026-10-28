#!/usr/bin/env python3
"""pos step 8 (read-only): 're-arm pre-send on tokens that already paid' -- a PROXY on the tape (INFERRED; the T2 whale-BUY trigger
is not rebuilt here). Whale dumps = dv8 uni candidates whose single sell is >= 6% of supply (the pre-send engine arms on
>= 6% holders and buys their dump in the same slot). Mayhem excluded, usable hours only.
Pre-send-style entry = right after the dump (our pre-send fills land a median 29 ms after it, MEASURED) -> 'ideal' entry, exact
follower model, 2-slot timer exit (the pre-send exit), 0.40 SOL. This is an UPPER bound per fill; the live/replay ratio for
pre-send was ~0.6 (probe 3: live = 62% of the size-matched shadow, MEASURED earlier) -- shown as a 0.6x row.
Groups: the token's 1st whale dump (what pre-send takes today: one window per token) vs later whale dumps on the same token,
split by whether the PREVIOUS whale dump's 2-slot ideal result was >= +5% (paid; known 2 slots after it).
Out: p8.txt"""
import sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import p6_rules as R6
import dv8lib as L
from plib import Out, OUT, day_name, boot_sum
P = Out(f"{OUT}/p8.txt")


def main():
    Z = np.load(f"{L.D}/uni.npz"); X = Z["X"]; M = Z["M"]; R = Z["R"]; ES = Z["ES"]
    hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
    bt = M["bt"].astype(np.int64); usable = np.isin((bt + 18000) // 3600 * 3600 - 18000, list(good)) & ~np.load(f"{L.D}/mayhem.npy")
    day = ((bt - L.DAY0) // 86400).astype(int)
    wh = np.flatnonzero(X[:, 2] >= 6.0)
    tape = R6.Tape()
    pn = np.full(len(M), np.nan)
    for i in wh:
        r = int(R[i, 0]); q = tape.qrow(r, int(M["end"][i]), int(ES[i, 0]), 2)
        pn[i] = tape.joint([(r, q)])[0]
    # order of whale dumps per token; previous whale dump's result (known 2 slots later)
    o = wh[np.lexsort((M["cc"][wh], M["mint"][wh]))]
    kw = {}; prevpay = {}; prevslot = {}
    last = None
    for i in o:
        m = int(M["mint"][i])
        if last is None or last[0] != m: kw[i] = 1; last = (m, i); continue
        kw[i] = kw[last[1]] + 1; prevpay[i] = pn[last[1]]; prevslot[i] = int(M["slot"][last[1]]); last = (m, i)
    rows = [i for i in wh if usable[i] and np.isfinite(pn[i])]
    P(f"# Pre-send re-arm proxy: whale dumps (single sell >= 6% supply) {len(wh):,}; usable non-mayhem {len(rows):,}")
    P("Ideal (right-after-dump) entry, 2-slot exit, 0.40 SOL, curve P&L before tx costs (mSOL per fill). INFERRED upper bound.")
    groups = [("1st whale dump on the token (pre-send today)", lambda i: kw[i] == 1),
              ("2nd+ whale dump, previous one paid >= +5%, closed", lambda i: kw[i] >= 2 and prevpay.get(i, -1) >= 0.02 and M["slot"][i] > prevslot[i] + 2),
              ("2nd+ whale dump, previous one < +5%, closed", lambda i: kw[i] >= 2 and prevpay.get(i, 1) < 0.02 and M["slot"][i] > prevslot[i] + 2),
              ("2nd+ whale dump within 2 slots of the previous", lambda i: kw[i] >= 2 and M["slot"][i] <= prevslot[i] + 2)]
    P("| group | dumps | mean mSOL [90%] | x0.6 (live/replay ratio) | win | D0..D5 mean mSOL | days > 0 |"); P("|---|---|---|---|---|---|---|")
    for nm, f in groups:
        v = [i for i in rows if f(i)]
        if not v: continue
        x = pn[v]; lo, hi = boot_sum(x / len(x))
        pd = [1000 * np.mean(pn[[i for i in v if day[i] == d]]) if any(day[i] == d for i in v) else float("nan") for d in range(6)]
        P(f"| {nm} | {len(v):,} | {1000 * x.mean():+.2f} [{1000 * lo:+.2f}..{1000 * hi:+.2f}] | {600 * x.mean():+.2f} | {100 * np.mean(x > 0):.0f}% | "
          + " ".join(f"{p:+.1f}" for p in pd) + f" | {sum(p > 0 for p in pd if p == p)}/6 |")
    P("\nPer day counts and sum (SOL, ideal, before costs) of the 're-arm on paid' group:")
    v = [i for i in rows if groups[1][1](i)]
    for d in range(7):
        w = [i for i in v if day[i] == d]
        if w: P(f"- {day_name(d)}: {len(w)} dumps, sum {pn[w].sum():+.2f} SOL ideal, x0.6 {0.6 * pn[w].sum():+.2f}")
    P.save()


if __name__ == "__main__":
    main()
