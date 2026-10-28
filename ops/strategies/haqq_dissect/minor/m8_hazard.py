#!/usr/bin/env python3
"""MINOR step 8 (read-only): exit HAZARD of the short-hold minor bots (226, 231, 251, 252, 244 first sell): for every slot s after
the buy while the lot is still fully held, the state at the END of slot s-1 (what a bot sees when it decides for slot s):
  ret (exact curve value of his tokens / cost - 1), peak ret so far, outside buys / buy SOL / sells in slot s-1, slots held,
  slots since the last outside buy; event = his first same-code sell lands in slot s. MEASURED.
Hazard tables per feature bucket show what precedes his sells (timer vs wave vs TP/SL).
Out: minor/m8.txt"""
import pickle, sys, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
import xlib as X
from plib import Out
OUT = "/home/moiz/sniper-data/haqq_dissect/minor"
CODES = {226: 30, 231: 30, 251: 30, 252: 30, 244: 140}


def main():
    t0 = time.time()
    P = Out(f"{OUT}/m8.txt")
    lots = pickle.load(open(f"{OUT}/m2_lots.pkl", "rb"))
    R, MI, span, CC = X.tape(); H = MI["who"]["haqq"]; ours = [MI["who"]["FRA"], MI["who"]["AMS"]]
    bym = collections.defaultdict(list)
    for l in lots:
        if l["code"] in CODES and l["sells"] and not l["mayhem"]: bym[l["mint"]].append(l)
    H_ = collections.defaultdict(list)
    for m, ls in bym.items():
        M = X.Mint(m)
        o = ~np.isin(M.us, ours + [H])
        for l in ls:
            k = l["k"]; s0 = int(M.sl[k]); smax = CODES[l["code"]]
            sell_s = l["sells"][0][0]
            if sell_s > smax: sell_s_c = None
            else: sell_s_c = sell_s
            V0, T0 = M.vsp[k], M.vtp[k]; fee = M.fee[k] if M.fee[k] > 0 else X.FEE; tok = M.tk[k]
            K = V0 * T0; V = V0 + l["cost"] / (1 + fee); T = K / V
            js = np.flatnonzero(o & (np.arange(M.n) > k) & (M.sl <= s0 + smax))
            val = lambda: (V - K / (T + tok)) * (1 - fee) / l["cost"] - 1
            ret = val(); peak = ret; last_b = 0; a = 0
            for s in range(1, smax + 1):
                # trades of slot s0+s-1 (after his buy) are known at the start of slot s
                nb = 0; bs = 0.0; ns = 0
                while a < len(js) and M.sl[js[a]] <= s0 + s - 1:
                    j = js[a]
                    if M.bu[j]: V += M.so[j]; T = K / V; nb += 1; bs += M.so[j]
                    else: T += M.tk[j]; V = K / T; ns += 1
                    a += 1
                ret = val(); peak = max(peak, ret)
                if nb: last_b = s - 1
                ev = sell_s_c is not None and sell_s_c == s
                H_[l["code"]].append((s, ret, peak, nb, bs, ns, s - 1 - last_b, ev, l["spend"]))
                if sell_s_c is not None and s >= sell_s_c: break
    P("# Exit hazard per slot (MEASURED): P(first sell lands in slot s | still holding), state at the end of slot s-1")
    for c in CODES:
        A = np.array(H_[c], float)
        if not len(A): continue
        s, ret, peak, nb, bs, ns, since, ev = (A[:, i] for i in range(8))
        ev = ev > 0.5
        P(f"\n## code {c}: {len(A):,} lot-slots, {int(ev.sum()):,} sells (within {CODES[c]} slots)")
        def tab(name, x, edges):
            cells = []
            for lo, hi in zip(edges[:-1], edges[1:]):
                m = (x >= lo) & (x < hi)
                if m.sum() >= 30: cells.append(f"[{lo:g},{hi:g}) {100 * ev[m].mean():.0f}% (n {int(m.sum())})")
            P(f"- {name}: " + "; ".join(cells))
        tab("slot s", s, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16, 17, 20, 21, 25, 31, 33, 40, 64, 65, 100, 141])
        tab("ret", ret, [-1, -0.2, -0.1, -0.05, -0.02, 0, 0.02, 0.05, 0.1, 0.2, 0.5, 9])
        tab("peak-ret (drawdown from peak)", peak - ret, [0, 0.01, 0.03, 0.05, 0.1, 0.2, 9])
        tab("outside buys in slot s-1", nb, [0, 1, 2, 3, 5, 99])
        tab("outside sells in slot s-1", ns, [0, 1, 2, 3, 99])
        tab("slots since last outside buy", since, [0, 1, 2, 3, 5, 10, 999])
        # two-way: s>=2, by nb==0 and ret>0
        m2 = s >= 2
        for nm, cond in (("no buys last slot & ret>0", (nb == 0) & (ret > 0)), ("no buys last slot & ret<=0", (nb == 0) & (ret <= 0)),
                         ("buys last slot & ret>0", (nb > 0) & (ret > 0)), ("buys last slot & ret<=0", (nb > 0) & (ret <= 0))):
            m = m2 & cond
            P(f"  s>=2, {nm}: hazard {100 * ev[m].mean():.0f}% (n {int(m.sum())})")
    P.save(); print(f"done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
