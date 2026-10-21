# READ-ONLY (host, no RPC): per-wallet round trips + PnL from txs_multi.py rows, joined with our watched launches
# (discover.py launches.json / cand.json) and the engines' DETECT universe (create slot, verdict, dev buy).
# PnL per trade = sells*(1-f) - buys*(1+f) - tx fees (base+priority) of its txs - top-level transfers from the wallet in those
# txs (tips); f = pump fee + creator fee from the TradeEvent. A tx with several of the wallet's TradeEvents is split evenly.
# Token-account rent is excluded (the wallets reclaim it in separate close txs); pnl_wd (sum of the wallet's lamport deltas
# of the trade's txs) is kept as a check. Failed-tx fees = sample mean x failed count in the fetched span (wallet-level cost).
# usage: python3 -I comp_trades.py <wallets.txt> <w_dir> <tipmap.json> <launches.json> <cand.json> <detect_univ.json> <out_dir>
import sys, os, json, statistics, collections, time
WF, WD, TMF, LJ, CJ, DUJ, OUT = sys.argv[1:8]
AG = 459653000
TM = json.load(open(TMF)); LA = {l["mint"]: l for l in json.load(open(LJ))}
CA = {c["wallet"]: {t["mint"]: t for t in c["trades"]} for c in json.load(open(CJ))}
DU = json.load(open(DUJ))
RENT = 2039280


def route(dst):
    if dst in TM: return TM[dst]
    if dst.lower().startswith("b1oom"): return "b1oom?"
    if dst.startswith(("noz", "TEMPa")): return "nozomi"
    if dst.startswith("moon"): return "lunar"
    if dst.startswith("FLaSH"): return "flashblock"
    return "other:" + dst[:6]


q = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(p * len(xs)))] if xs else None
med = lambda xs: statistics.median(xs) if xs else None
allrows = []; summ = []
for W in [l.split()[0] for l in open(WF) if l.strip() and not l.startswith("#")]:
    fn = os.path.join(WD, W + ".txs.jsonl"); sf = os.path.join(WD, W + ".sigs.json")
    if not os.path.exists(fn): continue
    R = [json.loads(l) for l in open(fn)]; SG = json.load(open(sf))
    ok = [r for r in R if not r["err"]]; fl = [r for r in R if r["err"]]
    if not ok: continue
    t0 = min(r["bt"] for r in ok if r["bt"]); t1 = max(r["bt"] for r in ok if r["bt"])
    nfail = sum(1 for s in SG if s["err"] and s["bt"] and t0 <= s["bt"] <= t1)
    ffee = statistics.mean([r["fee"] for r in fl]) / 1e9 if fl else 0.0
    fprio = statistics.mean([(r.get("prio") or 0) for r in fl]) / 1e9 if fl else 0.0
    by = collections.defaultdict(lambda: dict(buys=[], sells=[]))
    other_wd = 0; ext = []
    for r in ok:
        mine = [t for t in r["trades"] if t["user"] == W]
        tips = [(d, l) for s, d, l in r["transfers"] if s == W and d != W]
        if not mine:
            if r["wd"] is not None: other_wd += r["wd"]
            for s, d, l in r["transfers"] + r["inner_tr"]:
                if l >= 50_000_000 and (s == W or d == W) and s != d: ext.append((r["bt"], s[:6], d[:6], l / 1e9 * (-1 if s == W else 1)))
            continue
        k = len(mine)
        for t in mine:
            f = ((t.get("fee") or 95) + (t.get("cfee") or 30)) / 1e4
            x = dict(sig=r["sig"], slot=r["slot"], bt=r["bt"], sol=t["sol"] / 1e9, tok=t["tok"], f=f, vsol=t["vsol"], vtok=t["vtok"],
                     txfee=r["fee"] / 1e9 / k, prio=(r.get("prio") or 0) / 1e9 / k, tip=sum(l for _, l in tips) / 1e9 / k,
                     routes=sorted({route(d) for d, _ in tips}), cul=r["cul"], cu=r["cu"], nonce=r.get("nonce"), ver=r.get("ver"),
                     wd=(r["wd"] or 0) / 1e9 / k, progs=[p[:6] for p in r["progs"] if p[:6] not in ("111111", "Comput")])
            by[t["mint"]]["buys" if t["buy"] else "sells"].append(x)
    rows = []
    for m, d in by.items():
        b, s = d["buys"], d["sells"]
        if not b: continue
        b.sort(key=lambda x: x["slot"]); s.sort(key=lambda x: x["slot"])
        bin_ = sum(x["sol"] * (1 + x["f"]) for x in b); sout = sum(x["sol"] * (1 - x["f"]) for x in s)
        cost = sum(x["txfee"] + x["tip"] for x in b + s)
        tb, ts = sum(x["tok"] for x in b), sum(x["tok"] for x in s)
        pnl = sout - bin_ - cost; pwd = sum(x["wd"] for x in b + s)
        la = LA.get(m); du = DU.get(m); ca = CA.get(W, {}).get(m)
        S = la["S"] if la else (du["slot"] if du else None)
        b0 = b[0]
        rows.append(dict(wallet=W, mint=m, slot=b0["slot"], bt=b0["bt"], post_ag=b0["slot"] >= AG, n_buys=len(b), n_sells=len(s),
                         sol_in=bin_, sol_out=sout, cost=cost, pnl=pnl, pnl_wd=pwd, ret=pnl / bin_ if bin_ else None,
                         closed=ts >= 0.99 * tb, frac_sold=ts / tb if tb else None,
                         hold_slots=(s[-1]["slot"] - b0["slot"]) if s else None, hold_s=(s[-1]["bt"] - b0["bt"]) if s else None,
                         first_sell_slots=(s[0]["slot"] - b0["slot"]) if s else None,
                         first_leg=(s[0]["tok"] / tb) if s and tb else None,
                         sells=[dict(ds=x["slot"] - b0["slot"], frac=x["tok"] / tb if tb else None, sol=x["sol"]) for x in s],
                         buy_fee=b0["txfee"], buy_prio=b0["prio"], buy_tip=b0["tip"], buy_routes=b0["routes"], buy_cul=b0["cul"], buy_cu=b0["cu"],
                         buy_nonce=b0["nonce"], buy_ver=b0["ver"], buy_progs=b0["progs"], sell_cost=sum(x["txfee"] + x["tip"] for x in s),
                         sell_routes=sorted({r for x in s for r in x["routes"]}),
                         px_buy=(b0["sol"] * 1e9 / b0["tok"]) if b0["tok"] else None,
                         curve_sol_before=(b0["vsol"] - b0["sol"] * 1e9 - 30e9) / 1e9,
                         S=S, dslot=(b0["slot"] - S) if S else None, watched=la is not None, r2=bool(la and la["r2"]), r2nc=bool(la and la["r2nc"]),
                         grp=la["grp"] if la else None, our_p2=la["p2"] if la else None, our_refused=la["refused"] if la else None,
                         verdict=du["verdict"] if du else ("watched" if la else None), dev=(int(du["dev"]) / 1e9 if du and du.get("dev") else (la["dev"] if la else None)),
                         rank=ca["rank"] if ca else None, after_bundle=ca["after_bundle"] if ca else None, fill=ca["fill"] if ca else None,
                         feed_ms=ca["feed_ms"] if ca else None, gsol=la["gsol"] if la else None, moon=la["moon"] if la else None))
    rows.sort(key=lambda r: r["slot"])
    n_nonsol = sum(r["sol_in"] < 0.001 for r in rows)          # non-SOL-quote launches: the TradeEvent carries no SOL amount
    rows = [r for r in rows if r["sol_in"] >= 0.001]
    allrows += rows
    H = (t1 - t0) / 3600
    cl = [r for r in rows if r["closed"]]
    old_open = [r for r in rows if not r["closed"] and r["bt"] < t1 - 1800]
    pn = [r["pnl"] for r in cl]; sz = [r["sol_in"] for r in rows]
    tot = sum(pn); fcost = nfail * ffee
    res = dict(wallet=W, hours=H, t0=t0, t1=t1, n=len(rows), n_nonsol=n_nonsol, n_closed=len(cl), n_open_old=len(old_open), open_old_in=sum(r["sol_in"] for r in old_open),
               per_h=len(rows) / H if H else None, sol_in=sum(sz), size_med=med(sz), size_p10=q(sz, .1), size_p90=q(sz, .9),
               pnl=tot, fail_n=nfail, fail_fee=fcost, fail_prio_mean=fprio, net=tot - fcost - sum(r["sol_in"] for r in old_open) * 0,
               net_h=(tot - fcost) / H if H else None, mean=statistics.mean(pn) if pn else None, median=med(pn),
               win=sum(p > 0 for p in pn) / len(pn) if pn else None, ex3=sum(sorted(pn)[:-3]) if len(pn) > 3 else None,
               ret=tot / sum(r["sol_in"] for r in cl) if cl else None, hold_med=med([r["hold_s"] for r in cl if r["hold_s"] is not None]),
               hold_slots_med=med([r["hold_slots"] for r in cl if r["hold_slots"] is not None]),
               single=sum(r["n_sells"] == 1 for r in cl) / len(cl) if cl else None,
               buycost_med=med([r["buy_fee"] + r["buy_tip"] for r in rows]), buycost_pct=med([(r["buy_fee"] + r["buy_tip"]) / r["sol_in"] for r in rows if r["sol_in"]]),
               routes=collections.Counter(x for r in rows for x in (r["buy_routes"] or ["none"])).most_common(6),
               nonce=sum(bool(r["buy_nonce"]) for r in rows) / len(rows) if rows else None,
               ver=collections.Counter(str(r["buy_ver"]) for r in rows).most_common(3),
               cul=collections.Counter(r["buy_cul"] for r in rows).most_common(3),
               dslot=collections.Counter(r["dslot"] for r in rows if r["dslot"] is not None).most_common(5), n_known_S=sum(r["dslot"] is not None for r in rows),
               watched=sum(r["watched"] for r in rows), watched_pnl=sum(r["pnl"] for r in cl if r["watched"]),
               r2=sum(r["r2"] for r in rows), r2_pnl=sum(r["pnl"] for r in cl if r["r2"]),
               pre=[sum(1 for r in cl if not r["post_ag"]), sum(r["pnl"] for r in cl if not r["post_ag"])],
               post=[sum(1 for r in cl if r["post_ag"]), sum(r["pnl"] for r in cl if r["post_ag"])],
               other_wd=other_wd / 1e9, ext=ext[:10], ext_sum=sum(e[3] for e in ext), ext_n=len(ext), wd_check=sum(r["pnl_wd"] for r in cl) - tot,
               verdicts=collections.Counter(r["verdict"] for r in rows).most_common(6))
    summ.append(res)

json.dump(allrows, open(os.path.join(OUT, "comp_rows.json"), "w"))
json.dump(summ, open(os.path.join(OUT, "comp_summary.json"), "w"))
f = lambda x, fmt: (fmt % x) if x is not None else "-"
print("wallet        hours trades /h   size(p10-p90)   SOL_in   PnL    failfee  net/h   mean    median  win  ex3     ret   hold_s single buycost(%)  nonce routes")
for s in sorted(summ, key=lambda s: -(s["net_h"] or 0)):
    print(f"{s['wallet'][:12]} {s['hours']:5.1f} {s['n']:5} {s['per_h']:5.1f} {s['size_med']:5.2f}({f(s['size_p10'],'%.2f')}-{f(s['size_p90'],'%.2f')}) {s['sol_in']:7.1f} {s['pnl']:+7.2f} {s['fail_fee']:6.2f} {s['net_h']:+6.3f} "
          f"{f(s['mean'],'%+.3f')} {f(s['median'],'%+.3f')} {f(s['win'],'%.0f%%') if s['win'] is None else '%3.0f%%' % (100*s['win'])} {f(s['ex3'],'%+6.2f')} {f(s['ret'],'%+.1f%%') if s['ret'] is None else '%+5.1f%%' % (100*s['ret'])} "
          f"{f(s['hold_med'],'%4.0f')} {f(s['single'],'%.2f')} {s['buycost_med']:.4f}({100*s['buycost_pct']:.1f}%) {s['nonce']:.2f} {' '.join(f'{k}:{v}' for k,v in s['routes'][:4])}")
print("\nper wallet: open>30min (n, SOL in) | fail n x fee | non-trade wd | trade wd-ev check | pre-AG n/pnl | post-AG n/pnl | watched n/pnl | rule#2 n/pnl | dslot | verdicts")
for s in sorted(summ, key=lambda s: -(s["net_h"] or 0)):
    print(f"{s['wallet'][:12]} open {s['n_open_old']}/{s['open_old_in']:.2f} | fail {s['fail_n']}x{s['fail_fee']/max(1,s['fail_n']):.5f} | other {s['other_wd']:+.3f} | chk {s['wd_check']:+.3f} | "
          f"pre {s['pre'][0]}/{s['pre'][1]:+.2f} post {s['post'][0]}/{s['post'][1]:+.2f} | watched {s['watched']}/{s['watched_pnl']:+.2f} r2 {s['r2']}/{s['r2_pnl']:+.2f} | dslot {s['dslot']} (known {s['n_known_S']}) | {s['verdicts']}")
    if s["ext"]: print(f"      external transfers >=0.05 SOL: n {s['ext_n']} sum {s['ext_sum']:+.2f}; non-trade wd minus them {s['other_wd']-s['ext_sum']:+.3f} (rent closes etc.)", s["ext"][:4])
