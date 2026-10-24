#!/usr/bin/env python3
# entry / scale-in / exit / follower profile per wallet from out/pos3.json (tapes) + on-chain per-token PnL (out/chain_tokens_*.json)
import os, sys, json, collections, statistics, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib3
P = [p for p in json.load(open(os.path.join(lib3.HERE, "out/pos3.json"))) if not p.get("nobuy") and not p["mayhem"]]
med = lambda v: statistics.median(v) if v else float("nan")
def q(v, a): return statistics.quantiles(v, n=20)[int(a * 20) - 1] if len(v) >= 20 else float("nan")
HOURS = {"R1": 14.9, "R2": 21.8, "R3": 24.0}
out = {}; L = []
pr = lambda *a: L.append(" ".join(str(x) for x in a))
for w8 in lib3.W3:
    v = [p for p in P if p["w"] == w8]
    C = json.load(open(os.path.join(lib3.HERE, f"out/chain_tokens_{w8}.json")))
    o = {}
    pr(f"\n######## {w8}: {len(v)} positions on tape (R1 {sum(p['run']=='R1' for p in v)}, R2 {sum(p['run']=='R2' for p in v)}, R3 {sum(p['run']=='R3' for p in v)})")
    for run in ("R1", "R2", "R3"):
        x = [p for p in v if p["run"] == run]
        if not x: continue
        ch = [C[p["m"]]["net"] for p in x if p["m"] in C]
        o[f"act_{run}"] = dict(n=len(x), per_day=len(x) / HOURS[run] * 24, tape_pnl=sum(p["pnl"] for p in x), tape_pnl_closed=sum(p["pnl"] for p in x if not p["open"]),
                               chain_pnl=sum(ch), chain_n=len(ch), open=sum(p["open"] for p in x))
        pr(f"  {run}: {len(x)} positions = {len(x) / HOURS[run] * 24:.0f}/day | tape PnL {o[f'act_{run}']['tape_pnl']:+.2f} (closed only {o[f'act_{run}']['tape_pnl_closed']:+.2f}, open {o[f'act_{run}']['open']}) | chain PnL on {len(ch)} of them {sum(ch):+.2f}")
    # hour of day (PKT)
    hp = collections.defaultdict(lambda: [0, 0.0])
    for p in v: hp[p["hour"]][0] += 1; hp[p["hour"]][1] += C[p["m"]]["net"] if p["m"] in C else p["pnl"]
    o["by_hour"] = {h: (hp[h][0], round(hp[h][1], 2)) for h in sorted(hp)}
    pr("  by PKT hour (positions, SOL):", " ".join(f"{h:02d}h:{hp[h][0]}/{hp[h][1]:+.1f}" for h in sorted(hp)))
    # sizes
    pr(f"  first buy SOL med {med([p['b0_sol'] for p in v]):.2f} (p10 {q([p['b0_sol'] for p in v], .1):.2f}, p90 {q([p['b0_sol'] for p in v], .9):.2f}) | total in per position med {med([p['sin'] for p in v]):.2f}, p90 {q([p['sin'] for p in v], .9):.2f}")
    # entry
    E = lambda k: med([p["e_" + k] for p in v])
    o["entry"] = {k: E(k) for k in ("age", "vsol", "ch10", "ch60", "n_buyers", "n_tr", "gap", "b10", "s10", "u10", "bigsell10", "dev_sol", "bundle_n", "cs_n", "dev_sold", "dd_peak", "peak_vsol")}
    pr(f"  ENTRY (medians): token age {E('age'):.0f} s (p10 {q([p['e_age'] for p in v], .1):.0f}, p90 {q([p['e_age'] for p in v], .9):.0f}) | curve {E('vsol'):.1f} SOL (p10 {q([p['e_vsol'] for p in v], .1):.1f}, p90 {q([p['e_vsol'] for p in v], .9):.1f}) | "
       f"price chg 10 s {E('ch10'):+.0%}, 60 s {E('ch60'):+.0%} | below peak {E('dd_peak'):+.0%} | buyers before {E('n_buyers'):.0f} | trades before {E('n_tr'):.0f} | quiet gap {E('gap'):.1f} s")
    pr(f"         10 s before: buys {E('b10'):.2f} SOL, sells {E('s10'):.2f} SOL, buyers {E('u10'):.0f} | dump >=1 SOL in 10 s before: {sum(p['e_bigsell10'] >= 1 for p in v) / len(v):.0%} | "
       f"dev buy {E('dev_sol'):.2f} SOL | bundle n {E('bundle_n'):.0f} (any {sum(p['e_bundle_n'] > 0 for p in v) / len(v):.0%}) | create-slot buyers {E('cs_n'):.0f} | dev already sold some {sum(p['e_dev_sold'] > 0 for p in v) / len(v):.0%}, all {sum(p['e_dev_sold'] > 0.99 for p in v) / len(v):.0%}")
    pr(f"         is creator {sum(p['isdev'] for p in v)} | buys in create slot {sum(p['create_slot'] for p in v)} | in glued bundle {sum(p['in_bundle'] for p in v)} | first buy position in block med {med([p['pos_ms_in_slot'] for p in v]):.0f} ms of 212")
    # scale in
    nb = [p["nb"] for p in v]
    multi = [p for p in v if p["nb"] > 1]
    pr(f"  SCALE-IN: buys per token med {med(nb):.0f}, mean {statistics.mean(nb):.1f}, 1 buy {sum(1 for x in nb if x == 1) / len(nb):.0%}, 2-3 {sum(1 for x in nb if 2 <= x <= 3) / len(nb):.0%}, 4+ {sum(1 for x in nb if x >= 4) / len(nb):.0%} | "
       f"when >1: 2nd buy after {med([p['buy_ts'][1] for p in multi]):.1f} s, last buy {med([p['buy_ts'][-1] for p in multi]):.1f} s, first buy share of total {med([p['buy_sols'][0] / sum(p['buy_sols']) for p in multi]):.0%}" if multi else "  SCALE-IN: single buys only")
    o["scale"] = dict(nb_med=med(nb), nb_mean=statistics.mean(nb), one=sum(1 for x in nb if x == 1) / len(nb))
    # exit
    cl = [p for p in v if p["ns"] > 0]
    X = lambda k: med([p[k] for p in cl if p.get(k) is not None])
    pr(f"  EXIT: hold (first buy -> last sell) med {X('hold'):.0f} s (p10 {q([p['hold'] for p in cl], .1):.0f}, p90 {q([p['hold'] for p in cl], .9):.0f}) | first sell after {X('t_first_sell'):.0f} s | sells per token med {X('ns'):.0f}, 1 sell {sum(p['ns'] == 1 for p in cl) / len(cl):.0%} | "
       f"first sell size {X('x_frac_first'):.0%} of tokens")
    pr(f"        price at first sell vs avg entry {X('x_ret_px'):.2f}x | vs peak before it {X('x_vs_peak'):.2f} | MFE {X('mfe'):.2f}x MAE {X('mae'):.2f}x | return med {X('ret'):+.1%}")
    pr(f"        just before the first sell (10 s): dev sold {sum(p['x_dev_sold'] for p in cl) / len(cl):.0%} | net flow {X('x_net10'):+.2f} SOL | sells {X('x_sells10'):.0f}, buys {X('x_buys10'):.0f} | dump >=1 SOL {sum(p['x_bigsell10'] >= 1 for p in cl) / len(cl):.0%} | "
       f"previous trade a sell {sum(p['x_prev_is_sell'] for p in cl) / len(cl):.0%} | in the same slot as previous trade {sum(p['x_prev_same_slot'] for p in cl) / len(cl):.0%}")
    tf = sorted(p["t_first_sell"] for p in cl)
    pr(f"        timer check: first-sell time p10 {q(tf, .1):.0f} p25 {q(tf, .25):.0f} p50 {q(tf, .5):.0f} p75 {q(tf, .75):.0f} p90 {q(tf, .9):.0f} s (a fixed timer would make these close)")
    o["exit"] = {k: X(k) for k in ("hold", "t_first_sell", "ns", "x_ret_px", "x_vs_peak", "mfe", "mae", "ret", "x_net10", "x_frac_first")}
    # followers / exit liquidity
    pr(f"  FOLLOWERS: outside buys within 1 slot of their first buy med {med([p['fol1'] for p in v]):.0f} ({sum(p['fol1'] > 0 for p in v) / len(v):.0%} have >=1), SOL {med([p['fol1_sol'] for p in v]):.2f} | within 5 s {med([p['fol5s'] for p in v]):.0f} buys / {med([p['fol5s_sol'] for p in v]):.2f} SOL | "
       f"same slot {sum(p['fol_sameslot'] > 0 for p in v) / len(v):.0%}")
    pr(f"        outside buying between their first buy and first sell: {X('x_out_buy_sol'):.2f} SOL from {X('x_out_buyers'):.0f} buyers (vs their buy {med([p['sin'] for p in cl]):.2f}) | outside selling {X('x_out_sell_sol'):.2f}")
    # profit vs follower flow
    cl2 = sorted(cl, key=lambda p: p["x_out_buy_sol"] / max(p["sin"], 0.01))
    k3 = len(cl2) // 3
    parts = [cl2[:k3], cl2[k3:2 * k3], cl2[2 * k3:]]
    pr("        PnL by outside-buy SOL (relative to their size) before their first sell, low/mid/high third: " + " | ".join(
        f"{med([p['x_out_buy_sol'] / p['sin'] for p in g]):.1f}x their size -> tape PnL {sum(p['pnl'] for p in g):+.1f} SOL, win {sum(p['pnl'] > 0 for p in g) / len(g):.0%}" for g in parts))
    nofol = [p for p in v if p["fol5s"] == 0]
    pr(f"        positions with no outside buy within 5 s: {len(nofol)} -> PnL {sum(p['pnl'] for p in nofol):+.2f}; with >=1: {len(v) - len(nofol)} -> {sum(p['pnl'] for p in v if p['fol5s'] > 0):+.2f}")
    o["followers"] = dict(fol1_med=med([p["fol1"] for p in v]), fol1_any=sum(p["fol1"] > 0 for p in v) / len(v), fol5s_sol=med([p["fol5s_sol"] for p in v]), out_buy_before_sell=X("x_out_buy_sol"),
                          terciles=[(med([p["x_out_buy_sol"] / p["sin"] for p in g]), sum(p["pnl"] for p in g), len(g)) for g in parts])
    out[w8] = o
json.dump(out, open(os.path.join(lib3.HERE, "out/profile.json"), "w"), indent=1)
open(os.path.join(lib3.HERE, "out/profile.txt"), "w").write("\n".join(L) + "\n")
print("\n".join(L))
