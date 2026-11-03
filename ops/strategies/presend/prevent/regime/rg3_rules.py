"""REGIME step 3: task 1 (clustering + conditional P&L) and task 2 (59 cooldown rules) on the live runs, PAPER on shadow-only runs.
Writes rules.json + prints tables. usage: rg3_rules.py"""
import sys, pickle, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/prevent/regime")
import rg_lib as G
import rg2_core as C

OUT = "/home/moiz/sniper-data/prevent/regime"
D = pickle.load(open(f"{OUT}/runs.pkl", "rb"))
live, paper = D["live"], D["paper"]
PICK, TEST, R38 = G.PICK, G.TEST, ["dip_ams_r38"]
ALL = G.LIVE_ORDER

print("== TASK 1. clustering of big losses / SL exits (within-run permutation of the labels over the real trade times)")
for lab in ("big", "sl"):
    for nm, names in (("PICK", PICK), ("r37", TEST), ("r38", R38), ("all 20", ALL)):
        cl = C.clustering(live, names, lab, perms=3000 if nm != "all 20" else 3000)
        print(f"  {lab:3s} {nm:6s} events {cl[15]['n_events']:3d} | " + " | ".join(
            f"{M}m: pairs {v['obs']} vs chance {v['null_mean']:.1f} p={v['p']:.3f}" for M, v in cl.items()))
print()
print("== TASK 1b. trades that START within M min after a trigger became known (scaled to 0.696, mSOL per trade, trigger excluded)")
for trig in ("big", "sl"):
    for nm, names in (("PICK", PICK), ("r37", TEST), ("all 20", ALL)):
        co = C.conditional(live, names, trig)
        print(f"  after {trig:3s} {nm:6s} | " + " | ".join(
            f"{M}m: n {v['n_after']} {1000*(v['mean_after'] or 0):+.1f} vs {1000*v['mean_other']:+.1f}" for M, v in co.items()))
for trig in ("big", "sl"):
    for M in (5, 15, 30):
        d, p = C.conditional_perm(live, ALL, trig, M, perms=1000)
        print(f"  perm test all 20, after {trig} within {M}m: diff {1000*d:+.2f} mSOL/trade, one-sided p(worse) = {p:.3f}")
for trig in ("big", "sl"):
    for k in (3, 5, 10):
        nk = C.nextk(live, ALL, trig, k)
        print(f"  next {k} trades after a {trig}: n {nk['n']} mean {1000*nk['mean']:+.1f} mSOL (all trades {1000*nk['mean_all']:+.1f}); big-loss rate {nk['big_rate']:.1%} (all {nk['big_rate_all']:.1%})")
# two big losses within 15 min -> next trades
for M in (10, 15, 30):
    vals = []; bigs = 0
    for n in ALL:
        tr = live[n]["trades"]
        bk = [x for x in tr if x["big"]]
        for a, b in zip(bk, bk[1:]):
            if b["known"] - a["known"] <= M * 60:
                nxt = [y for y in tr if y["t"] >= b["known"]][:10]
                vals += [y["v"] for y in nxt]; bigs += sum(y["big"] for y in nxt)
    if vals:
        print(f"  next 10 trades after 2 big losses within {M}m: n {len(vals)} mean {1000*sum(vals)/len(vals):+.1f} mSOL, big rate {bigs/len(vals):.1%}")

print()
print("== TASK 2. cooldown rules (scaled to 0.696 SOL; saving = rule - no rule; + = rule better)")
rules = C.mk_rules()
rows = []
for rule in rules:
    res = C.score(live, rule)
    pk = C.summarize(res, PICK); ts = C.summarize(res, TEST); r8 = C.summarize(res, R38)
    ci = C.boot_ci(res, PICK + TEST)
    both = C.summarize(res, PICK + TEST)
    pz = sum(res[n]["paused_s"] for n in PICK + TEST) / sum(res[n]["span_s"] for n in PICK + TEST)
    pres = C.score(paper, rule)
    pp = C.summarize(pres, list(paper))
    rows.append(dict(rule=rule.name, fam=rule.fam, pick=pk, test=ts, r38=r8, both=both, ci=ci, paused=pz,
                     per_run={n: res[n]["save"] for n in ALL}, paper=pp, paper_per_run={n: pres[n]["save"] for n in paper},
                     r38_skipped_t=res["dip_ams_r38"]["skipped_t"], r37_paused=res["dip_ams_r37"]["paused_s"] / res["dip_ams_r37"]["span_s"]))
# candidates per family
cands = {}
for fam in ("C1", "C2", "C3", "C4", "C5", "C6"):
    ok = [r for r in rows if r["fam"] == fam and r["pick"]["help"] > r["pick"]["hurt"]]
    if ok:
        cands[fam] = max(ok, key=lambda r: r["pick"]["save"])["rule"]
for r in rows:
    r["cand"] = cands.get(r["fam"]) == r["rule"]
    pk, ts = r["pick"], r["test"]
    passes = ts["save"] > 0 and pk["help"] > pk["hurt"] and r["ci"][0] > 0 and r["both"]["wo1"] > 0 and r["both"]["win_sol"] <= r["both"]["los_sol"]
    lead = ts["save"] > 0 and pk["save"] > 0 and pk["help"] > pk["hurt"]
    r["verdict"] = ("PASS" if passes else "LEAD" if lead else "FAIL") if r["cand"] else ("(pass)" if passes else "-")
print(f"  {'rule':34s} {'PICK':>7s} {'h/h':>6s} {'r37':>7s} {'r38':>7s} {'P+T CI90':>15s} {'w/o1':>6s} {'w/o5':>6s} {'skipW/L':>11s} {'paused':>6s} {'PAPER':>6s} verdict")
for r in rows:
    pk, ts, r8, b = r["pick"], r["test"], r["r38"], r["both"]
    print(f"  {r['rule']:34s} {pk['save']:+7.3f} {pk['help']:2d}/{pk['hurt']:<2d} {ts['save']:+7.3f} {r8['save']:+7.3f} {r['ci'][0]:+6.2f}..{r['ci'][1]:+6.2f} {b['wo1']:+6.2f} {b['wo5']:+6.2f} {b['win_sol']:5.2f}/{b['los_sol']:<5.2f} {r['paused']:6.1%} {r['paper']['save']:+6.2f} {'*' if r['cand'] else ' '}{r['verdict']}")
json.dump(dict(rules=rows, cands=cands), open(f"{OUT}/rules.json", "w"), indent=1, default=str)
print("  candidates:", cands)
