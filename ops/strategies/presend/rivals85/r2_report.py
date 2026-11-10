#!/usr/bin/env python3
"""RIVALS85 step 2: flagged vs not-flagged tables from r1_fills.py's fills.pkl (competitor participation, competitor outcome, our outcome),
the 2x2 split (other >= 6% holder at signing x depth < 15%), per run, the competitors most present in flagged fills, cluster-bootstrap CIs.
Out: /home/it/sniper-data/rivals85/RESULTS.txt + RESULTS.json
usage: r2_report.py"""
import pickle, json, collections, statistics as st, random
import numpy as np

OUT = "/home/it/sniper-data/rivals85"
X = pickle.load(open(f"{OUT}/fills.pkl", "rb")); R = [o for o in X["fills"] if o.get("dump")]
RUNS = ["A34", "A35", "A36", "A37", "A38", "A39"]
SLOT_S = 0.2135


def grp(o):
    sh = o["depth"] is not None and o["depth"] < 0.15
    return ("F" if sh else "H") if o["other6"] else ("S" if sh else "N")


def comps(v, who="all", side=None):
    out = []
    for o in v:
        for c in o.get("comp", []):
            if who == "named" and not c["named"]: continue
            if who == "pro" and c["named"]: continue
            if side == "before" and not c["before_us"]: continue
            if side == "after" and c["before_us"]: continue
            out.append((o, c))
    return out


def summ(v, who="all"):
    n = len(v)
    if n == 0: return {"fills": 0}
    part = [o for o in v if any((who == "all") or (who == "named" and c["named"]) or (who == "pro" and not c["named"]) for c in o.get("comp", []))]
    cs = comps(v, who)
    rat = [c["ratio"] for _, c in cs if c.get("ratio") is not None]
    pe = [c["pnl_est"] for _, c in cs if c.get("pnl_est") is not None]
    hs = [c["hold_slots"] for _, c in cs if c.get("hold_slots") is not None]
    ours = [o["pnl"] for o in v if o.get("pnl") is not None]
    ourr = [o["our_ratio_px"] for o in v if o.get("our_ratio_px")]
    lost = [o for o in v if (o.get("pnl") or 0) < 0]
    cl = [c for o, c in comps(lost, who) if c.get("ratio") is not None]
    return {"fills": n,
            "part_pct": round(100 * len(part) / n, 1),
            "comp_wallets_per_fill": round(sum(len([c for c in o.get("comp", []) if (who == "all") or (who == "named") == bool(c["named"])]) for o in v) / n, 2),
            "comp_sol_per_fill": round(sum(c["sol"] for _, c in cs) / n, 3),
            "trades": len(cs), "before_us_pct": round(100 * sum(1 for _, c in cs if c["before_us"]) / len(cs), 1) if cs else None,
            "ratio_med": round(st.median(rat), 4) if rat else None, "ratio_mean": round(st.mean(rat), 4) if rat else None,
            "win_pct": round(100 * sum(1 for r in rat if r > 1) / len(rat), 1) if rat else None,
            "pnl_est_sum": round(sum(pe), 3), "pnl_est_per_trade": round(st.mean(pe), 4) if pe else None,
            "hold_med_slots": st.median(hs) if hs else None, "censored": sum(1 for _, c in cs if c.get("censored")),
            "exit_before_our_sell_pct": round(100 * sum(1 for _, c in cs if c.get("exit_before_our_sell")) / len(cs), 1) if cs else None,
            "our_pnl_mean": round(st.mean(ours), 4) if ours else None, "our_pnl_sum": round(sum(ours), 3), "our_win_pct": round(100 * sum(1 for p in ours if p > 0) / len(ours), 1) if ours else None,
            "our_ratio_med": round(st.median(ourr), 4) if ourr else None, "our_ratio_mean": round(st.mean(ourr), 4) if ourr else None,
            "we_lost_fills": len(lost), "comp_win_pct_where_we_lost": round(100 * sum(1 for c in cl if c["ratio"] > 1) / len(cl), 1) if cl else None,
            "comp_ratio_mean_where_we_lost": round(st.mean([c["ratio"] for c in cl]), 4) if cl else None,
            "all_buyers_per_fill": round(st.mean([o["n_buyers_win"] for o in v]), 2)}


def boot(a, b, fn, n=2000, seed=7):
    """cluster bootstrap (by fill) of fn(a) - fn(b)"""
    rnd = random.Random(seed); d = []
    for _ in range(n):
        x = [a[rnd.randrange(len(a))] for _ in a]; y = [b[rnd.randrange(len(b))] for _ in b]
        fx, fy = fn(x), fn(y)
        if fx is not None and fy is not None: d.append(fx - fy)
    d.sort()
    return [round(d[int(0.025 * len(d))], 4), round(d[int(0.975 * len(d))], 4)] if d else None


def f_part(v): return sum(1 for o in v if o.get("comp")) / len(v)
def f_rat(v):
    r = [c["ratio"] for o in v for c in o.get("comp", []) if c.get("ratio") is not None]
    return st.mean(r) if r else None
def f_win(v):
    r = [c["ratio"] for o in v for c in o.get("comp", []) if c.get("ratio") is not None]
    return sum(1 for x in r if x > 1) / len(r) if r else None
def f_our(v):
    r = [o["pnl"] for o in v if o.get("pnl") is not None]
    return st.mean(r) if r else None


if __name__ == "__main__":
    res = {"n_fills": len(R), "runs": {}, "groups": {}, "who": {}}
    Fl = [o for o in R if o["flag"]]; Un = [o for o in R if not o["flag"]]
    L = []
    L.append("RIVALS85 - do competitors trade the deeper-limit FLAGGED T2 fills? (AMS r34-r39, live T2 fills; MEASURED on decoded chain tapes)")
    L.append("flag = other >= 6% holder (not the whale, not us) at signing AND depth < 15%. competitor = 16 of the 20 named wallets seen + 243 auto pros")
    L.append("(>= 50 buys within 2 slots after >= 1 SOL sells in a run). window = buys after the dump, in the dump's slot + next slot.")
    L.append("comp ratio = their first sell price / their buy price, net 1.25% fee each way (price basis; a partial first sell counts at its price).")
    L.append("")
    for who in ("all", "named", "pro"):
        res["who"][who] = {"flagged": summ(Fl, who), "unflagged": summ(Un, who)}
    res["groups"] = {g: summ([o for o in R if grp(o) == g]) for g in "FSHN"}
    for run in RUNS:
        v = [o for o in R if o["run"] == run]
        res["runs"][run] = {"flagged": summ([o for o in v if o["flag"]]), "unflagged": summ([o for o in v if not o["flag"]])}
    res["ci"] = {"participation_F_minus_U": boot(Fl, Un, f_part), "comp_ratio_mean_F_minus_U": boot(Fl, Un, f_rat),
                 "comp_win_F_minus_U": boot(Fl, Un, f_win), "our_pnl_mean_F_minus_U": boot(Fl, Un, f_our),
                 "comp_ratio_mean_F_minus_S": boot(Fl, [o for o in R if grp(o) == "S"], f_rat),
                 "participation_F_minus_S": boot(Fl, [o for o in R if grp(o) == "S"], f_part)}
    # before / after us
    res["side"] = {k: {side: (lambda cs: {"trades": len(cs), "ratio_mean": round(st.mean([c["ratio"] for _, c in cs if c.get("ratio")]), 4) if cs else None,
                                          "win_pct": round(100 * sum(1 for _, c in cs if (c.get("ratio") or 0) > 1) / max(1, sum(1 for _, c in cs if c.get("ratio"))), 1)})(comps(v, "all", side))
                       for side in ("before", "after")} for k, v in (("flagged", Fl), ("unflagged", Un))}
    # who is most present in flagged fills
    per = collections.defaultdict(lambda: {"F": [], "U": []})
    for o in R:
        for c in o.get("comp", []): per[c["w"]]["F" if o["flag"] else "U"].append((o, c))
    tops = sorted(per.items(), key=lambda kv: -len(kv[1]["F"]))[:15]
    def ws(lst):
        r = [c["ratio"] for _, c in lst if c.get("ratio") is not None]
        return {"fills": len(lst), "before_us_pct": round(100 * sum(1 for _, c in lst if c["before_us"]) / len(lst), 0) if lst else None,
                "ratio_mean": round(st.mean(r), 4) if r else None, "win_pct": round(100 * sum(1 for x in r if x > 1) / len(r), 0) if r else None,
                "pnl_est": round(sum(c.get("pnl_est") or 0 for _, c in lst), 3), "sol": round(sum(c["sol"] for _, c in lst), 2),
                "hold_med_slots": st.median([c["hold_slots"] for _, c in lst if c.get("hold_slots") is not None]) if any(c.get("hold_slots") is not None for _, c in lst) else None,
                "we_lost_there": sum(1 for o, _ in lst if (o.get("pnl") or 0) < 0)}
    res["top_in_flagged"] = [{"w": w, "named": (v["F"] or v["U"])[0][1]["named"], "flagged": ws(v["F"]), "unflagged": ws(v["U"])} for w, v in tops]
    # per flagged fill where we lost: did any competitor win?
    lostF = [o for o in Fl if (o.get("pnl") or 0) < 0]
    res["flagged_we_lost"] = {"fills": len(lostF), "with_comp": sum(1 for o in lostF if o.get("comp")),
                              "with_comp_winner": sum(1 for o in lostF if any((c.get("ratio") or 0) > 1 for c in o.get("comp", []))),
                              "with_comp_before_us_winner": sum(1 for o in lostF if any((c.get("ratio") or 0) > 1 and c["before_us"] for c in o.get("comp", [])))}
    # the same for unflagged where we lost
    lostU = [o for o in Un if (o.get("pnl") or 0) < 0]
    res["unflagged_we_lost"] = {"fills": len(lostU), "with_comp": sum(1 for o in lostU if o.get("comp")),
                                "with_comp_winner": sum(1 for o in lostU if any((c.get("ratio") or 0) > 1 for c in o.get("comp", []))),
                                "with_comp_before_us_winner": sum(1 for o in lostU if any((c.get("ratio") or 0) > 1 and c["before_us"] for c in o.get("comp", [])))}
    json.dump(res, open(f"{OUT}/RESULTS.json", "w"), indent=1)

    def row(name, s):
        if not s.get("fills"): return f"{name:22s} {0:5d}"
        return (f"{name:22s} {s['fills']:5d} | {s['part_pct']:5.1f}% {s['comp_wallets_per_fill']:5.2f} {s['comp_sol_per_fill']:6.2f} {str(s['before_us_pct']):>5s}% | "
                f"{str(s['ratio_mean']):>7s} {str(s['ratio_med']):>7s} {str(s['win_pct']):>5s}% {s['pnl_est_sum']:+8.2f} {str(s['hold_med_slots']):>5s} | "
                f"{s['our_pnl_mean']:+.4f} {s['our_win_pct']:5.1f}% {s['our_pnl_sum']:+7.3f}")
    H = (f"{'group':22s} {'fills':>5s} | {'part':>6s} {'w/fill':>5s} {'SOL/f':>6s} {'bef':>6s} | {'cRatio':>7s} {'cMed':>7s} {'cWin':>6s} {'cPnL':>8s} {'hold':>5s} | "
         f"{'ourPnL/f':>8s} {'ourWin':>6s} {'ourSum':>7s}")
    L.append("A. Flagged vs not (all competitors / named only / auto pros only)")
    L.append(H)
    for who in ("all", "named", "pro"):
        L.append(row(f"{who}: FLAGGED", res["who"][who]["flagged"])); L.append(row(f"{who}: not flagged", res["who"][who]["unflagged"]))
    L.append("")
    L.append("B. 2x2 (F = other6 & depth<15% = FLAGGED; S = no other6 & depth<15%; H = other6 & depth>=15%; N = neither)")
    L.append(H)
    for g in "FSHN": L.append(row(g, res["groups"][g]))
    L.append("")
    L.append("C. per run (all competitors)")
    L.append(H)
    for run in RUNS:
        L.append(row(f"{run} FLAGGED", res["runs"][run]["flagged"])); L.append(row(f"{run} not", res["runs"][run]["unflagged"]))
    L.append("")
    L.append("D. 95% cluster-bootstrap CIs (by fill): " + json.dumps(res["ci"]))
    L.append("E. before vs after our buy: " + json.dumps(res["side"]))
    L.append("F. flagged fills where WE lost: " + json.dumps(res["flagged_we_lost"]) + " | unflagged where we lost: " + json.dumps(res["unflagged_we_lost"]))
    L.append("")
    L.append("G. competitors most present in FLAGGED fills (flagged | unflagged): fills, before-us %, mean ratio, win %, est P&L SOL, hold median slots, we lost there")
    for t in res["top_in_flagged"]:
        a, b = t["flagged"], t["unflagged"]
        L.append(f"{t['w'][:8]} {('named' if t['named'] else 'pro'):5s} | F {a['fills']:3d} {str(a['before_us_pct']):>4s}% {str(a['ratio_mean']):>7s} {str(a['win_pct']):>4s}% {a['pnl_est']:+7.3f} {str(a['hold_med_slots']):>5s} lost {a['we_lost_there']:3d}"
                 f" | U {b['fills']:3d} {str(b['before_us_pct']):>4s}% {str(b['ratio_mean']):>7s} {str(b['win_pct']):>4s}% {b['pnl_est']:+7.3f} {str(b['hold_med_slots']):>5s}")
    # H. robustness: medians, per-fill weighting, fast-exit and same-slot subsets, per-run medians, our own price ratio
    def med(x): return round(st.median(x), 4) if x else None
    def wr(x): return round(100 * sum(1 for r in x if r > 1) / len(x), 1) if x else None
    rob = {}
    for nm, v in (("flagged", Fl), ("unflagged", Un), ("S_shallow_no_other6", [o for o in R if grp(o) == "S"])):
        cs = [c for o in v for c in o.get("comp", []) if c.get("ratio") is not None]
        pfm = [st.median([c["ratio"] for c in o.get("comp", []) if c.get("ratio") is not None]) for o in v if any(c.get("ratio") is not None for c in o.get("comp", []))]
        rob[nm] = {"per_fill_median_ratio": med(pfm), "per_fill_n": len(pfm),
                   "hold_le2": {"n": sum(1 for c in cs if c["hold_slots"] <= 2), "med": med([c["ratio"] for c in cs if c["hold_slots"] <= 2]), "win": wr([c["ratio"] for c in cs if c["hold_slots"] <= 2])},
                   "hold_gt2": {"n": sum(1 for c in cs if c["hold_slots"] > 2), "med": med([c["ratio"] for c in cs if c["hold_slots"] > 2]), "win": wr([c["ratio"] for c in cs if c["hold_slots"] > 2])},
                   "same_slot_as_dump": {"n": sum(1 for c in cs if c["same_slot_as_dump"]), "med": med([c["ratio"] for c in cs if c["same_slot_as_dump"]]), "win": wr([c["ratio"] for c in cs if c["same_slot_as_dump"]])},
                   "before_us": {"n": sum(1 for c in cs if c["before_us"]), "med": med([c["ratio"] for c in cs if c["before_us"]]), "win": wr([c["ratio"] for c in cs if c["before_us"]])},
                   "hold_slots_p25_50_75": [sorted(c["hold_slots"] for c in cs)[len(cs) // 4], st.median([c["hold_slots"] for c in cs]), sorted(c["hold_slots"] for c in cs)[3 * len(cs) // 4]] if cs else None,
                   "our_ratio_px_med": med([o["our_ratio_px"] for o in v if o.get("our_ratio_px")]), "our_hold_slots_med": st.median([o["our_hold_slots"] for o in v if o.get("our_hold_slots") is not None])}
    rob["per_run_trade_median"] = {run: {"F": med([c["ratio"] for o in R if o["run"] == run and o["flag"] for c in o.get("comp", []) if c.get("ratio") is not None]),
                                         "U": med([c["ratio"] for o in R if o["run"] == run and not o["flag"] for c in o.get("comp", []) if c.get("ratio") is not None])} for run in RUNS}
    rnd = random.Random(3); d = []
    trs = lambda v: [c["ratio"] for o in v for c in o.get("comp", []) if c.get("ratio") is not None]
    for _ in range(2000):
        x = [Fl[rnd.randrange(len(Fl))] for _ in Fl]; y = [Un[rnd.randrange(len(Un))] for _ in Un]; d.append(st.median(trs(x)) - st.median(trs(y)))
    d.sort(); rob["ci_trade_median_F_minus_U"] = [round(d[50], 4), round(d[1950], 4)]
    res["robust"] = rob
    # I. named wallets: presence rate flagged vs unflagged
    pres = {}
    for o in R:
        for c in o.get("comp", []):
            if c["named"]: pres.setdefault(c["named"], {"F": 0, "U": 0})["F" if o["flag"] else "U"] += 1
    res["named_presence"] = {k: {"F": v["F"], "F_pct": round(100 * v["F"] / len(Fl), 1), "U": v["U"], "U_pct": round(100 * v["U"] / len(Un), 1)} for k, v in sorted(pres.items(), key=lambda kv: -kv[1]["F"])}
    res["named_not_seen"] = [p for p, ws_ in X["meta"]["named_full"].items() if not ws_]
    json.dump(res, open(f"{OUT}/RESULTS.json", "w"), indent=1)
    L.append("")
    L.append("H. robustness: " + json.dumps(rob))
    L.append("I. named presence (fills with that wallet in the window; % of flagged / unflagged fills): " + json.dumps(res["named_presence"]) + " | not seen on any fill token: " + json.dumps(res["named_not_seen"]))
    open(f"{OUT}/RESULTS.txt", "w").write("\n".join(L) + "\n")
    print("\n".join(L))
