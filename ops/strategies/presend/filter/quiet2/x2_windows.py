#!/usr/bin/env python3
"""QUIET2 step 2: one row per live window (armed) and per quiet skip, from the records only (MEASURED). Labels in the ENGINE view
(tape followers); the chain view is added by x3. Output windows.json in the data dir."""
import sys, json, collections
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/quiet2")
import q2lib as Q

rows = []; skiprows = []
for run, R in Q.RUNS.items():
    W, S, M, SH = Q.load(run)
    seen_arm = collections.Counter(); seen_fill = collections.Counter(); seen_whale = collections.Counter()
    for (seg, wi), w in W.items():
        tr = w["arm"]["trig"]; q = w["arm"].get("quiet") or {"q": [None]*4, "all4": None, "coh_hold": None, "fb_n": None, "since_last": None, "wh_dumps": None, "wh_fol": None}
        d = w["disarm"] or {}
        fee_fail = sum(Q.try_fee(t) for t in w["tries"])
        n_unseen = sum(1 for t in w["tries"] if t["land"] and t["land"].get("res") == "unseen")
        r = dict(run=run, name=R["name"], role=R["role"], seg=seg, w=wi, mint=w["mint"], whale=w["whale"], t=w["t"], pkt=Q.pkt(w["t"]),
                 hour=int(Q.pkt(w["t"], "%H")), trig_slot=w["trig_slot"], trig_idx=tr["idx"], trig_sig=tr["sig"], whale_sol=tr["sol"] / 1e9, whale_pct=tr["pct"],
                 vsol=tr["vsol"] / 1e9, vtok=tr["vtok"], age_slots=tr["age_slots"], spend=w["spend"] / 1e9,
                 q_a=q["q"][0], q_b=q["q"][1], q_c=q["q"][2], q_d=q["q"][3], all4=q["all4"], coh_hold=q["coh_hold"], fb_n=q["fb_n"], since_last=q["since_last"],
                 wh_dumps=q["wh_dumps"], wh_fol=q["wh_fol"], rule_on=q.get("rule_on"),
                 disarm_why=d.get("why"), disarm_slot=d.get("slot"), others_at_disarm=(d.get("quiet") or {}).get("others"), quiet_stop=d.get("quiet_stop"),
                 n_tries=len(w["tries"]), fee_fail=fee_fail / 1e9, n_unseen=n_unseen, prior_arms=seen_arm[w["mint"]], prior_fills=seen_fill[w["mint"]],
                 prior_whale_arms=seen_whale[w["whale"]], filled=bool(w["fills"]))
        if w["fills"]:
            f = w["fills"][0]
            r.update(fill_slot=f["slot"], fill_idx=f["idx"], fill_t=f["t"], fill_sol=f["sol_in"] / 1e9, fill_tokens=f["tokens"], fill_sig=f["sig"],
                     slots_after_trigger=f["slots_after_trigger"], ms_send_to_rx=f.get("ms_send_to_rx"), fill_lag_ms=(f["t"] - w["t"]) / 1e6,
                     p_entry_post=f.get("p_entry_post"), p_entry_pre=f.get("p_entry_pre"), p_sign=f.get("p_sign"), n_fills=len(w["fills"]))
            if w["sells"]:
                s = w["sells"][-1]
                r.update(sell_slot=s["slot"], sell_idx=s["idx"], sell_t=s["t"], sell_sol=s["sol"] / 1e9, sell_sig=s["sig"])
            e = w["exit"] or {}
            r.update(exit_why=e.get("why"), slots_held=e.get("slots_held"))
            pnl = (w["realized"] or {}).get("pnl")
            ata = sum(a["delta"] for a in w["ata"])
            r.update(pnl=None if pnl is None else pnl / 1e9, ata=ata / 1e9, net=None if pnl is None else (pnl + ata) / 1e9)
            # engine-view followers: tape trades by other wallets between our buy and our sell (chain position)
            fpos = (f["slot"], f["idx"]); spos = (s["slot"], s["idx"]) if w["sells"] else (10**12, 0)
            tp = [x for x in w["tape"] if x["user"] not in Q.OURS and fpos < (x["slot"], x["idx"]) < spos]
            r.update(eng_fol_trades=len(tp), eng_fol_buys=sum(1 for x in tp if x["buy"]), eng_fol_buyers=len({x["user"] for x in tp if x["buy"]}),
                     eng_fol_buy_sol=sum(x["sol"] for x in tp if x["buy"]) / 1e9, eng_fol_sell_sol=sum(x["sol"] for x in tp if not x["buy"]) / 1e9)
            seen_fill[w["mint"]] += 1
        rows.append(r)
        seen_arm[w["mint"]] += 1; seen_whale[w["whale"]] += 1
    for s in S:
        tr = s["trig"]; q = s.get("quiet") or {}
        skiprows.append(dict(run=run, name=R["name"], role=R["role"], seg=s["seg"], mint=tr["mint"], whale=tr["wallet"], t=tr["t"], pkt=Q.pkt(tr["t"]), hour=int(Q.pkt(tr["t"], "%H")),
                             trig_slot=tr["slot"], trig_idx=tr["idx"], whale_sol=tr["sol"] / 1e9, whale_pct=tr["pct"], vsol=tr["vsol"] / 1e9, vtok=tr["vtok"], age_slots=tr["age_slots"],
                             why=s.get("why"), q=q.get("q"), all4=q.get("all4"), coh_hold=q.get("coh_hold"), fb_n=q.get("fb_n"), since_last=q.get("since_last"),
                             wh_dumps=q.get("wh_dumps"), wh_fol=q.get("wh_fol"), rule_on=q.get("rule_on")))
    nf = [r for r in rows if r["run"] == run and r["filled"]]
    net = sum(r["net"] or 0 for r in nf); fees = sum(r["fee_fail"] for r in rows if r["run"] == run)
    flat = [r for r in nf if r["eng_fol_trades"] == 0]
    print(f"{R['name']:8s} {R['role']:5s} windows {sum(1 for r in rows if r['run']==run):5d} quiet-skips {sum(1 for s in S if s.get('why')=='quiet'):4d} fills {len(nf):4d} "
          f"flat(eng) {len(flat):3d} ({sum(r['net'] for r in flat):+.3f}) wins {sum(1 for r in nf if (r['net'] or 0)>0):3d} net {net:+.3f} fees_failed {fees:.3f} pre-send net {net-fees:+.3f} "
          f"span {Q.pkt(M['starts'][0]['t'],'%m-%d %H:%M')}..{Q.pkt(M['ends'][-1]['t'],'%H:%M') if M['ends'] else 'live'}")
json.dump(dict(windows=rows, skips=skiprows), open(f"{Q.D}/windows.json", "w"))
print(len(rows), len(skiprows))
