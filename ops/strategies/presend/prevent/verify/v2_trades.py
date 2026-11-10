#!/usr/bin/env python3
"""VERIFY step 2 [MEASURED]: per-trade and per-window tables from live.pkl (own extraction).
Trade P&L components (fit on the live records, all runs): realized pnl = curve pnl - 1.25% x (sol in + sol out) - FIXED, FIXED = 3.524 mSOL
when the run creates+closes the ATA (2.010 fees/tips + 1.514 rent), 2.010 mSOL on runs without ATA close; ATA close refunds 1.509 mSOL.
unit (real) = pnl + rent refund; failed-try fees per window (landed failed tries, res != ok).
scaled to 0.696: s = (pnl + FIXED) * 0.696 / spend - FIXED + refund   (re-arm at 0.65 in r38 is left at its real size unless asked).
Out: /home/it/sniper-data/prevent/verify/tables.pkl"""
import pickle, collections
OUT = "/home/it/sniper-data/prevent/verify"
L = pickle.load(open(f"{OUT}/live.pkl", "rb"))
SIZE = 0.696
FIX_ATA = 0.003524; FIX_NOATA = 0.002010
trades = []; wins = []
for run, D in L.items():
    has_ata = len(D["ata"]) > 0
    fills = collections.defaultdict(list)
    for f in D["fills"]: fills[(f["w"], f["mint"])].append(f)
    closes = {}
    for c in D["closes"]: closes.setdefault((c["w"], c["mint"]), c)
    sells = collections.defaultdict(list)
    for s in D["sells"]: sells[(s["w"], s["mint"])].append(s)
    ata = collections.defaultdict(list)
    for a in D["ata"]:
        if a.get("ok"): ata[(a["_s"], a["mint"])].append(a)
    failfee = collections.Counter(); nfail = collections.Counter()
    for w, lst in D["att"].items():
        for x in lst:
            if x[0] == "L" and x[2] != "ok": failfee[w] += x[3] or 0; nfail[w] += 1
    filled_w = set()
    for r in sorted(D["realized"], key=lambda r: (fills.get((r["w"], r["mint"])) or [{"t": 0}])[0]["t"]):
        k = (r["w"], r["mint"]); f = fills.get(k)
        if not f: print("no fill for realized", run, k); continue
        f0 = f[0]; c = closes.get(k, {})
        sl = sells.get(k, [])
        t_sell = max([s["t"] for s in sl], default=None)
        if t_sell is None and c.get("sell_land"): t_sell = c["sell_land"][2]
        rf = ata.get((r["_s"], r["mint"]))
        refund = rf.pop(0)["delta"] / 1e9 if rf else 0.0
        spend = (f0.get("spend") or c.get("spend") or (D["cfg"]["presend_live"]["spend"])) / 1e9
        pnl = r["pnl"] / 1e9
        FIX = FIX_ATA if has_ata else FIX_NOATA
        s = (pnl + FIX) * SIZE / spend - FIX + refund
        kind = r.get("kind") or f0.get("kind") or "t2"
        arm = D["arms"].get(r["w"], {})
        trades.append(dict(run=run, w=r["w"], kind=kind, mint=r["mint"], t=f0["t"] / 1e9, t_sell=(t_sell or f0["t"]) / 1e9, pnl=pnl, refund=refund,
                           unit=pnl + refund, s=s, spend=spend, k=SIZE / spend, nfills=len(f), why=c.get("exit_why"), held=c.get("held_s"),
                           p_sign=f0.get("p_sign"), lim=f0.get("lim"), p_pre=f0.get("p_entry_pre"), p_post=f0.get("p_entry_post"), min_out=f0.get("min_out"),
                           tokens=f0.get("tokens"), sol_in=f0.get("sol_in"), fslot=f0.get("slot"), fidx=f0.get("idx"), n_try=f0.get("n"),
                           path=f0.get("path"), curve=(c.get("sol_out_curve") or 0) / 1e9 - (c.get("sol_in_curve") or 0) / 1e9 if c else None,
                           wfee=failfee.get(r["w"], 0) / 1e9, has_ata=has_ata))
        filled_w.add(r["w"])
    for w, a in D["arms"].items():
        tr = a.get("trig") or a.get("dump") or {}
        kind = a.get("kind", "t2")
        dis = D["disarm"].get(w, {})
        wins.append(dict(run=run, w=w, kind=kind, mint=a.get("mint") or tr.get("mint"), t=(a.get("t") or tr.get("t")) / 1e9,
                         who=tr.get("wallet") or tr.get("seller"), slot=tr.get("slot"), idx=tr.get("idx"), pct=tr.get("pct"), age=tr.get("age_slots"),
                         arm_slot=a.get("arm_slot"), en_slot=a.get("en_slot"), spend=(a.get("spend") or 0) / 1e9, quiet=a.get("quiet"),
                         qskip=a.get("quiet_skip"), holders=a.get("holders"), filled=w in filled_w, wfee=failfee.get(w, 0) / 1e9, nfail=nfail.get(w, 0),
                         dis_why=dis.get("why"), dis_slot=dis.get("slot"), attempts=dis.get("attempts")))
    # fees of tries whose window has no arm record
    lost = sum(v for w, v in failfee.items() if w not in D["arms"]) / 1e9
    if lost: print(run, "fail fees without arm", round(lost, 4))
trades.sort(key=lambda x: (x["run"], x["t"])); wins.sort(key=lambda x: (x["run"], x["t"]))
pickle.dump(dict(trades=trades, wins=wins), open(f"{OUT}/tables.pkl", "wb"))
by = collections.defaultdict(list)
for x in trades: by[x["run"]].append(x)
wb = collections.defaultdict(list)
for x in wins: wb[x["run"]].append(x)
print(f"{'run':4s} {'n':>4s} {'spend':>5s} {'pnl':>7s} {'refund':>6s} {'failfee':>7s} {'net':>7s} | {'scaled':>7s} | t2 n/net  rearm n/net | windows")
for run in sorted(by, key=lambda r: (r[0], int(r[1:]))):
    xs = by[run]; ff = sum(w["wfee"] for w in wb[run])
    net = sum(x["unit"] for x in xs) - ff; scl = sum(x["s"] for x in xs) - ff
    t2 = [x for x in xs if x["kind"] == "t2"]; ra = [x for x in xs if x["kind"] != "t2"]
    print(f"{run:4s} {len(xs):4d} {xs[0]['spend']:5.3f} {sum(x['pnl'] for x in xs):+7.3f} {sum(x['refund'] for x in xs):6.3f} {ff:7.3f} {net:+7.3f} | {scl:+7.3f} | "
          f"{len(t2)} {sum(x['unit'] for x in t2):+.3f}  {len(ra)} {sum(x['unit'] for x in ra):+.3f} | {len(wb[run])}")
