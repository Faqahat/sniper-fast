#!/usr/bin/env python3
# r18: REAL positions of other wallets on the SAME 309 dumps we fired on: every non-us buy in the first ~3 slots after the dump,
# by its landing position (block-position ms after the dump). For each: (1) its real tokens valued with OUR exit (time limit
# at its landing slot + 5, index 148; no counterfactual: their position really existed, the tape after it is real), and
# (2) its own real exit (its sells of that token in the next 40 slots, FIFO, rest marked to market). % of the SOL it spent,
# pump fees both sides, no tx fees. Shows on real money how the value of a position falls with landing order on these dumps.
import sys, os, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S

if __name__ == "__main__":
    P = json.load(open(f"{R.WORK}/pertrade.json"))
    TPS = {tag: S.Tapes(tag) for tag in ("NEW", "OLD")}
    B = [(0, 10), (10, 20), (20, 35), (35, 50), (50, 75), (75, 100), (100, 150), (150, 300)]
    acc = collections.defaultdict(list); ours = collections.defaultdict(list)
    for o in P:
        TP = TPS[o["tape"]]; t, j0 = TP.find(o["mint"], o["dump_slot"], o["dump_idx"], o.get("sell")); tp = TP.token(t)
        a0 = float(tp["arr"][j0]); n = tp["n"]
        for x in range(j0 + 1, n):
            if tp["s"][x] > o["dump_slot"] + 2: break
            if not tp["buy"][x] or tp["ours"][x]: continue
            L = float(tp["arr"][x]) - a0
            sol = float(tp["sol"][x]); q = float(tp["tokn"][x]); fr = float(tp["fr"][x]); cost = sol * (1 + fr)
            if cost < 0.05e9: continue
            s_in = int(tp["s"][x]); key = (s_in + 5) * 100000 + 148
            # (1) our exit on the real tape: value of q just before key (state after the last trade before key, any wallet)
            V = T = None; frs = fr
            for y in range(x, n):
                if tp["SI"][y] >= key: break
                V = float(tp["vsol"][y]); T = float(tp["vtok"][y]); frs = float(tp["fr"][y])
            v1 = V * q / (T + q) * (1 - frs)
            # (2) its own exit: its sells of this token within 40 slots, FIFO on this buy's tokens
            u = tp["uid"][x]; left = q; got = 0.0
            for y in range(x + 1, n):
                if tp["s"][y] > s_in + 40 or left <= 0: break
                if tp["uid"][y] == u and not tp["buy"][y]:
                    k = min(left, float(tp["tokn"][y])); got += float(tp["sol"][y]) * (k / float(tp["tokn"][y])) * (1 - float(tp["fr"][y])); left -= k
            if left > 0:
                yl = min(n - 1, int(np.searchsorted(tp["SI"], (s_in + 41) * 100000)) - 1)
                Vl = float(tp["vsol"][yl]); Tl = float(tp["vtok"][yl]); got += Vl * left / (Tl + left) * (1 - float(tp["fr"][yl]))
            for lo, hi in B:
                if lo <= L < hi:
                    acc[(lo, hi)].append(((v1 - cost) / cost, (got - cost) / cost, cost / 1e9)); break
        # our own real fills: % of spend (curve, after pump fees, before tx costs) by our landing
        if o["live_fill"] and o.get("sell_received"):
            for lo, hi in B:
                if lo <= o["L_meas"] < hi: ours[(lo, hi)].append((o["sell_received"] - o["size"]) / o["size"]); break
    print("rival buys (>= 0.05 SOL) on our 309 dumps, by landing position after the dump (block-position ms):")
    print(f"{'landing':>10s} {'buys':>5s} {'SOL':>6s} | {'our exit (hold 5 slots)':>24s} | {'their own exit (40 slots)':>26s} | {'OUR fills':>16s}")
    for b in B:
        a = acc[b]
        if not a: continue
        x1 = np.array([z[0] for z in a]); x2 = np.array([z[1] for z in a]); w = np.array([z[2] for z in a])
        oo = ours.get(b, [])
        print(f"{b[0]:4d}-{b[1]:<4d}ms {len(a):5d} {w.sum():6.1f} | mean {100 * x1.mean():+5.1f}% (wtd {100 * (x1 * w).sum() / w.sum():+5.1f}%) win {100 * np.mean(x1 > 0):3.0f}% | "
              f"mean {100 * x2.mean():+5.1f}% (wtd {100 * (x2 * w).sum() / w.sum():+5.1f}%) win {100 * np.mean(x2 > 0):3.0f}% | "
              + (f"n {len(oo):3d} {100 * np.mean(oo):+5.1f}%" if oo else ""))
    json.dump({f"{b[0]}-{b[1]}": dict(n=len(acc[b]), ourexit=float(np.mean([z[0] for z in acc[b]])) if acc[b] else None,
                                      ownexit=float(np.mean([z[1] for z in acc[b]])) if acc[b] else None,
                                      sol=float(sum(z[2] for z in acc[b])), ours=ours.get(b, [])) for b in B},
              open(f"{R.WORK}/rivals.json", "w"))
