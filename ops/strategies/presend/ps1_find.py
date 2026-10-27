#!/usr/bin/env python3
# Step 1a: which wallets' buys land within ~10 ms (block-position proxy) after a >= 2% dump in the SAME slot, very often?
# For every successful buy in the tapes: the latest same-slot >= 2% sell on that token before it -> dt (ms, arrival proxy),
# rank within the post-dump queue. Per wallet (uid): buys, fast buys (<= 10 ms after a >= 2% dump), share, tokens, days.
# -> presend/ps1_wallets.json (top uids) + stdout table
import sys, json, collections
import numpy as np
import ps_common as C
if __name__ == "__main__":
    agg = collections.defaultdict(lambda: np.zeros(8))      # buys, fast2, fast465, fast2_first, sol_fast, days-bitmask, n_tok_fast, first-after-dump
    toks = collections.defaultdict(set); per_day = collections.defaultdict(dict)
    for day in ("R1", "R2", "R3", "R4"):
        d = C.load(day); n = len(d["s"])
        dump = (d["buy"] == 0) & (d["move"] <= -2.0)
        idx = np.where(dump, np.arange(n), -1); last = np.maximum.accumulate(idx)
        prev = np.concatenate([[-1], last[:-1]])                       # latest dump strictly before j
        okp = prev >= 0
        same = np.zeros(n, bool); same[okp] = (d["tok"][prev[okp]] == d["tok"][okp]) & (d["s"][prev[okp]] == d["s"][okp])
        b = d["buy"] == 1
        dt = np.full(n, np.inf); dt[same] = d["arr"][same] - d["arr"][prev[same]]
        mv = np.zeros(n); mv[same] = d["move"][prev[same]]
        # first buy after the dump (no other buy between)
        bidx = np.where(b, np.arange(n), -1); lastb = np.concatenate([[-1], np.maximum.accumulate(bidx)[:-1]])
        first = same & (lastb < prev)
        fast = b & same & (dt <= 10.0); fast465 = fast & (mv <= -4.65)
        u = d["uid"]
        U, inv = np.unique(u, return_inverse=True)
        nb = np.bincount(inv, weights=b, minlength=len(U)); nf = np.bincount(inv, weights=fast, minlength=len(U))
        nf4 = np.bincount(inv, weights=fast465, minlength=len(U)); nff = np.bincount(inv, weights=fast & first, minlength=len(U))
        sf = np.bincount(inv, weights=np.where(fast, d["sol"] / 1e9, 0), minlength=len(U))
        tw = d["t"][C.in_win(d, d["t"])]; hrs = (tw.max() - tw.min()) / 3600
        for k in np.flatnonzero(nf >= 3):
            a = agg[int(U[k])]; a[0] += nb[k]; a[1] += nf[k]; a[2] += nf4[k]; a[3] += nff[k]; a[4] += sf[k]
            per_day[int(U[k])][day] = int(nf[k])
        for j in np.flatnonzero(fast): toks[int(u[j])].add((day, int(d["tok"][j])))
        # all-dump context: how many >= 2% dumps had ANY buy within 10 ms in the same slot
        nd = dump.sum(); fd = np.unique(prev[fast]).size
        print(f"{day}: trades {n}, >=2% dumps {nd}, dumps followed by a buy <= 10 ms in the same slot {fd} ({100 * fd / nd:.1f}%), "
              f"fast buys {fast.sum()} by {len(set(u[fast].tolist()))} wallets, {hrs:.1f} h", flush=True)
        del d
    known = {C.crc(w): w for w in C.PRE}
    try:
        for w in json.load(open("/home/moiz/sniper-data/competitors2/dossier.json")): known.setdefault(C.crc(w), w)
    except Exception: pass
    rows = []
    for uid, a in agg.items():
        if a[1] < 20: continue
        rows.append(dict(uid=uid, w=known.get(uid, ""), buys=int(a[0]), fast=int(a[1]), share=a[1] / max(a[0], 1), fast465=int(a[2]),
                         first=int(a[3]), sol_fast=round(a[4], 2), ntok=len(toks[uid]), days=per_day[uid]))
    rows.sort(key=lambda r: -r["fast"])
    print(f"\nwallets with >= 20 buys landing <= 10 ms after a >= 2% same-slot dump (all 4 tapes): {len(rows)}")
    print(f"{'uid':>10s} {'wallet':10s} {'buys':>6s} {'fast':>5s} {'share':>5s} {'>=4.65':>6s} {'1st':>5s} {'SOLfast':>7s} {'tok':>5s}  per day")
    for r in rows[:60]:
        print(f"{r['uid']:>10d} {r['w'][:9]:10s} {r['buys']:6d} {r['fast']:5d} {r['share']:5.2f} {r['fast465']:6d} {r['first']:5d} {r['sol_fast']:7.1f} {r['ntok']:5d}  {r['days']}")
    json.dump(rows, open(f"{C.OUT}/ps1_wallets.json", "w"))
