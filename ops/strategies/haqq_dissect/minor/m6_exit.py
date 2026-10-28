#!/usr/bin/env python3
"""MINOR step 6 (read-only): exit footprints of every minor bot (MEASURED on the exit tape, his actual entries and sells).
Per lot and per same-code sell (from m1): slot / ms after the buy; outside buys between his buy and the sell (count, SOL), ms since
the last outside buy before the sell (wave signature), the lot's exact curve value just before the sell (ret_at_sell) and its max /
min along the way, whether ANOTHER haqq code sold the mint within 424 ms before (sibling exit), fraction sold.
Also replays simple exits from his actual entry (exact curve, his tokens, outside trades only; landing = 60 ms after the trigger for
reactive rules, slot start + 100 ms for timers) to find which rule reproduces his exit TIMING (share within +-1 slot) and P&L.
Rules: T n (timer n slots); WAVE g (from 2 slots after the buy, sell at the first g-ms gap with no outside buy; cap 20 s);
TP x / SL x (first time value >= 1+x / <= 1-x, cap = his own exit); SIB (sell when another haqq code sells the mint).
Out: minor/m6.txt, minor/m6.pkl"""
import pickle, sys, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
import xlib as X
from plib import Out
OUT = "/home/moiz/sniper-data/haqq_dissect/minor"
CODES = (226, 231, 244, 251, 252, 249, 234)
SMS = 212.0; RD = 60.0; TD = 100.0


def main():
    t0 = time.time()
    P = Out(f"{OUT}/m6.txt")
    lots = pickle.load(open(f"{OUT}/m2_lots.pkl", "rb"))
    R, MI, span, CC = X.tape(); H = MI["who"]["haqq"]; ours = [MI["who"]["FRA"], MI["who"]["AMS"]]
    # haqq sells per mint with code
    TX = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/exec/txs.pkl", "rb"))
    code = {(r["s"], r["i"]): (r["cup"] or 0) % 1000 for r in TX if r["w"] == "haqq" and r["ok"]}
    del TX
    bym = collections.defaultdict(list)
    for l in lots:
        if l["code"] in CODES and l["sells"] and not l["mayhem"]: bym[l["mint"]].append(l)
    rows = []
    for n_m, (m, ls) in enumerate(bym.items()):
        M = X.Mint(m)
        o = ~np.isin(M.us, ours + [H])
        hs = np.flatnonzero((M.us == H) & ~M.bu)
        hs_cc = M.cc[hs]; hs_code = np.array([code.get((int(M.sl[k]), int(M.ix[k])), -1) for k in hs])
        for l in ls:
            k = l["k"]; c0 = M.cc[k]
            V0, T0 = M.vsp[k], M.vtp[k]
            fee = M.fee[k] if M.fee[k] > 0 else X.FEE
            tok = M.tk[k]
            first = l["sells"][0]; ts = first[1]          # ms after buy (chain clock) of his first sell
            js = np.flatnonzero(o & (np.arange(M.n) > k) & (M.cc <= c0 + max(ts, 20000) + 1))
            # exact value path: state after his buy, outside rows only (his other rows ignored)
            K = V0 * T0; V = V0 + l["cost"] / (1 + fee); T = K / V
            vals = np.empty(len(js));
            for a, j in enumerate(js):
                if M.bu[j]: V += M.so[j]; T = K / V
                else: T += M.tk[j]; V = K / T
                vals[a] = (V - K / (T + tok)) * (1 - fee) / l["cost"]
            v_pre = (V0 + l["cost"] / (1 + fee) - K / (K / (V0 + l["cost"] / (1 + fee)) + tok)) * (1 - fee) / l["cost"]
            dcc = M.cc[js] - c0; bu = M.bu[js]
            def val_at(t):
                q = np.searchsorted(dcc, t, side="right") - 1
                return v_pre if q < 0 else vals[q]
            pre = dcc < ts
            bts = dcc[bu & pre]
            sib = hs_cc[(hs_code != l["code"]) & (hs_cc >= c0) & (hs_cc <= c0 + ts) & (hs_cc >= c0 + ts - 424)]
            r = dict(code=l["code"], li=id(l), day=l["day"], spend=l["spend"], net=l["net"], ts=ts, sl=first[0], f1=first[2], nsell=len(l["sells"]),
                     nb=int(bts.size), bsol=float(M.so[js][bu & pre].sum()), gap=float(ts - bts[-1]) if bts.size else None,
                     first_b=float(bts[0]) if bts.size else None, ret=float(val_at(ts - 1)) - 1, vmax=float(max([v_pre] + list(vals[pre]))) - 1,
                     vmin=float(min([v_pre] + list(vals[pre]))) - 1, sib=bool(sib.size), sig=l["sig"], ssig=first[4], ms=l["ms"], bt=l["bt"], cost=l["cost"])
            # rule replays (value ratio at landing) + timing
            off = (c0 % SMS)
            def tslot(n): return n * SMS - off + TD
            alt = {}
            for n in (2, 3, 4, 5, 6, 8, 10, 16, 20, 32, 64, 100, 200):
                alt[("T", n)] = tslot(n)
            ball = dcc[bu]
            for g in (200, 300, 424, 600, 1000):
                start = tslot(2) - TD
                later = ball[ball > start - g]
                if not later.size: t = start
                else:
                    gaps = np.diff(np.concatenate([later, [np.inf]])); j = int(np.argmax(gaps >= g)); t = max(later[j] + g, start)
                alt[("WAVE", g)] = min(t, 20000) + RD
            for x in (0.03, 0.05, 0.10, 0.20):
                hit = np.flatnonzero(vals >= 1 + x)
                alt[("TP", x)] = min(dcc[hit[0]] + RD, ts) if hit.size else ts
                hit = np.flatnonzero(vals <= 1 - x)
                alt[("SL", x)] = min(dcc[hit[0]] + RD, ts) if hit.size else ts
            sib_all = hs_cc[(hs_code != l["code"]) & (hs_cc > c0)]
            alt[("SIB",)] = (sib_all[0] - c0 + RD) if sib_all.size else 20000 + RD
            r["alt"] = {k2: (float(t), float(val_at(t)) - 1) for k2, t in alt.items()}
            r["his_val"] = float(val_at(ts - 1)) - 1
            rows.append(r)
        if n_m % 3000 == 0: print(f"  {n_m:,}/{len(bym):,} mints ({time.time() - t0:.0f}s)", flush=True)
    pickle.dump(rows, open(f"{OUT}/m6.pkl", "wb"))
    P("# Minor bots: exit footprints (MEASURED, his actual entries/sells; curve value = exact replay of his tokens vs outside trades)")
    for c in CODES:
        v = [r for r in rows if r["code"] == c]
        if not v: continue
        P(f"\n## code {c}: {len(v):,} sold lots")
        gp = [r["gap"] for r in v if r["gap"] is not None]
        P(f"- first sell: slots p10/50/90 {np.percentile([r['sl'] for r in v], [10, 50, 90]).tolist()}; outside buys before it p50 {np.median([r['nb'] for r in v]):.0f}; "
          f"no outside buy at all {100 * np.mean([r['nb'] == 0 for r in v]):.0f}%; ms since last outside buy p10/50/90 {np.percentile(gp, [10, 50, 90]).round(0).tolist() if gp else '-'}")
        P(f"- lot value just before his sell: p10/50/90 {np.percentile([r['ret'] for r in v], [10, 50, 90]).round(3).tolist()}; max before {np.percentile([r['vmax'] for r in v], [10, 50, 90]).round(3).tolist()}; "
          f"sold within 1% of the path max {100 * np.mean([r['ret'] >= r['vmax'] - 0.01 for r in v]):.0f}%; another haqq code sold <= 424 ms before {100 * np.mean([r['sib'] for r in v]):.0f}%")
        P(f"- partial first sells (0.45-0.55) {100 * np.mean([0.45 <= r['f1'] <= 0.55 for r in v]):.0f}%")
        # timing agreement and P&L per rule
        keys = list(v[0]["alt"].keys())
        P("| rule | sells within +-1 slot of his | rule value P&L SOL (his tokens, curve only) |")
        P("|---|---|---|")
        his = sum(r["his_val"] * r["cost"] for r in v)
        P(f"| HIS (value just before his own first sell) | 100% | {his:+.2f} |")
        sc = []
        for kk in keys:
            agree = np.mean([abs(r["alt"][kk][0] - r["ts"]) <= SMS * 1.0 for r in v])
            pn = sum(r["alt"][kk][1] * r["cost"] for r in v)
            sc.append((agree, kk, pn))
        for agree, kk, pn in sorted(sc, key=lambda x: -x[0])[:12]:
            P(f"| {kk} | {100 * agree:.0f}% | {pn:+.2f} |")
    P.save(); print(f"done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
