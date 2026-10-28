#!/usr/bin/env python3
"""Per-day execution tables for haqq vs our two wallets (MEASURED from the raw recordings; landed + failed txs).
Out: sniper-data/haqq_dissect/exec/t3_*.txt"""
import pickle, collections, statistics as st
D = "/home/moiz/sniper-data/haqq_dissect/exec"
rows = pickle.load(open(f"{D}/txs.pkl", "rb"))
out = []
def P(*a): out.append(" ".join(str(x) for x in a))
def med(x): return st.median(x) if x else float("nan")
def q(x, p):
    x = sorted(x); return x[int(p * (len(x) - 1))] if x else float("nan")
L = 1e-6  # lamports -> mSOL
# ---------------- haqq ----------------
H = [r for r in rows if r["w"] == "haqq"]
def tier(r): return "hi" if r["fee"] >= 60000 else "lo"
P("## haqq per PKT day (10-28 = partial, to ~02:30). MEASURED. Lots = landed buys. mSOL = 1e-3 SOL.")
P(f"{'day':6} {'buyOK':>6} {'buyF':>5} {'fail%':>6} {'sellOK':>6} {'sellF':>5} {'close':>5} {'fee/buy':>8} {'tip/buy':>8} {'fee/sell':>8} {'tip/sell':>8} {'failfee/lot':>11} {'cost/lot':>8} {'buy SOL/lot':>11}")
tot = collections.Counter()
for day in sorted({r["day"] for r in H}):
    R = [r for r in H if r["day"] == day]
    bo = [r for r in R if r["kind"] == "buy" and r["ok"]]; bf = [r for r in R if r["kind"] == "buy" and not r["ok"]]
    so = [r for r in R if r["kind"] == "sell" and r["ok"]]; sf = [r for r in R if r["kind"] == "sell" and not r["ok"]]
    cl = [r for r in R if r["kind"] == "close"]
    n = len(bo) or 1
    cost = sum(r["fee"] + r["tip"] for r in bo + so + cl) + sum(r["fee"] for r in bf + sf)
    P(f"{day:6} {len(bo):6} {len(bf):5} {100*len(bf)/max(1,len(bo)+len(bf)):6.1f} {len(so):6} {len(sf):5} {len(cl):5} "
      f"{L*sum(r['fee'] for r in bo)/n:8.3f} {L*sum(r['tip'] for r in bo)/n:8.3f} {L*sum(r['fee'] for r in so)/max(1,len(so)):8.3f} {L*sum(r['tip'] for r in so)/max(1,len(so)):8.3f} "
      f"{L*sum(r['fee'] for r in bf+sf)/n:11.3f} {L*cost/n:8.3f} {1e-9*sum(r['sol'] for r in bo)/n:11.3f}")
    for k, v in (("bo", len(bo)), ("bf", len(bf)), ("so", len(so)), ("sf", len(sf)), ("cost", cost), ("failfee", sum(r['fee'] for r in bf + sf)),
                 ("buyfee", sum(r['fee'] for r in bo)), ("buytip", sum(r['tip'] for r in bo)), ("sellfee", sum(r['fee'] for r in so)), ("selltip", sum(r['tip'] for r in so)), ("closefee", sum(r['fee'] + r['tip'] for r in cl))):
        tot[k] += v
n = tot["bo"]
P(f"ALL    buys {tot['bo']} failed {tot['bf']} ({100*tot['bf']/(tot['bo']+tot['bf']):.1f}%), sells {tot['so']} failed {tot['sf']}; cost/lot {L*tot['cost']/n:.3f} mSOL = "
  f"buy fee {L*tot['buyfee']/n:.3f} + buy tip {L*tot['buytip']/n:.3f} + sell fee {L*tot['sellfee']/n:.3f} + sell tip {L*tot['selltip']/n:.3f} + failed {L*tot['failfee']/n:.3f} + close {L*tot['closefee']/n:.4f}")
P("")
P("## haqq buys by size class and fee tier (all days). fail% = failed / (landed+failed) of txs that reached the chain")
P(f"{'size SOL':10} {'tier':4} {'landed':>7} {'failed':>7} {'fail%':>6} {'fee mSOL':>8} {'tip mSOL(landed)':>16} {'cul med':>7} {'cu med':>7}")
def szc(r):
    s = r["sol"] * 1e-9
    return "<0.2" if s < 0.2 else "0.2-0.35" if s < 0.35 else "0.35-0.45" if s < 0.45 else "0.45-0.7" if s < 0.7 else ">=0.7"
# failed txs carry no TradeEvent -> size unknown; give fail rate by tier only, landed by size
B = [r for r in H if r["kind"] == "buy"]
for t in ("hi", "lo"):
    for sc in ("<0.2", "0.2-0.35", "0.35-0.45", "0.45-0.7", ">=0.7"):
        bo = [r for r in B if r["ok"] and tier(r) == t and szc(r) == sc]
        if not bo: continue
        P(f"{sc:10} {t:4} {len(bo):7} {'':>7} {'':>6} {L*med([r['fee'] for r in bo]):8.3f} {L*med([r['tip'] for r in bo]):16.3f} {med([r['cul'] or 0 for r in bo]):7.0f} {med([r['cu'] or 0 for r in bo]):7.0f}")
    bo = [r for r in B if r["ok"] and tier(r) == t]; bf = [r for r in B if not r["ok"] and tier(r) == t]
    P(f"{'ALL':10} {t:4} {len(bo):7} {len(bf):7} {100*len(bf)/(len(bo)+len(bf)):6.1f}   failed by ix index: {dict(collections.Counter(r['eidx'] for r in bf))} (4 = no-tip copy, 5 = tipped copy)")
P("")
P("## haqq landed txs by path (tip account of the landed copy) per day; buys / sells")
paths = collections.Counter(r["path"] for r in H if r["ok"] and r["kind"] in ("buy", "sell"))
top = [p for p, _ in paths.most_common(9)]
P(f"{'day':6} {'side':4} " + " ".join(f"{p[:9]:>9}" for p in top))
for day in sorted({r["day"] for r in H}):
    for side in ("buy", "sell"):
        R = [r for r in H if r["day"] == day and r["ok"] and r["kind"] == side]
        c = collections.Counter(r["path"] for r in R)
        P(f"{day:6} {side:4} " + " ".join(f"{100*c[p]/max(1,len(R)):8.1f}%" for p in top))
P("tip amounts by path (landed buys): " + "; ".join(f"{p}: {collections.Counter(round(r['tip']*1e-9,5) for r in H if r['ok'] and r['kind']=='buy' and r['path']==p).most_common(3)}" for p in top))
P("ntip per landed tx: " + str(collections.Counter(r["ntip"] for r in H if r["ok"] and r["kind"] in ("buy", "sell"))))
P("")
# ---------------- ours ----------------
P("## OUR wallets per PKT day (MEASURED on chain). Pre-send try = fee tier 5,120 lamports (CU 120k x 1,000 uL); regular fire = fee >= 505,000.")
P("pre-send fails: 6042 (price), 6001 at ix2 (INFERRED: deadline/assert guard), IllegalOwner ix3 (ATA), 6005 (curve complete)")
P(f"{'wal':4} {'day':6} {'psFill':>6} {'psFail':>7} {'fails/fill':>10} {'regFill':>7} {'regFail':>7} {'regFail%':>8} {'sells':>5} {'close':>5} {'ps cost/fill':>12} {'reg cost/fill':>13} {'sell fee':>8} {'total SOL':>9}")
OT = collections.Counter()
for w in ("FRA", "AMS"):
    for day in sorted({r["day"] for r in rows if r["w"] == w}):
        R = [r for r in rows if r["w"] == w and r["day"] == day]
        ps = [r for r in R if r["fee"] < 10000 and r["kind"] in ("buy", "other")]
        psf = [r for r in ps if r["ok"]]; psx = [r for r in ps if not r["ok"]]
        rg = [r for r in R if r["fee"] >= 400000 and r["kind"] in ("buy", "other")]
        rgf = [r for r in rg if r["ok"]]; rgx = [r for r in rg if not r["ok"]]
        se = [r for r in R if r["kind"] == "sell"]; cl = [r for r in R if r["kind"] == "close"]
        sellfee = sum(r["fee"] + r["tip"] for r in se); closefee = sum(r["fee"] for r in cl)
        nps, nrg = len(psf), len(rgf)
        # allocate sells + closes to fills proportionally (each fill has one sell)
        per_sell = sellfee / max(1, len(se)); per_close = closefee / max(1, len(cl))
        ps_cost = sum(r["fee"] + r["tip"] for r in psf) + sum(r["fee"] for r in psx) + nps * (per_sell + per_close)
        rg_cost = sum(r["fee"] + r["tip"] for r in rgf) + sum(r["fee"] for r in rgx) + nrg * per_sell
        tot = sum(r["fee"] + (r["tip"] if r["ok"] else 0) for r in R)
        P(f"{w:4} {day:6} {nps:6} {len(psx):7} {len(psx)/max(1,nps):10.1f} {nrg:7} {len(rgx):7} {100*len(rgx)/max(1,nrg+len(rgx)):8.1f} {len(se):5} {len(cl):5} "
          f"{L*ps_cost/max(1,nps):12.3f} {L*rg_cost/max(1,nrg):13.3f} {L*per_sell:8.3f} {1e-9*tot:9.3f}")
        for k, v in (("psf", nps), ("psx", len(psx)), ("psxfee", sum(r['fee'] for r in psx)), ("psfill", sum(r['fee'] + r['tip'] for r in psf)), ("rgf", nrg), ("rgx", len(rgx)),
                     ("rgxfee", sum(r['fee'] for r in rgx)), ("rgfill", sum(r['fee'] + r['tip'] for r in rgf)), ("sell", sellfee), ("nsell", len(se)), ("close", closefee), ("ncl", len(cl)), ("tot", tot)):
            OT[k] += v
P(f"ALL: pre-send fills {OT['psf']} / failed tries {OT['psx']} ({OT['psx']/OT['psf']:.0f} per fill); failed-try fees {1e-9*OT['psxfee']:.3f} SOL = {L*OT['psxfee']/OT['psf']:.3f} mSOL/fill; fill tx fee+tip {L*OT['psfill']/OT['psf']:.3f} mSOL/fill")
P(f"     regular fills {OT['rgf']} / failed fires {OT['rgx']} ({100*OT['rgx']/(OT['rgf']+OT['rgx']):.1f}% fail); failed-fire fees {L*OT['rgxfee']/max(1,OT['rgx']):.3f} mSOL each = {L*OT['rgxfee']/OT['rgf']:.3f} mSOL/fill; fill tx fee+tip {L*OT['rgfill']/OT['rgf']:.3f} mSOL/fill")
P(f"     sells {OT['nsell']} at {L*OT['sell']/OT['nsell']:.3f} mSOL each; ATA-close txs {OT['ncl']} at {L*OT['close']/max(1,OT['ncl']):.4f} mSOL; total execution spend {1e-9*OT['tot']:.3f} SOL")
P("")
P("## our regular buy txs: tip per landed buy, tips per tx, paths")
RG = [r for r in rows if r["w"] in ("FRA", "AMS") and r["fee"] >= 400000 and r["kind"] == "buy" and r["ok"]]
P("tip mSOL: " + str(collections.Counter(round(r['tip'] * L, 3) for r in RG).most_common(8)))
P("ntip: " + str(collections.Counter(r['ntip'] for r in RG)) + "  paths: " + str(collections.Counter(r['path'] for r in RG).most_common(10)))
PS = [r for r in rows if r["w"] in ("FRA", "AMS") and r["fee"] < 10000 and r["kind"] == "buy" and r["ok"]]
P("pre-send fill tip mSOL: " + str(collections.Counter(round(r['tip'] * L, 3) for r in PS).most_common(5)) + " paths: " + str(collections.Counter(r['path'] for r in PS).most_common(5)))
SE = [r for r in rows if r["w"] in ("FRA", "AMS") and r["kind"] == "sell"]
P("our sells fee: " + str(collections.Counter(r['fee'] for r in SE).most_common(3)) + " tip: " + str(collections.Counter(r['tip'] for r in SE).most_common(3)) + " cul " + str(collections.Counter(r['cul'] for r in SE).most_common(2)) + " cu med " + str(med([r['cu'] for r in SE])))
P("our regular buys cu med " + str(med([r['cu'] for r in RG])) + " cul " + str(collections.Counter(r['cul'] for r in RG).most_common(3)) + "; pre-send fill cu med " + str(med([r['cu'] for r in PS])))
P("haqq landed buys cu med " + str(med([r['cu'] for r in H if r['kind']=='buy' and r['ok']])) + " cul med " + str(med([r['cul'] for r in H if r['kind']=='buy' and r['ok'] and r['cul']])) +
  "; sells cu " + str(med([r['cu'] for r in H if r['kind']=='sell' and r['ok']])) + " cul " + str(med([r['cul'] for r in H if r['kind']=='sell' and r['ok'] and r['cul']])))
open(f"{D}/t3_tables.txt", "w").write("\n".join(out) + "\n")
print("\n".join(out))
