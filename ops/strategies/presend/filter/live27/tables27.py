#!/usr/bin/env python3
"""LIVE27 step 5: the report's detail tables (markdown) from the replay pickles and effects JSONs.
  * the 36 skipped triggers: per group and per window (stream C = armed with the stop rule; B = armed, no stop), with the tape's
    story (whale's first sell, the dump, buyers after it)
  * the 45 stopped windows: after the stop (D - A0) per window with a fill, fees after the stop
  * the sensitivity table across landing pools / stress tests
usage: tables27.py [POOL] [TAG]"""
import sys, os, json, pickle, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib27 as L
import sim
import effects27 as E

RENT = 5020


def net(r, fw=1.0): return E.adj_net(r, fw)


def grp(dr, keys, fw=1.0):
    """per draw totals over keys: fills, wins, realized, fees, net (SOL)"""
    f = [sum(by[k]["filled"] for k in keys if k in by) for _, by in dr]
    w = [sum(1 for k in keys if k in by and by[k]["filled"] and by[k]["pnl"] - RENT > 0) for _, by in dr]
    p = [sum((by[k]["pnl"] - RENT) * (fw if by[k]["pnl"] - RENT > 0 else 1) for k in keys if k in by and by[k]["filled"]) / 1e9 for _, by in dr]
    fe = [sum(by[k]["fees"] for k in keys if k in by and by[k]["armed"]) / 1e9 for _, by in dr]
    n = [sum(net(by[k], fw) for k in keys if k in by) / 1e9 for _, by in dr]
    return {a: (float(np.mean(v)), float(np.percentile(v, 5)), float(np.percentile(v, 95))) for a, v in
            (("fills", f), ("wins", w), ("pnl", p), ("fees", fe), ("net", n))}


def story(tp, mint, slot, idx, whale, upto=12):
    """the tape after the trigger: the first trade that takes the price 12% under its high since the trigger (the pre-send limit),
    the sells in that slot (whale or not), the low, and the buys within 2 slots after the low (not ours)"""
    tk = sim.Tok(tp, mint, slot - 2, slot + upto + 4)
    idm = tp.id_map(); wid = idm.get(whale)
    kt = tk.before(slot, idx + 0.5)
    if kt < 0: return "no tape"
    pr = lambda x: tk.vsol[x] / tk.vtok[x]
    p0 = pr(kt); hi = p0; xc = None
    for x in range(kt + 1, tk.n):
        if tk.s[x] > slot + upto: break
        if pr(x) <= 0.88 * hi: xc = x; break
        hi = max(hi, pr(x))
    if xc is None:
        o = sum(1 for x in range(kt + 1, tk.n) if tk.s[x] <= slot + 10 and tk.user[x] != wid)
        return f"no 12% drop within {upto} slots ({o} other trades in 10 slots)"
    s_d = tk.s[xc]
    sells = [x for x in range(kt + 1, tk.n) if tk.s[x] == s_d and not tk.buy[x]]
    sol_out = sum(tk.sol[x] for x in sells) / 1e9; wh = any(tk.user[x] == wid for x in sells)
    cand = [x for x in range(xc, tk.n) if tk.s[x] <= s_d + 1]
    low = min(cand, key=pr)
    buys = [x for x in range(low + 1, tk.n) if tk.buy[x] and tk.s[x] <= s_d + 2 and tk.user[x] != tp.our_id]
    bsol = sum(tk.sol[x] for x in buys) / 1e9
    after = [x for x in range(low + 1, tk.n) if tk.s[x] <= s_d + 2]
    p2 = pr(after[-1]) if after else pr(low)
    return (f"dump at +{s_d - slot}: {len(sells)} sells{' incl. the whale' if wh else ' (not the whale)'}, {sol_out:.1f} SOL, low {100 * (pr(low) / hi - 1):+.0f}% "
            f"from the high; then {len(buys)} buys ({bsol:.1f} SOL) in 2 slots, {100 * (p2 / pr(low) - 1):+.0f}% off the low")


if __name__ == "__main__":
    pool = sys.argv[1] if len(sys.argv) > 1 else "P3"; tag = sys.argv[2] if len(sys.argv) > 2 else "main"
    Z = pickle.load(open(f"{L.DATA}/replay27_{pool}_{tag}.pkl", "rb"))
    M = Z["meta"]; lv = {x["key"]: x for x in M["live"]}; sk = {x["key"]: x for x in M["skip"]}
    EJ = json.load(open(f"{L.DATA}/effects27_{pool}_{tag}.json"))
    fw1, fw2 = EJ["fw_no120"], EJ["fw_all"]
    R = L.load_run(); tp = L.Tape27(R)
    SK = list(sk); ST = [k for k, x in lv.items() if x["d_stop"] is not None]
    f3 = lambda t, f="%+.4f": (f % t[0]) + " (" + (f % t[1]) + " to " + (f % t[2]) + ")"
    print(f"## pool {pool} {tag}\n")
    print("### 36 skipped triggers, armed (model)\n")
    print("| Case | Fills | Wins | Realized | Failed-try fees | Net = given up |")
    print("|---|---|---|---|---|---|")
    for lab, s, fw in (("Armed with the stop rule (as QUIET-skip-off would run)", "C", 1.0), ("Armed, no stop rule", "B", 1.0),
                       (f"Armed with the stop rule, calibrated (wins x {fw1:.2f})", "C", fw1), (f"Armed with the stop rule, calibrated (wins x {fw2:.2f})", "C", fw2)):
        g = grp(Z["out"][s], SK, fw)
        print(f"| {lab} | {g['fills'][0]:.1f} | {g['wins'][0]:.1f} | {f3(g['pnl'])} | {g['fees'][0]:.4f} | **{f3(g['net'])}** |")
    # iso check
    iso = {name: [(s, by) for s, d in Z["out"]["iso"] for name2, by in d.items() if name2 == name] for name in ("skip_full", "skip_qstop", "stop_after", "stop_live")}
    gi = grp(iso["skip_qstop"], SK); gb = grp(iso["skip_full"], SK)
    print(f"\nEach window alone (no other window around): with stop {gi['net'][0]:+.4f} ({gi['fills'][0]:.1f} fills), no stop {gb['net'][0]:+.4f} ({gb['fills'][0]:.1f} fills)\n")
    print("Per window (C = with stop rule; B = no stop):\n")
    print("| # | PKT | Mint | Whale % | Fill p (C) | Net (C) | Net (B) | P&L if filled | Stopped at +6 (C) | Tape |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for i, k in enumerate(SK):
        x = sk[k]
        C = [by[k] for _, by in Z["out"]["C"]]; B = [by[k] for _, by in Z["out"]["B"]]
        pf = [r["pnl"] - RENT for r in B if r["filled"]]
        st = story(tp, x["mint"], x["slot"], x["idx"], x["whale"])
        print(f"| S{i} | {L.hm(x['t_ns'])} | {x['mint'][:8]} | {x['pct']:.1f} | {np.mean([r['filled'] for r in C]):.2f} | {np.mean([net(r) for r in C]) / 1e9:+.4f} | "
              f"{np.mean([net(r) for r in B]) / 1e9:+.4f} | {(np.mean(pf) / 1e9) if pf else float('nan'):+.4f} | {np.mean([bool(r['q_stop']) for r in C]):.2f} | {st} |")
    print("\n### 45 stopped windows, after the stop (model; tries before the stop never fill, as live)\n")
    gD = grp(Z["out"]["D"], ST); gA = grp(Z["out"]["A0"], ST)
    print("| | Fills | Wins | Realized | Failed-try fees | Net |")
    print("|---|---|---|---|---|---|")
    print(f"| Stopped at the live time (A0; live: 0 fills, fees 0.0050, net -0.0050) | {gA['fills'][0]:.1f} | {gA['wins'][0]:.1f} | {f3(gA['pnl'])} | {gA['fees'][0]:.4f} | {f3(gA['net'])} |")
    print(f"| Run to the window end (D) | {gD['fills'][0]:.1f} | {gD['wins'][0]:.1f} | {f3(gD['pnl'])} | {gD['fees'][0]:.4f} | {f3(gD['net'])} |")
    dd = np.array([sum(net(by.get(k) or {"armed": False}) for k in ST) for _, by in Z["out"]["D"]]) - np.array([sum(net(by[k]) for k in ST) for _, by in Z["out"]["A0"]])
    print(f"| **Given up by stopping (D - A0)** | | | | {gD['fees'][0] - gA['fees'][0]:.4f} extra | **{dd.mean() / 1e9:+.4f}** ({np.percentile(dd, 5) / 1e9:+.4f} to {np.percentile(dd, 95) / 1e9:+.4f}) |")
    for ph in ("warm", "on"):
        ks = [k for k in ST if lv[k]["phase"] == ph]
        d1 = np.array([sum(net(by.get(k) or {"armed": False}) for k in ks) for _, by in Z["out"]["D"]]) - np.array([sum(net(by[k]) for k in ks) for _, by in Z["out"]["A0"]])
        fl = np.mean([sum((by.get(k) or {}).get("filled", False) for k in ks) for _, by in Z["out"]["D"]])
        print(f"|   {ph} ({len(ks)} windows) | {fl:.2f} | | | | {d1.mean() / 1e9:+.4f} |")
    print("\nStopped windows with a fill after the stop in any draw:\n")
    print("| w | Phase | PKT | Mint | Others at +6 (live) | Fill p after stop | Given up (mean) | P&L if filled | Tape |")
    print("|---|---|---|---|---|---|---|---|---|")
    for k in ST:
        x = lv[k]
        Dd = [by.get(k) for _, by in Z["out"]["D"]]; Aa = [by[k] for _, by in Z["out"]["A0"]]
        fp = np.mean([bool(a and a["filled"]) for a in Dd])
        if fp == 0: continue
        g = np.mean([(net(a) if a else 0) - net(b) for a, b in zip(Dd, Aa)]) / 1e9
        pf = [a["pnl"] - RENT for a in Dd if a and a["filled"]]
        oth = (R["W"][k[1]]["disarm"].get("quiet") or {}).get("others")
        st = story(tp, x["mint"], x["slot"], x["idx"], R["W"][k[1]]["arm"]["trig"]["wallet"])
        print(f"| w{k[1]} | {x['phase']} | {L.hm(x['t_ns'])} | {x['mint'][:8]} | {oth} | {fp:.2f} | {g:+.4f} | {np.mean(pf) / 1e9:+.4f} | {st} |")
    # stopped windows: fees after the stop and stop timing
    fa = np.mean([sum((by.get(k) or {}).get("fees_after") or 0 for k in ST) for _, by in Z["out"]["D"]]) / 1e9
    sa = np.mean([sum((by.get(k) or {}).get("sent_after") or 0 for k in ST) for _, by in Z["out"]["D"]])
    print(f"\nTries after the stop (D): {sa:.0f} sent, landed-failed fees {fa:.4f} SOL")
    # blocked live windows (knock-on)
    print("\n### Knock-on: live windows the counterfactual blocks\n")
    for s in ("C", "D", "B"):
        c = collections.Counter(k for _, by in Z["out"][s] for k, r in by.items() if not r["armed"] and k[0] == "L")
        print(f"- {s}: " + ", ".join(f"w{k[1]} {lv[k]['mint'][:8]} {L.hm(lv[k]['t_ns'])} live {lv[k]['live']['net'] / 1e9:+.4f} ({v / len(Z['out'][s]) * 100:.0f}% of draws)" for k, v in c.items()))
