#!/usr/bin/env python3
"""BOTS step 9 (read-only): names + claims + >= 5 example trades per claim, with links (GMGN token page filtered to haqq; Solscan buy and
sell txs from the exec extraction, bots/hsigs.pkl), time PKT, size, hold, P&L (code-matched, after his tx costs), trigger.
Recent trades first (D6 = 10-27 23:15 -> 10-28 01:12, then D5 = 10-26 23:15 -> 10-27 23:15).
Out: bots/examples.json, bots/b9.txt"""
import sys, json, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import xlib as X
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
HQ = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
NAMES = {247: "Launch-Dump Sniper", 248: "Big-Dump Rebounder"}


def main():
    rows = pickle.load(open(f"{OUT}/b1.pkl", "rb"))
    sigs = pickle.load(open(f"{OUT}/hsigs.pkl", "rb")); codes = pickle.load(open(f"{OUT}/hcodes.pkl", "rb"))
    Z = pickle.load(open(f"{OUT}/b4_res.pkl", "rb")); meta, res = Z["meta"], Z["res"]
    pr = {m["li"]: res[i][0]["pr"] for i, m in meta.items() if m["kind"] == "lot" and res.get(i)}
    kk = {m["li"]: res[i][0]["k"] for i, m in meta.items() if m["kind"] == "lot" and res.get(i)}
    R, MI, span, CC = X.tape(); H = MI["who"]["haqq"]; ours = (MI["who"]["FRA"], MI["who"]["AMS"])
    ids, idm = L.ids_map()
    same_dump = collections.defaultdict(list)
    for r in rows:
        if r["dump"]: same_dump[(r["mint"], r["d_slot"], r["d_idx"])].append(r)

    def detail(r):
        mi = r["mi"]; a, b = span[mi]; Xr = R[a:b]; cc = CC[a:b]
        sl = Xr["slot"].astype(np.int64); ix = Xr["idx"].astype(np.int64)
        hs = np.flatnonzero((Xr["user"] == H) & (Xr["buy"] == 0) & (cc > r["cc"]) & (cc <= (r["close_cc"] or 0) + 1))
        hs = [j for j in hs.tolist() if codes.get((int(sl[j]), int(ix[j]))) == r["code"]]
        ob = (~np.isin(Xr["user"], (H,) + ours)) & (Xr["buy"] == 1) & (cc > r["cc"]) & (cc < (r["close_cc"] or r["cc"]))
        trig = None
        if r["d_slot"] is not None:
            j = np.flatnonzero((sl == r["d_slot"]) & (ix == r["d_idx"]) & (Xr["buy"] == 0))
            if len(j): trig = ids[int(Xr["user"][j[0]])]
        return dict(
            mint=r["mint"], gmgn=f"https://gmgn.ai/sol/token/{r['mint']}?maker={HQ}",
            buy_tx=f"https://solscan.io/tx/{sigs[(r['slot'], r['idx'])]}" if (r["slot"], r["idx"]) in sigs else None,
            sell_txs=[f"https://solscan.io/tx/{sigs[(int(sl[j]), int(ix[j]))]}" for j in hs if (int(sl[j]), int(ix[j])) in sigs],
            time_pkt=L.pkt(r["bt"]), size_sol=round(r["size"], 3), hold_s=round(r["hold"], 2) if r["hold"] is not None else None,
            hold_slots=int(round(r["hold"] / 0.212)) if r["hold"] is not None else None, pnl_sol=round(r["net"], 4), pnl_pct=round(100 * r["net"] / r["size"], 1),
            trigger=dict(seller=trig, seller_type=r["d_type"], drop_pct=round(100 * (r["d_drop"] or 0), 1), sell_sol=round(r["d_sol"] or 0, 3),
                         slots_dump_to_buy=r["d_slots"], ms_dump_to_buy=round(r["d_ms"] or 0), token_age_s=round(r["age"] * 0.212, 1) if r["age"] is not None else None,
                         curve_sol_before_buy=round(r["vsol"], 2)),
            trades_ahead_after_dump=kk.get(r["li"]), price_vs_post_dump=round(pr[r["li"]], 3) if r["li"] in pr else None,
            outside_buys_during_hold=int(ob.sum()), outside_buy_sol_during_hold=round(float(Xr["sol"][ob].sum()) / 1e9, 2), n_sells=len(hs))

    def pick(c, cond, n=6):
        v = [r for r in rows if r["code"] == c and r["usable"] and not r["gap"] and r["mi"] in span and (r["slot"], r["idx"]) in sigs and cond(r)]
        v.sort(key=lambda r: -r["bt"])
        rng = np.random.default_rng(c)
        recent = [r for r in v if r["day"] >= 5]
        pool = recent if len(recent) >= 3 * n else v
        ch = [pool[i] for i in sorted(rng.choice(len(pool), min(n, len(pool)), replace=False))] if pool else []
        return [detail(r) for r in ch], len(v)

    hslots = lambda r: int(round(r["hold"] / 0.212)) if r["hold"] is not None else -1
    C = {
        247: [
            ("ENTRY: buys 0-1 slot after a >= 5 % single sell by the DEV or a creation-slot BUNDLER, on a token < 6 s old (76 % of its dump buys are on tokens < 5 s old; 97 % follow a sell by a wallet that bought in the first 10 slots)",
             lambda r: r["dump"] and r["d_type"] in ("dev", "bundler") and r["age"] is not None and r["age"] * 0.212 < 6 and r["d_slots"] <= 1),
            ("ENTRY on a dev sell < 5 % (8 % of its lots, +7.6 mSOL/lot): devs sell in chunks; its buy rate on a dev's 2nd sell within 10 slots is 5.4 % vs 1.3 % on a first dev sell (b2b section 3)",
             lambda r: (r["d_drop"] or 0) < 0.05 and r["d_type"] == "dev" and r["d_slots"] is not None and r["d_slots"] <= 2),
            ("SIZE 0.40 SOL (0.27 on 10-22, 0.40 since 10-23) with NO price limit: it fills even when the crowd landed first and it pays > 7 % above the post-dump price (our +5 % guard would fail these)",
             lambda r: r["li"] in pr and pr[r["li"]] > 1.07 and r["size"] > 0.39),
            ("EXIT, winners: sold within 2 s into the follower buy wave (lots held < 2 s: +29..+44 mSOL/lot, 6/6 days)",
             lambda r: r["hold"] is not None and r["hold"] < 2 and r["net"] > 0.01),
            ("EXIT, losers: no bounce, held to a slot timer (15 / 20 / 25 / 30 slots = 3.2-6.4 s each ~7 % of lots; lots held 4-8 s: -4 mSOL/lot, 0/6 days)",
             lambda r: hslots(r) in (15, 20, 25, 30) and r["net"] < 0),
            ("GOOD vs BAD lot: the good ones see >= 3 SOL of outside buys while held",
             lambda r: r["net"] > 0.02 and r["hold"] is not None and r["hold"] < 4),
        ],
        248: [
            ("ENTRY: buys 0-2 slots after a BIG dump (drop >= 10 %, sell >= 3 SOL), any seller, tokens up to ~60 s old (buy rate rises from 0.6 % at 5-7 % drops to 10.6 % at 20-30 %)",
             lambda r: r["dump"] and (r["d_drop"] or 0) >= 0.10 and (r["d_sol"] or 0) >= 3),
            ("STACKS BEHIND 247: on the same dump, it buys after bot 247 already bought (247->248 is the most common multi-buy)",
             lambda r: r["dump"] and any(o["code"] == 247 and (o["slot"], o["idx"]) < (r["slot"], r["idx"]) for o in same_dump[(r["mint"], r["d_slot"], r["d_idx"])])),
            ("SIZE 0.25 (10-22) -> 0.30 (10-23..10-25) -> 0.40 SOL (since 10-25 23:15), NO price limit, often >= 3 trades behind and > 7 % above the post-dump price, still profitable on average",
             lambda r: r["li"] in pr and pr[r["li"]] > 1.07 and kk.get(r["li"], 0) >= 3 and r["net"] > 0),
            ("EXIT, winners: quick sell (< 2 s) on the bounce (lots held < 2 s: +12..+17 mSOL/lot, 6/6 days)",
             lambda r: r["hold"] is not None and r["hold"] < 2 and r["net"] > 0.005),
            ("EXIT, long timer ~65 slots (~14 s) when the token keeps running (lots held 15-60 s: +33 mSOL/lot)",
             lambda r: 60 <= hslots(r) <= 70),
            ("BAD lot: the dump keeps going, timer exit at a loss",
             lambda r: r["net"] < -0.01 and r["hold"] is not None and r["hold"] > 3),
        ]}
    J = {}; lines = []
    for c, cl in C.items():
        J[str(c)] = dict(name=NAMES[c], claims=[])
        lines.append(f"\n# {c} = {NAMES[c]}")
        for claim, cond in cl:
            ex, n = pick(c, cond)
            J[str(c)]["claims"].append(dict(claim=claim, matching_lots=n, examples=ex))
            lines.append(f"\n## {claim}  (matching lots: {n:,})")
            for e in ex:
                t = e["trigger"]
                lines.append(f"- {e['time_pkt']} | {e['size_sol']} SOL | hold {e['hold_s']} s ({e['hold_slots']} slots) | P&L {e['pnl_sol']:+.4f} SOL ({e['pnl_pct']:+.1f}%) | trigger: {t['seller_type']} sell "
                             f"{t['drop_pct']}% / {t['sell_sol']} SOL, {t['slots_dump_to_buy']} slots ({t['ms_dump_to_buy']} ms) before, token {t['token_age_s']} s old, curve {t['curve_sol_before_buy']} SOL | "
                             f"k ahead {e['trades_ahead_after_dump']}, price {e['price_vs_post_dump']}x post-dump | outside buys while held {e['outside_buys_during_hold']} ({e['outside_buy_sol_during_hold']} SOL)")
                lines.append(f"  GMGN {e['gmgn']}")
                lines.append(f"  buy {e['buy_tx']}  sell {' '.join(e['sell_txs'])}")
    json.dump(J, open(f"{OUT}/examples.json", "w"), indent=1)
    open(f"{OUT}/b9.txt", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines[:60]))


if __name__ == "__main__":
    main()
