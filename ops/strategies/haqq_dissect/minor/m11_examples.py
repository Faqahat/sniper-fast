#!/usr/bin/env python3
"""MINOR step 11 (read-only): bot names, claims with >= 5 example trades each (GMGN token link filtered to haqq, Solscan buy / sell
links, PKT time, size, hold, P&L, trigger), recent days first; plus the per-day reconciliation table.
Out: minor/examples.json, minor/m11.txt"""
import json, pickle, sys, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
from plib import Out
OUT = "/home/moiz/sniper-data/haqq_dissect/minor"
H = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
pkt = lambda t: time.strftime("%m-%d %H:%M:%S", time.gmtime(int(t) + 18000))
NAMES = {244: "Binary-Timer Dipper (0.25 SOL, no limit, 8/16/32/64-slot timers, 50% partials, 0.01 shadow tier)",
         226: "Band Bouncer (0.5 SOL, +-9% band limit, ~1 s flip)",
         231: "Band Bouncer Jr. (0.25 SOL, same band, dev dumps on brand-new tokens)",
         234: "Dead-Curve Fisher (0.5-1.25 SOL at the 30-SOL floor, take-profit or 20/32-min timer)",
         249: "Probe-then-Scale Tester (0.01 -> 0.395 SOL, 42 s timer; switched off after 10-25)",
         251: "4-Second Momentum Flipper (0.1-0.4 SOL after heavy outside buying, 19-20 slot timer)",
         252: "Micro Momentum Probe (0.01 SOL, 2-3 slot exit; ran only 10-24 and 10-26)"}


def trig(l):
    x = l["ctx"] or {}
    if l["vsol_pre"] <= 30.6: s = f"curve at the floor ({l['vsol_pre']:.2f} SOL) after "
    else: s = ""
    if x.get("d_drop") and x["d_drop"] > 0:
        s += f"{x.get('d_type')} sell -{100 * x['d_drop']:.0f}% ({x['d_sol']:.2f} SOL) {x['d_slots']} slot(s) before"
    else: s += "no outside sell in the 5 slots before"
    s += f"; token age {l['age']} slots; outside buys last 3 slots {x.get('bo3', 0):.2f} SOL"
    if l["others"]: s += f"; other haqq bots holding: {','.join(map(str, l['others']))}"
    return s


def ex(l):
    sells = l["sells"]
    return dict(mint=l["ms"], gmgn=f"https://gmgn.ai/sol/token/{l['ms']}?maker={H}", buy_tx=f"https://solscan.io/tx/{l['sig']}" if l["sig"] else None,
                sell_tx=f"https://solscan.io/tx/{sells[0][4]}" if sells and sells[0][4] else None,
                sell_tx2=f"https://solscan.io/tx/{sells[-1][4]}" if len(sells) > 1 and sells[-1][4] else None,
                time_pkt=pkt(l["bt"]), size_sol=round(l["spend"], 3), hold_slots=l["hold_sl"], hold_s=round(l["hold_ms"] / 1000, 2) if l["hold_ms"] else None,
                first_sell_fraction=round(sells[0][2], 2) if sells else None, pnl_sol=round(l["net"], 4), trigger=trig(l))


def fex(f):
    return dict(mint=f["mint"], gmgn=f"https://gmgn.ai/sol/token/{f['mint']}?maker={H}", failed_buy_tx=f"https://solscan.io/tx/{f['sig']}",
                time_pkt=pkt(f["bt"]), error=f["ecode"], cu_price=f["cup"])


def pick(v, n=6):
    v = sorted(v, key=lambda l: -l["bt"]); out = []; seen = set()
    for l in v:
        if l["ms"] in seen or not l["sig"] or not l["sells"]: continue
        seen.add(l["ms"]); out.append(l)
        if len(out) >= n: break
    return out


def main():
    lots = pickle.load(open(f"{OUT}/m2_lots.pkl", "rb"))
    fails = pickle.load(open(f"{OUT}/m1.pkl", "rb"))["fails"]
    C = collections.defaultdict(list)
    for l in lots:
        if not l["mayhem"]: C[l["code"]].append(l)
    dump = lambda l, lim=2: l["ctx"] and (l["ctx"].get("d_drop") or 0) >= 0.05 and l["ctx"].get("d_slots") is not None and l["ctx"]["d_slots"] <= lim
    tim = lambda s, ts: s is not None and any(abs(s - t) <= 1 for t in ts)
    claims = {
        244: [("ENTRY: 0.247 SOL, no price limit, right after a >=5% dump on a young token (47% of its 0.247 lots); the rest are non-dump buys on active young tokens",
               lambda l: abs(l["spend"] - 0.247) < 0.002 and dump(l, 3) and l["age"] is not None and l["age"] <= 60),
              ("EXIT: first sell on a power-of-two timer menu (exactly 8, 16, 32 or 64 slots after the buy)", lambda l: tim(l["first_sl"], (8, 16, 32, 64))),
              ("EXIT: 33% of lots sell 50% first and the rest later (partial ladder)", lambda l: l["f1"] is not None and 0.45 <= l["f1"] <= 0.55 and l["nsell"] == 2),
              ("SIZE: a 0.01 SOL 'shadow' tier on the same logic (2,281 lots; same timers and partials; +5..8%/SOL gross but -2%/SOL after 0.79 mSOL tx cost)",
               lambda l: l["spend"] <= 0.011)],
        226: [("ENTRY: 0.494 SOL within 0-5 slots of a dev/bundler dump on a token 8-30 slots old", lambda l: dump(l, 5) and (l["ctx"].get("d_type") in ("dev", "bundler")) and l["age"] is not None and l["age"] <= 30),
              ("EXIT: one sell 2-7 slots (0.5-1.5 s) after the buy", lambda l: l["first_sl"] is not None and 2 <= l["first_sl"] <= 7),
              ("INTERACTION: buys while bot 247 already holds the token (58% of its lots)", lambda l: 247 in l["others"])],
        231: [("ENTRY: 0.247 SOL (0.494 on 10-22/10-23) after a dev dump on a brand-new token (age <= 30 slots)", lambda l: dump(l, 5) and l["ctx"].get("d_type") == "dev" and l["age"] is not None and l["age"] <= 30),
              ("EXIT: one sell 3-20 slots after the buy (timer peaks 5, 8, 20)", lambda l: l["first_sl"] is not None and 3 <= l["first_sl"] <= 20),
              ("INTERACTION: co-buys the same dump as 247 (55% of its dump lots)", lambda l: 247 in l["others"] and l["po_code"] == 247 and l["po_ms"] is not None and l["po_ms"] <= 500)],
        234: [("ENTRY: buys in the same slot after an outside sell takes the curve back to ~30 SOL (launch price); 96% of its buys start at curve <= 30.6 SOL",
               lambda l: l["vsol_pre"] <= 30.6 and l["ctx"] and l["ctx"].get("d_slots") == 0),
              ("EXIT (loss side): no revival -> sells on a long timer, 5,650 or 9,000 slots (20 / 32 min) later", lambda l: tim(l["hold_sl"], (5650, 5651, 9000, 9001))),
              ("EXIT (win side): revival -> early sell well above entry (take-profit); these 798 lots make +94 SOL vs -89 SOL on timer lots", lambda l: not tim(l["hold_sl"], (50, 51, 100, 101, 300, 301, 5650, 5651, 9000, 9001)) and l["net"] > 0.05),
              ("EXIT: short timers 50 / 100 / 300 slots", lambda l: tim(l["hold_sl"], (50, 51, 100, 101, 300, 301)))],
        249: [("SIZE: 0.01 SOL lots on 10-22 (399 lots), then 0.395 SOL on 10-24, switched off after 10-25", lambda l: True),
              ("EXIT: one sell exactly 200-202 slots (42.5 s) after the buy", lambda l: tim(l["hold_sl"], (200, 201, 202)))],
        251: [("ENTRY: after heavy outside buying (>= 4 SOL in the last 3 slots) on tokens > 25 slots old", lambda l: l["ctx"] and (l["ctx"].get("bo3") or 0) >= 4 and (l["age"] or 0) > 25),
              ("EXIT: one sell 19-20 slots (~4 s) after the buy", lambda l: tim(l["first_sl"], (19, 20)))],
        252: [("SIZE+ENTRY: 0.01 SOL buys after outside buying (momentum), only on 10-24 and 10-26", lambda l: l["spend"] <= 0.011),
              ("EXIT: one sell 2-3 slots after the buy", lambda l: l["first_sl"] in (2, 3))],
    }
    J = {}
    for c, cl in claims.items():
        J[str(c)] = dict(name=NAMES[c], claims=[])
        for text, f in cl:
            v = [l for l in C[c] if f(l)]
            J[str(c)]["claims"].append(dict(claim=text, matching_lots=len(v), share_of_code_lots=round(len(v) / max(len(C[c]), 1), 3),
                                            examples=[ex(l) for l in pick(v)]))
    for c, text in ((226, "LIMIT: band order; failed buys (error 6042) when the price ran > ~8.7% above the post-dump price before landing (29% of its buys fail)"),
                    (231, "LIMIT: same band; 54% of its buys fail (6042)"), (234, "LIMIT: 5% above the floor price it saw; 50% of its buys fail (someone bought first)")):
        fv = sorted([f for f in fails if f["code"] == c and f["kind"] == "buy"], key=lambda f: -f["bt"])
        seen = set(); exs = []
        for f in fv:
            if f["mint"] in seen: continue
            seen.add(f["mint"]); exs.append(fex(f))
            if len(exs) >= 6: break
        J[str(c)]["claims"].append(dict(claim=text, matching_txs=len(fv), examples=exs))
    json.dump(J, open(f"{OUT}/examples.json", "w"), indent=1)
    # ---- reconciliation
    P = Out(f"{OUT}/m11.txt")
    R = json.load(open(f"{OUT}/m10.json"))
    real = collections.defaultdict(float)
    for l in lots: real[(l["code"], l["day"])] += l["net"]
    P("# Reconciliation per day (SOL): his real net (MEASURED, code-matched) vs explicit-rule replays (INFERRED, his style: his size, limit, nearest timer, 0.79 mSOL/lot)")
    P("| day | haqq real, all codes | real 247+248 | real minor (all other codes) | minor rule replays (226+231+244+251) | real P&L of minor-bot lots the rules catch | 247/248 rule replays (analyst F) |")
    P("|---|---|---|---|---|---|---|")
    for d in range(6):
        allr = sum(v for (c, dd), v in real.items() if dd == d); big = real[(247, d)] + real[(248, d)]
        rep = sum(R[f"{c}|hisstyle|D{d}"]["rep"] for c in (226, 231, 244, 251)); cau = sum(R[f"{c}|hisstyle|D{d}"]["caught"] for c in (226, 231, 244, 251))
        P(f"| D{d}{' (rules in-sample)' if d <= 2 else ''} | {allr:+.2f} | {big:+.2f} | {allr - big:+.2f} | {rep:+.2f} | {cau:+.2f} | pending |")
    P.save()
    print(json.dumps({c: [(x["claim"][:50], x.get("matching_lots", x.get("matching_txs"))) for x in J[c]["claims"]] for c in J}, indent=0)[:3000])


if __name__ == "__main__":
    main()
