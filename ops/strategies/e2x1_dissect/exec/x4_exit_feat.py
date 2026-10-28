#!/usr/bin/env python3
"""Q3 exits: per D1 lot, the state at each of his sells (MEASURED from tape): slots/ms since buy, price change since entry
(curve vSOL just before his sell vs just after his buy -> price ratio (v/v0)^2), peak since entry, drawdown from peak, the trade(s)
just before his sell (who, side, size: sibling Grozoe / the trigger wallet / the creator / other), outside buy/sell flow since entry,
time since the last outside buy. Also a per-slot path for rule fitting (x5). Out: sniper-data/e2x1_dissect/exec/x4.pkl"""
import sys, pickle, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/exec")
import numpy as np, xlib as X
L = [l for l in X.lots() if l["day"] in ("D0", "D1")]
T = X.tape()["trades"]; C = X.tape()["creates"]
rows = []
for l in L:
    tr = [t for t in T.get(l["mint"], []) if t[16]]
    k0 = next((k for k, t in enumerate(tr) if t[15] == l["buy_sig"]), None)
    if k0 is None: continue
    v0 = l["vsol_after"]; creator = (C.get(l["mint"]) or {}).get("creator") or l.get("creator")
    sells = l["sells"]; ssig = {s[0] for s in sells}
    end_s = (l["close_s"] or l["s"] + 9000) + 50
    path = []  # (slot, idx, user, buy, sol, vsol_after, is_his, is_sib)
    for t in tr[k0 + 1:]:
        if t[0] > end_s: break
        path.append((t[0], t[1], t[4], t[6], t[7] / 1e9, t[9] / 1e9, t[4] == X.WAL, t[4] == X.SIB, t[15]))
    # per sell features
    sf = []
    for sx in sells:
        sig, s, i = sx[0], sx[1], sx[2]
        pre = [p for p in path if (p[0], p[1]) < (s, i)]
        outside = [p for p in pre if not p[6]]
        v_pre = pre[-1][5] if pre else v0
        peak = max([v0] + [p[5] for p in pre]); trough = min([v0] + [p[5] for p in pre])
        last = outside[-1] if outside else None
        lastsell = next((p for p in reversed(outside) if not p[3]), None)
        lastbuy = next((p for p in reversed(outside) if p[3]), None)
        sib_sell_before = any(p[7] and not p[3] and p[0] == s for p in pre)
        sib_sell_slot = [p for p in path if p[7] and not p[3] and abs(p[0] - s) <= 2]
        trig_sold = [p for p in outside if p[2] == l.get("trig_user") and not p[3]]
        cre_sold = [p for p in outside if p[2] == creator and not p[3]]
        sf.append(dict(sig=sig, s=s, i=i, bt=sx[3], frac_tok=sx[4] / l["tok"] if l["tok"] else 0, net=sx[5],
                       dslots=s - l["s"], dms=X.cc(s, i) - X.cc(l["s"], l["i"]), dbt=sx[3] - l["bt"],
                       r=(v_pre / v0) ** 2, rpeak=(peak / v0) ** 2, rtrough=(trough / v0) ** 2, dd=(v_pre / peak) ** 2,
                       n_out=len(outside), buy_sol=sum(p[4] for p in outside if p[3]), sell_sol=sum(p[4] for p in outside if not p[3]),
                       last_user=last and last[2], last_buy=last and last[3], last_sol=last and last[4], last_gap=last and (s - last[0]), last_sib=last and last[7],
                       last_trig=last and last[2] == l.get("trig_user"), last_cre=last and last[2] == creator,
                       lastsell_sol=lastsell and lastsell[4], lastsell_gap=lastsell and s - lastsell[0], lastsell_user=lastsell and lastsell[2],
                       lastbuy_gap=lastbuy and s - lastbuy[0], sib_sell_before=sib_sell_before, sib_near=len(sib_sell_slot),
                       trig_sold=bool(trig_sold), trig_sold_gap=trig_sold and s - trig_sold[-1][0], cre_sold=bool(cre_sold), cre_sold_gap=cre_sold and s - cre_sold[-1][0],
                       relay=None))
    rows.append(dict(lot=l["lot_id"], day=l["day"], bot=l["bot"], mint=l["mint"], buy_sig=l["buy_sig"], s=l["s"], i=l["i"], bt=l["bt"], v0=v0, tok=l["tok"],
                     cost=l["cost"], pnl=l["pnl"], hold_s=l["hold_s"], n_sells=l["n_sells"], sells=sf, path=path, trig_user=l.get("trig_user"), creator=creator,
                     is_open=l["is_open"], sell_tip_amts=l["sell_tip_amts"], fbps=l["fbps"], cbps=l["cbps"], swap=l["swap_sell"]))
pickle.dump(rows, open(f"{X.X}/x4.pkl", "wb")); print(len(rows))
