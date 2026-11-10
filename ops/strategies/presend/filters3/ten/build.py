#!/usr/bin/env python3
"""TEN: build flat tables from the extracted runs (r37..r42 only; holdout never read).
out: /home/it/sniper-data/filters3/ten/pos.json   one row per live position (filled window): real money + signing-time features
     /home/it/sniper-data/filters3/ten/trig.json  one row per shadow T2 trigger: shadow row c money (scaled to live size) + live status
     /home/it/sniper-data/filters3/ten/wide.json  one row per wide-shadow window (r41, r42)
     /home/it/sniper-data/filters3/ten/hours.json run hours per segment
Segments: DEV = r37..r41 + r42 with t < 11-01 12:00 PKT; VAL = r42 with t >= that (t = record ns epoch)."""
import json, datetime, collections
D = "/home/it/sniper-data/filters3/ten/"
CUT = int(datetime.datetime(2026, 11, 1, 7, 0, tzinfo=datetime.timezone.utc).timestamp() * 1e9)
RUNS = ["r37", "r38", "r39", "r40", "r41", "r42"]
ME = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"
FEE = 0.0125

def seg(t): return "DEV" if t < CUT else "VAL"
def hour_pkt(t): return (datetime.datetime.fromtimestamp(t / 1e9, datetime.timezone.utc) + datetime.timedelta(hours=5)).hour

pos, trig, wide, hours = [], [], [], collections.defaultdict(float)
for r in RUNS:
    R = json.load(open(D + r + ".x.json"))
    a, b = R["first_t"], R["last_t"]
    if b <= CUT: hours["DEV"] += (b - a) / 3.6e12; hours["DEV:" + r] += (b - a) / 3.6e12
    else:
        hours["DEV"] += (CUT - a) / 3.6e12; hours["VAL"] += (b - CUT) / 3.6e12
        hours["DEV:" + r] += (CUT - a) / 3.6e12; hours["VAL:" + r] += (b - CUT) / 3.6e12
    live_size = R["run_start"]["presend_live"]["spend"] / 1e9
    # live T2 windows by trigger sig
    live_by_sig = {}
    for k, v in R["live"].items():
        arm = v.get("arm")
        if v["kind"] == "t2" and arm: live_by_sig[arm["trig"]["sig"]] = v
        if not v.get("fills") or v["pnl"] is None: continue
        f = v["fills"][0]; arm = arm or {}; tr = arm.get("trig") or {}; q = arm.get("quiet") or {}; v2 = arm.get("v2") or {}
        cl = (v.get("close") or [{}])[0]
        # followers: buys by others after our buy (feed order), up to our first sell landing
        sl = cl.get("sell_land") or [f["slot"] + 3, 10**6]
        tp = sorted(v["tape"], key=lambda x: (x["slot"], x["idx"] or 0))
        after = [x for x in tp if (x["slot"], x["idx"] or 0) > (f["slot"], f["idx"] or 0) and x["user"] != ME]
        inhold = [x for x in after if (x["slot"], x["idx"] or 0) < (sl[0], sl[1])]
        fol = [x for x in inhold if x["buy"]]
        sells = [x for x in inhold if not x["buy"]]
        fol10 = [x for x in after if x["buy"] and x["slot"] <= f["slot"] + 10]
        anh = (f.get("ann") or {}).get("holders") or []
        pos.append({"run": r, "seg": seg(f["t"]), "kind": v["kind"], "w": v["w"], "mint": v.get("mint"), "t": f["t"], "hour": hour_pkt(f["t"]),
                    "pnl": v["pnl"] / 1e9, "fail_fee": v["fail_fee"] / 1e9, "spend": (f.get("spend") or arm.get("spend") or 0) / 1e9, "sol_in": (f.get("sol_in") or 0) / 1e9,
                    "tokens": f.get("tokens"), "min_out": f.get("min_out"), "lim": f.get("lim"), "p_pre": f.get("p_entry_pre"), "p_sign": f.get("p_sign"),
                    "fill_slot": f["slot"], "fill_idx": f["idx"], "sat": f.get("slots_after_trigger"),
                    "trig_pct": tr.get("pct"), "trig_sol": (tr.get("sol") or 0) / 1e9, "age": tr.get("age_slots"), "trig_vsol": (tr.get("vsol") or 0) / 1e9,
                    "trig_t": tr.get("t"), "trig_slot": tr.get("slot"), "dump_drop": tr.get("drop_pct"), "whale": tr.get("wallet") or tr.get("seller"),
                    "depth": (f.get("ann") or {}).get("depth"), "ob6": (f.get("ann") or {}).get("ob6"),
                    "q": q, "v2": v2, "nb": arm.get("nb"), "ann": arm.get("ann"), "rearm_holders": [h.get("pct") for h in (arm.get("holders") or [])] if v["kind"] == "rearm" else None,
                    "n_fol": len(fol), "fol_sol": sum(x["sol"] for x in fol) / 1e9, "n_sell_hold": len(sells), "sell_sol_hold": sum(x["sol"] for x in sells) / 1e9,
                    "n_fol10": len(fol10), "fol_users": sorted({x["user"] for x in fol10}),
                    "held_s": cl.get("held_s"), "curve_pnl": (cl.get("curve_pnl") or 0) / 1e9, "sol_out_curve": (cl.get("sol_out_curve") or 0) / 1e9,
                    "exit_why": cl.get("exit_why"), "rounds": cl.get("rounds"), "sell_land": cl.get("sell_land"), "tape": tp,
                    "fill_holders": [(h.get("pct"), h.get("n"), h.get("h3"), h.get("age")) for h in anh]})
    # shadow T2 triggers
    skip_by_sig = {}
    for s in R["t2_skips"]: skip_by_sig.setdefault(s["sig"], s)
    for w, st in R["shadow"].items():
        arm = st.get("arm")
        if not arm: continue
        rc = st["rows"].get("c") or {}
        net = (rc.get("exit") or {}).get("net_cheap")
        szl = ((rc.get("fill") or {}).get("sol_in") or 0) / 1e9
        paper = None if net is None else net * (live_size / szl if szl else 1.0)
        lv = live_by_sig.get(arm["sig"]); sk = skip_by_sig.get(arm["sig"])
        status = "armed" if lv else ("skip:" + (sk["why"] or "?") if sk else "unseen")
        live_pnl = None
        if lv: live_pnl = (lv["pnl"] or 0) / 1e9
        trig.append({"run": r, "seg": seg(arm["t"]), "t": arm["t"], "hour": hour_pkt(arm["t"]), "sig": arm["sig"], "mint": arm["mint"], "wallet": arm.get("wallet"),
                     "pct": arm["pct"], "age": arm["age_slots"], "sol": (arm.get("sol") or 0) / 1e9, "vsol": (arm.get("vsol") or 0) / 1e9,
                     "q": arm.get("quiet"), "v2": arm.get("v2"), "paper": paper, "sh_fill": rc.get("fill"), "sh_exit": rc.get("exit"),
                     "sh_disarm": st.get("disarm"), "status": status, "live_pnl": live_pnl,
                     "live_filled": bool(lv and lv.get("fills")), "live_failfee": (lv["fail_fee"] / 1e9) if lv else 0.0,
                     "live_disarm": (lv.get("disarm") or {}).get("why") if lv else None, "nb": (lv.get("arm") or {}).get("nb") if lv else (sk or {}).get("nb")})
    for w, st in R["wide"].items():
        arm = st.get("arm")
        if not arm: continue
        rc = st["rows"].get("c") or {}
        net = (rc.get("exit") or {}).get("net_cheap"); szl = ((rc.get("fill") or {}).get("sol_in") or 0) / 1e9
        wide.append({"run": r, "seg": seg(arm["t"]), "t": arm["t"], "hour": hour_pkt(arm["t"]), "sig": arm["sig"], "mint": arm["mint"], "wallet": arm.get("wallet"),
                     "pct": arm["pct"], "age": arm["age_slots"], "age_s": arm.get("age_s"), "sol": (arm.get("sol") or 0) / 1e9, "vsol": (arm.get("vsol") or 0) / 1e9,
                     "paper": None if net is None else net * (live_size / szl if szl else 1.0), "sh_fill": rc.get("fill"), "sh_exit": rc.get("exit"), "sh_disarm": st.get("disarm")})
    print(r, "positions", sum(1 for p in pos if p["run"] == r), "trig", sum(1 for x in trig if x["run"] == r), "wide", sum(1 for x in wide if x["run"] == r))
json.dump(pos, open(D + "pos.json", "w")); json.dump(trig, open(D + "trig.json", "w")); json.dump(wide, open(D + "wide.json", "w")); json.dump(dict(hours), open(D + "hours.json", "w"))
print(dict(hours))
