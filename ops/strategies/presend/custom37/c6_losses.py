#!/usr/bin/env python3
"""CUSTOM37 step 6 [MEASURED]: r37 loss decomposition. Every live r37 fill with its realized P&L, arm-time features, the dump that
filled us (depth vs the try's signing price), our fill price vs the dip's low, what traded in our hold (chain tape, our wallet out),
a loss bucket, and what each knob would have done to that window (the grid's paired replay, mean over reps).
Buckets (first match): FLAT (no outside trade of >= 0.01 SOL between our fill and our sell), CASCADE (outside sells in our hold >= 1 SOL and net
selling >= 0.5 SOL: 'whale 2nd leg' if the whale sold in our hold, else 'second dumper'), SHALLOW ENTRY (dump depth at our fill
< 15% and our entry >= 5% above the dip's low in the next 2 s), DRIFT (the rest: small sells / no rebound).
Out: stdout + /home/moiz/sniper-data/custom37/losses.json + losses.md"""
import sys, json, pickle, datetime, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/custom37")
import c37lib as L

pkt = lambda t_ms: datetime.datetime.fromtimestamp(t_ms / 1e3, datetime.UTC) + datetime.timedelta(hours=5)
KNOBS = ["drop0.10", "drop0.15", "drop0.18", "quote_a0.7_f0.12_c0.16", "quote_a0.8_f0.12_c0.18", "size0.5", "size0.85", "exit100", "exit300", "tp10", "tp_off", "sl10",
         "flat1000", "q3:2", "win6", "win15", "dl2", "k4", "k12"]


def main():
    X, wins, R = L.load("r37")
    G = pickle.load(open(f"{L.D}/grid.pkl", "rb"))
    gw = G["runs"]["r37"]["wins"]; gi = {(w["ses"], w["w"]): n for n, w in enumerate(gw)}
    base = G["runs"]["r37"]["res"]["base"][0.0]
    rows = []
    for P in wins:
        if not P.fill: continue
        ft = next(tr for tr in P.tries if tr["sig"] == P.fill["sig"])
        fs, fi = P.fill["slot"], P.fill["idx"]; ss, si = P.sell["slot"], P.sell["idx"]
        Vb, Tb, kn = L.state_before(P, fs, fi)
        p_sign = ft["vsol"] / ft["vtok"]; p_pre = Vb / Tb; p_trig = P.V0 / P.T0
        depth = 1 - p_pre / p_sign
        # the dump(s) that filled us: outside sells in the fill's slot before our fill, and the last sell before it
        last_sell = next((P.out[q] for q in range(kn - 1, -1, -1) if not P.out[q][3]), None)
        dump_sol = last_sell[4] / 1e9 if last_sell else 0.0
        dump_whale = bool(last_sell and last_sell[6] == P.whale)
        # hold: outside trades with chain position in (fill, sell)
        hold = [x for x in P.out if (fs, fi) < (x[0], x[1]) < (ss, si)]
        sells = [x for x in hold if not x[3]]; buys = [x for x in hold if x[3]]
        s_sol = sum(x[4] for x in sells) / 1e9; b_sol = sum(x[4] for x in buys) / 1e9
        wh_hold = any(x[6] == P.whale for x in sells)
        # the dip's low: min clean price from our fill to 2 s later (block clock), our own trades out
        c0 = P.cc(fs, fi)
        lows = [x[7] / x[8] for q, x in enumerate(P.out) if q >= kn and P.c[q] <= c0 + 2000]
        p_low = min([p_pre] + lows)
        p_sell_pre = (lambda s: s[0] / s[1])(L.state_before(P, ss, si))
        pnl = P.live_pnl / 1e9
        if not [x for x in hold if x[4] >= 10_000_000]: b = "FLAT"      # no outside trade of >= 0.01 SOL in our hold
        elif s_sol >= 1.0 and s_sol - b_sol >= 0.5: b = "CASCADE (whale 2nd leg)" if wh_hold else "CASCADE (second dumper)"
        elif depth < 0.15 and p_pre / p_low - 1 >= 0.05: b = "SHALLOW ENTRY"
        else: b = "DRIFT"
        n = gi.get((P.W["ses"], P.W["w"]))
        kn_eff = {}
        if n is not None:
            for k in KNOBS:
                A = G["runs"]["r37"]["res"][k][0.0]
                kn_eff[k] = ((A[n, 1] + A[n, 2]) - (base[n, 1] + base[n, 2])) / 1e9
        tg = P.W["trig"]; q = P.W.get("quiet") or {}; v2 = P.W.get("v2") or {}
        rows.append({"mint": P.mint, "t": pkt(P.fill["t"] / 1e6).strftime("%H:%M:%S"), "pnl": pnl, "bucket": b, "age": tg["age_slots"], "pct": tg["pct"], "wsol": tg["sol"] / 1e9,
                     "vsol": tg["vsol"] / 1e9, "fulldrop": L.full_drop(P), "wh_dumps": q.get("wh_dumps"), "wh_fol": q.get("wh_fol"), "n60": v2.get("n_tr_60s"),
                     "depth": depth, "dump_sol": dump_sol, "dump_whale": dump_whale, "drop_vs_trig": 1 - p_pre / p_trig, "entry_vs_low": p_pre / p_low - 1,
                     "hold_move": p_sell_pre / p_pre - 1, "n_sell": len(sells), "sell_sol": s_sol, "n_buy": len(buys), "buy_sol": b_sol, "whale_sold_hold": wh_hold,
                     "exit": P.exit["why"], "held_ms": (P.sell["t"] - P.fill["t"]) / 1e6, "knobs": kn_eff, "slots_after_trig": fs - P.s0})
    json.dump(rows, open(f"{L.D}/losses.json", "w"))
    out = []
    def p(s=""): print(s); out.append(s)
    allp = np.array([r["pnl"] for r in rows])
    p(f"r37 live fills {len(rows)} (cut {pkt(X['meta']['t1'] / 1e6):%H:%M} PKT): realized {allp.sum():+.3f} SOL; winners {np.sum(allp > 0)} {allp[allp > 0].sum():+.3f}; "
      f"losers {np.sum(allp < 0)} {allp[allp < 0].sum():+.3f}")
    fees = sum(1 for P in wins for tr in P.tries if tr["land"] is not None and tr["res"] != "ok") * L.FAIL / 1e9
    p(f"failed-try fees (landed failed tries x 5120): {-fees:+.3f} SOL; ATA rent refunds not in realized: +{len(rows) * L.REFUND / 1e9:.3f} SOL")
    p("")
    p("LOSS BUCKETS (all r37 losers, realized < 0)")
    p("| bucket | n | sum SOL | mean mSOL | of them <= -0.02 | median dump depth | median entry above low | median hold sells SOL |")
    p("|---|---|---|---|---|---|---|---|")
    by = collections.defaultdict(list)
    for r in rows:
        if r["pnl"] < 0: by[r["bucket"]].append(r)
    for b in ("CASCADE (whale 2nd leg)", "CASCADE (second dumper)", "SHALLOW ENTRY", "DRIFT", "FLAT"):
        v = by.get(b, [])
        if not v: continue
        s = sum(r["pnl"] for r in v)
        p(f"| {b} | {len(v)} | {s:+.3f} | {s / len(v) * 1e3:+.1f} | {sum(1 for r in v if r['pnl'] <= -0.02)} | {np.median([r['depth'] for r in v]):.1%} | "
          f"{np.median([r['entry_vs_low'] for r in v]):.1%} | {np.median([r['sell_sol'] for r in v]):.2f} |")
    p(f"| failed-try fees | {sum(1 for P in wins for tr in P.tries if tr['land'] is not None and tr['res'] != 'ok')} tries | {-fees:+.3f} | 0.00512 each | | | | |")
    p("")
    p("WINNERS for comparison: " + ", ".join(f"{b} {sum(1 for r in rows if r['pnl'] > 0 and r['bucket'] == b)}" for b in ("CASCADE (whale 2nd leg)", "CASCADE (second dumper)", "SHALLOW ENTRY", "DRIFT", "FLAT")))
    p("")
    p("ALL r37 LOSERS AT OR BELOW -0.02 SOL (time = our fill, PKT; knob = the best single knob for THIS window in the paired replay, mSOL)")
    p("| time | mint (GMGN) | P&L | bucket | age sl | whale % / SOL | curve SOL | full-dump drop | dump depth / SOL (W = whale) | entry above low | hold: sells n/SOL, buys n/SOL | exit | best single knob for it | custom quote A |")
    p("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted([r for r in rows if r["pnl"] <= -0.02], key=lambda r: r["pnl"]):
        kb = max(r["knobs"].items(), key=lambda kv: kv[1]) if r["knobs"] else ("-", 0)
        kt = f"{kb[0]} {kb[1] * 1e3:+.0f}" if kb[1] > 0.005 else "none"
        p(f"| {r['t']} | [{r['mint'][:6]}](https://gmgn.ai/sol/token/{r['mint']}) | {r['pnl']:+.4f} | {r['bucket']} | {r['age']} | {r['pct']:.1f} / {r['wsol']:.2f} | {r['vsol']:.1f} | "
          f"{r['fulldrop']:.0%} | {r['depth']:.0%} / {r['dump_sol']:.2f}{' W' if r['dump_whale'] else ''} | {r['entry_vs_low']:.1%} | {r['n_sell']}/{r['sell_sol']:.2f}, {r['n_buy']}/{r['buy_sol']:.2f} | "
          f"{r['exit']} | {kt} | {r['knobs'].get('quote_a0.7_f0.12_c0.16', 0) * 1e3:+.0f} |")
    p("")
    # knob effect on losers vs winners
    p("KNOBS on r37 losers (<= -0.02) vs winners (paired replay, SOL; + = better)")
    p("| knob | on losers | on winners | on all fills | windows helped / hurt (by more than 5 mSOL) |")
    p("|---|---|---|---|---|")
    for k in KNOBS:
        lo = sum(r["knobs"].get(k, 0) for r in rows if r["pnl"] <= -0.02); wi = sum(r["knobs"].get(k, 0) for r in rows if r["pnl"] > 0)
        al = sum(r["knobs"].get(k, 0) for r in rows)
        hp = sum(1 for r in rows if r["knobs"].get(k, 0) > 0.005); ht = sum(1 for r in rows if r["knobs"].get(k, 0) < -0.005)
        p(f"| {k} | {lo:+.3f} | {wi:+.3f} | {al:+.3f} | {hp} / {ht} |")
    open(f"{L.D}/losses.md", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
