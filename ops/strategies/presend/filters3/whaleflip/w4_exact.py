#!/usr/bin/env python3
"""WHALEFLIP step 4 [MEASURED where the raw recording covers the fill]: the EXACT dumper of every live fill from the chain tape.
For each filled window: our buy tx on the tape (by signature); the crossing trade = the last tx between the trigger and our buy whose
price before was above the filling try's limit and after it at or below (chain order, our own txs skipped); its seller (the owner with
the largest token decrease); the trigger whale's balance just before our buy (its last tx on the tape before our buy, else the
engine's trigger balance) as a share of its trigger balance, and whether its token account was closed (CloseAccount in its sell tx,
balance 0); whether the whale sold during our hold (between our buy and our sell landing). Re-arm: the arm's other >= 6% holders'
balances at our fill. Checks: the tape's state at our buy vs the engine's p_entry_pre; engine "x" vs exact seller.
Out: whaleflip/exact.json + printed tables.  usage: w4_exact.py"""
import sys, json, bisect, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/whaleflip")
import wlib as W, wtape as T

F = W.load()
TP = T.build(); tapes = TP["tapes"]
h, hp, P = W.hours(F)
SUP = 1e15
out = []; chk = collections.Counter(); perr = []
for f in F:
    fl = f["fills"][0]; m = f["mint"]
    tp = tapes.get(m)
    r = {"run": f["run"], "seg": f["seg"], "period": f["period"], "kind": f["kind"], "w": f["w"], "ses": f["ses"], "mint": m, "pnl": f["pnl"], "t": fl["t"], "covered": False}
    out.append(r)
    if tp is None: chk["no_tape"] += 1; continue
    rows = tp["rows"]; sigs = {x["sig"]: k for k, x in enumerate(rows)}
    kb = sigs.get(fl["sig"])
    if kb is None: chk["buy_not_on_tape"] += 1; continue
    if f["kind"] == "t2":
        tg = f["trig"]; whale = tg["wallet"]; kt = sigs.get(tg["sig"]); wbal0 = tg["bal"]
        trig_pos = (tg["slot"], tg["idx"])
    else:
        dp = f["dump"]; whale = dp["seller"]; kt = sigs.get(dp["sig"]); wbal0 = None
        trig_pos = (dp["slot"], dp["idx"])
    if kt is None:
        kt = bisect.bisect_left([(x["s"], x["i"]) for x in rows], trig_pos)
        chk["trig_not_on_tape"] += 1
        kt -= 1
    r["covered"] = True
    bt = rows[kb]
    pe = T.price_pre(bt)
    perr.append(pe / fl["p_entry_pre"] - 1 if fl.get("p_entry_pre") else 0)
    lim = fl["lim"]
    # crossing trade
    kx = None
    for k in range(kb - 1, kt, -1):
        x = rows[k]
        if x["ours"]: continue
        if T.price_pre(x) > lim >= x["p"]: kx = k; break
    if kx is None:
        r["xlab"] = "nocross"; chk["nocross"] += 1
    else:
        x = rows[kx]; r["x_seller"] = x["seller"]; r["x_sold"] = x["sold"]; r["x_pos"] = (x["s"], x["i"]); r["x_slot_gap"] = bt["s"] - x["s"]
        r["x_drop"] = 1 - x["p"] / T.price_pre(x)
    # sells between trigger and our buy (others)
    sells = [rows[k] for k in range(kt + 1, kb) if rows[k]["seller"] and not rows[k]["ours"]]
    r["n_sells_before"] = len(sells); r["whale_sold_before"] = any(s["seller"] == whale for s in sells)
    # whale balance just before our buy
    wb, wcl, wlast = None, False, None
    for k in range(kb - 1, kt, -1):
        x = rows[k]
        if whale in x["own"]:
            wb = x["own"][whale][1]; wcl = bool(x["cl"] and wb == 0 and x["seller"] == whale); wlast = (x["s"], x["i"]); break
    if f["kind"] == "t2":
        if wb is None: wb = wbal0
        r["wh_bal"] = wb; r["wh_bal0"] = wbal0; r["wh_frac"] = wb / wbal0 if wbal0 else None; r["wh_closed"] = wcl
        r["xlab"] = r.get("xlab") or ("FLIP" if r.get("x_seller") == whale else "OTHER")
    else:
        if wb is None: wb = (dp.get("pct") or 0) and None
        hs = {z["w"]: z["pct"] * SUP / 100 for z in (f.get("holders") or []) if z["w"] != whale}
        hb = {}
        for u, b0 in hs.items():
            b = b0
            for k in range(kb - 1, kt, -1):
                if u in rows[k]["own"]: b = rows[k]["own"][u][1]; break
            hb[u] = b
        r["holders_at_fill"] = {u: b / SUP * 100 for u, b in hb.items()}
        r["holder6_still"] = any(b >= 0.06 * SUP for b in hb.values())
        if r.get("xlab") != "nocross":
            r["xlab"] = "SAME" if r.get("x_seller") == whale else ("HOLDER" if r.get("x_seller") in hs else "OTHER")
    # sells by the whale / >= 6% holders during our hold (our buy -> our first sell landing)
    sl = (f.get("close") or {}).get("sell_land")
    end = (sl[0], sl[1]) if sl else (bt["s"] + 3, 0)
    hold = [x for x in rows[kb + 1:] if (x["s"], x["i"]) < end and not x["ours"]]
    r["whale_sold_in_hold"] = any(x["seller"] == whale for x in hold)
    r["big_sell_in_hold"] = max((x["sold"] for x in hold), default=0) / SUP * 100
    # engine label agreement
    fl_try = next((t for t in f["tries"] if t["sig"] == fl["sig"]), None)
    ex = ((fl_try or {}).get("land") or {}).get("x") or {}
    r["engine_x_user"] = ex.get("user")
    if ex.get("user") and r.get("x_seller"):
        chk["engine_x_agree" if r["x_seller"].startswith(ex["user"]) or (r.get("x_pos") == (ex.get("slot"), ex.get("idx"))) else "engine_x_disagree"] += 1
    sh = f.get("shadow")
    r["slab"] = None if f["kind"] != "t2" else ("noshadow" if sh is None else ("nofill" if sh == "nofill" else ("FLIP" if sh.get("seller_is_whale") else "OTHER")))
json.dump(out, open(f"{W.D}/exact.json", "w"))
perr.sort()
print("checks:", dict(chk), "| covered fills:", sum(r["covered"] for r in out), "of", len(out))
if perr: print(f"tape price before our buy vs engine p_entry_pre: median {perr[len(perr)//2]*100:+.3f}%  p05 {perr[len(perr)//20]*100:+.3f}%  p95 {perr[len(perr)*19//20]*100:+.3f}%")
cov = collections.Counter((r["seg"], r["covered"]) for r in out)
print("coverage per segment:", {s: f"{cov[(s, True)]}/{cov[(s, True)] + cov[(s, False)]}" for s in ["r39", "r40", "r41", "r42a", "r42b", "r43", "r44", "r45", "r46", "r47", "r48"]})
for kind in ("t2", "rearm"):
    rr = [r for r in out if r["kind"] == kind and r["covered"]]
    print(f"\n==== {kind}: EXACT label (covered fills) ====")
    for per in ("DEV", "VAL", "HOLD", None):
        g = collections.defaultdict(list)
        for r in rr:
            if per is None or r["period"] == per: g[r["xlab"]].append(r["pnl"])
        print(f"  {per or 'ALL'}: " + " | ".join(f"{k}: {W.fmt(W.st(v))}" for k, v in sorted(g.items())))
    if kind == "t2":
        c = collections.Counter((r["slab"], r["xlab"]) for r in rr)
        print("  shadow label -> exact label:", dict(sorted(c.items(), key=str)))
        both = [r for r in rr if r["slab"] in ("FLIP", "OTHER") and r["xlab"] in ("FLIP", "OTHER")]
        print(f"  shadow agrees with exact: {sum(r['slab'] == r['xlab'] for r in both)}/{len(both)}")
        print("  OTHER fills split by whale balance at our fill (share of its trigger balance) and whale selling during our hold:")
        for per in ("DEV", "VAL", "HOLD"):
            g = collections.defaultdict(list)
            for r in rr:
                if r["period"] != per: continue
                fr = r.get("wh_frac")
                b = "closed" if r.get("wh_closed") else ("<=0.05" if fr is not None and fr <= 0.05 else ("<=0.5" if fr is not None and fr <= 0.5 else (">0.5" if fr is not None else "?")))
                g[(r["xlab"], b)].append(r["pnl"])
            print(f"    {per}: " + " | ".join(f"{k[0]}/{k[1]}: n {len(v)} {sum(v):+.3f}" for k, v in sorted(g.items())))
        for per in ("DEV", "VAL", "HOLD"):
            g = collections.defaultdict(list)
            for r in rr:
                if r["period"] == per: g[(r["xlab"], "whale sold in hold" if r["whale_sold_in_hold"] else "no")].append(r["pnl"])
            print(f"    {per}: " + " | ".join(f"{k[0]}/{k[1]}: n {len(v)} {sum(v):+.3f}" for k, v in sorted(g.items())))
    else:
        for per in ("DEV", "VAL", "HOLD"):
            g = collections.defaultdict(list)
            for r in rr:
                if r["period"] == per: g[(r["xlab"], "6%holder still" if r.get("holder6_still") else "none left")].append(r["pnl"])
            print(f"    {per}: " + " | ".join(f"{k[0]}/{k[1]}: {W.fmt(W.st(v))}" for k, v in sorted(g.items())))
