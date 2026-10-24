#!/usr/bin/env python3
# READ-ONLY, offline: CWiNFA's realized PnL after ALL costs over the owner's-RPC window, two independent ways:
#  (1) BALANCE: SOL balance change + value sent out (stablecoins bought with SOL and sent away = withdrawals, valued at the
#      SOL spent) - deposits; (2) PARTS: per-token trading (exact SOL deltas of buy + sell txs) + rent refunds + failed-tx
#      fees + nonce-only fees + other.  Plus a cost breakdown from the pump TradeEvents, a daily table, by sell type,
#      and the wallet's own token outcomes (hold time, sell price multiple).
import os, sys, json, collections, statistics, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
W = "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J"; WSOL = "So11111111111111111111111111111111111111112"
STABLE = {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT"}
D = json.load(open(os.path.join(HERE, "ledger_CWiNFA.json"))); T = [r for r in D["txs"] if not r.get("missing")]
# fill missing blockTimes from neighbours (slot-interpolated)
known = [(r["slot"], r["bt"]) for r in T if r.get("bt")]
for r in T:
    if not r.get("bt"):
        nb = min(known, key=lambda k: abs(k[0] - r["slot"])); r["bt"] = int(nb[1] + (r["slot"] - nb[0]) * 0.4); r["bt_est"] = True
day = lambda r: datetime.datetime.fromtimestamp(r["bt"], datetime.timezone.utc).strftime("%m-%d")
fmt = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%m-%d %H:%M")
def kind(r):
    rt = (r.get("router") or {}).get("tag")
    if rt == 2: return "buy" if not r["err"] else "buy FAILED"
    if rt == 3: return "sell" if not r["err"] else "sell FAILED"
    if any(STABLE.get(m) for m in r["tok"]) or any(n.startswith(("Swap", "Route", "Fill")) for n in r["names"]): return "stablecoin swap / transfer" + (" FAILED" if r["err"] else "")
    if r["nclose"] or (r["names"] and all(n == "CloseAccount" for n in r["names"])): return "close token accounts" + (" FAILED" if r["err"] else "")
    if r.get("nonce") and not r["names"] and not r["xfers"] and not r["tips"]: return "nonce advance only" + (" FAILED" if r["err"] else "")
    if r["xfers"] and not r["names"]: return "SOL transfer (dust in)" if r["sol_chg"] >= 0 and r["sol_chg"] < 0.001 else "SOL transfer"
    return "other" + (" FAILED" if r["err"] else "")
for r in T: r["kind"] = kind(r)
out = []; P = lambda *a: out.append(" ".join(str(z) for z in a))
t0 = T[0]["bt"]; t1 = T[-1]["bt"]
P(f"window {fmt(t0)} -> {fmt(t1)} UTC = {(t1 - t0) / 3600:.1f} h; {len(T)} txs: " + ", ".join(f"{k} {n}" for k, n in collections.Counter(r["kind"] for r in T).most_common()))
# ---- (1) balance method
first = T[0]; last = T[-1]
stab_out_sol = 0.0; stab_usd_out = 0.0; stab_rows = []
for r in T:
    if r["kind"].startswith("stablecoin"):
        stab_out_sol += -r["sol_chg"]
        for m, d in r["tok"].items():
            if STABLE.get(m): stab_rows.append((r["bt"], STABLE[m], d))
# stable holdings: net change over the window (bought with SOL, sent out)
net_stable = collections.Counter()
for _, s, d in stab_rows: net_stable[s] += d
P(f"balance {first['pre_bal']:.4f} -> {last['post_bal']:.4f} SOL (change {last['post_bal'] - first['pre_bal']:+.4f}); SOL spent on SOL->stablecoin swaps (all stablecoins then sent out) {stab_out_sol:.4f} SOL; "
  f"net stablecoin balance change over the window {dict((k, round(v, 2)) for k, v in net_stable.items())} (negative = stables it held before were also sent out)")
usd_sent = -sum(d for _, s, d in stab_rows if d < -1)
usd_bought = sum(d for _, s, d in stab_rows if d > 1 and True)
P(f"stablecoins sent out: {usd_sent:.2f} USD (incl. USDC->USDT conversions counted once below); bought with SOL: see per-tx list in the report")
# ---- (2) parts
cat = collections.Counter(); per_day = collections.defaultdict(collections.Counter)
for r in T:
    k = r["kind"]
    if k in ("buy", "sell"): c_ = "trading"
    elif k.endswith("FAILED"): c_ = "failed-tx fees"
    elif k == "nonce advance only": c_ = "nonce-advance txs"
    elif k == "close token accounts": c_ = "rent refunds"
    elif k.startswith("stablecoin"): c_ = "withdrawals (SOL->stablecoins sent out)"
    elif k.startswith("SOL transfer"): c_ = "dust / spam in"
    else: c_ = "other"
    cat[c_] += r["sol_chg"]; per_day[day(r)][c_] += r["sol_chg"]
profit = sum(v for k, v in cat.items() if not k.startswith("withdrawals"))
P("parts (SOL): " + " | ".join(f"{k} {v:+.4f}" for k, v in sorted(cat.items(), key=lambda kv: kv[1])))
P(f"PROFIT after all costs over the window = trading + rent refunds + failed fees + nonce txs + dust = {profit:+.4f} SOL "
  f"(check: balance change {last['post_bal'] - first['pre_bal']:+.4f} + withdrawals {-cat['withdrawals (SOL->stablecoins sent out)']:.4f} = {last['post_bal'] - first['pre_bal'] - cat['withdrawals (SOL->stablecoins sent out)']:+.4f})")
hrs = (t1 - t0) / 3600
P(f"   = {profit / hrs * 24:+.2f} SOL per 24 h on average; rent still parked in open token accounts at the end: not counted (accounts closed in batches)")
# ---- cost breakdown from events and tx fields
B = [r for r in T if r["kind"] == "buy"]; S = [r for r in T if r["kind"] == "sell"]
ev_b = [e for r in B for e in r["ev"] if e["buy"]]; ev_s = [e for r in S for e in r["ev"] if not e["buy"]]
buy_curve = sum(e["sol"] for e in ev_b) / 1e9; buy_fees = sum(e["fee"] + e["cfee"] for e in ev_b) / 1e9
sell_gross = sum(e["sol"] for e in ev_s) / 1e9; sell_fees = sum(e["fee"] + e["cfee"] for e in ev_s) / 1e9
tips_b = sum(t[1] for r in B for t in r["tips"]); tips_s = sum(t[1] for r in S for t in r["tips"])
untip = collections.Counter()
for r in B + S:
    for s, d, l, top in r["xfers"]:
        if s == W and top and d in ("tKq5esiQyvgRyfFa4JEz4uAUmppKyKB1PiQD9JhyGJY", "D1Mc6j9xQWgR1o1Z7yU5nVVXFQiAYx7FG9AW1aVfwrUM"): untip["buy" if r["kind"] == "buy" else "sell"] += l
fee_b = sum(r["fee"] for r in B); fee_s = sum(r["fee"] for r in S); fee_f = sum(r["fee"] for r in T if r["kind"].endswith("FAILED"))
gross = sell_gross - buy_curve
P(f"cost breakdown over {len(B)} round trips (SOL): curve result before any fee {gross:+.3f} (bought {buy_curve:.2f} on the curve, sold {sell_gross:.2f} gross) | "
  f"pump fees {-(buy_fees + sell_fees):.3f} (buy {buy_fees:.3f}, sell {sell_fees:.3f}) | tips {-(tips_b + tips_s + untip['buy'] + untip['sell']):.3f} (buys {tips_b + untip['buy']:.3f}, sells {tips_s + untip['sell']:.3f}; "
  f"incl. {untip['buy'] + untip['sell']:.3f} to 2 unlabelled tip accounts) | tx fees {-(fee_b + fee_s):.3f} (buys {fee_b:.3f}, sells {fee_s:.3f}) | failed-tx fees {-fee_f:.3f}")
net_parts = gross - buy_fees - sell_fees - tips_b - tips_s - untip["buy"] - untip["sell"] - fee_b - fee_s
P(f"   curve result - pump fees - tips - tx fees = {net_parts:+.3f} (vs measured trading SOL deltas {cat['trading']:+.3f}; difference = token-account rent {cat['trading'] - net_parts:+.3f}, refunded later)")
P("per day (UTC):")
for d_ in sorted(per_day):
    c = per_day[d_]; pr = sum(v for k, v in c.items() if not k.startswith("withdrawals"))
    nb = sum(1 for r in B if day(r) == d_)
    P(f"   {d_}: profit {pr:+.3f} SOL on {nb} buys | trading {c['trading']:+.3f}, rent refunds {c['rent refunds']:+.3f}, failed {c['failed-tx fees']:+.4f}"
      + (f" | withdrawn {-c['withdrawals (SOL->stablecoins sent out)']:.2f} SOL as stablecoins" if c['withdrawals (SOL->stablecoins sent out)'] else ""))
# ---- per token
rent = 0.00203928
tok = collections.defaultdict(lambda: dict(pnl=0.0, b=None, s=[]))
for r in B + S:
    e = r["ev"][0] if r["ev"] else None
    if not e: continue
    x = tok[e["mint"]]; x["pnl"] += r["sol_chg"]
    if r["kind"] == "buy": x["b"] = dict(slot=r["slot"], bt=r["bt"], tok=e["tok"], sol=e["sol"], vsol=e["vsol"], vtok=e["vtok"], v=r["v"])
    else: x["s"].append(dict(slot=r["slot"], bt=r["bt"], tok=e["tok"], sol=e["sol"], flags=r["router"].get("flags"), fee=r["fee"]))
RT = {m: x for m, x in tok.items() if x["b"] and x["s"]}
for x in RT.values(): x["net"] = x["pnl"] + rent
pn = sorted((x["net"] for x in RT.values()), reverse=True)
P(f"tokens round-tripped {len(RT)}: total {sum(pn):+.3f} SOL (rent refund added back), win {sum(p > 0 for p in pn) / len(pn):.1%}, median {statistics.median(pn):+.4f}, mean {statistics.mean(pn):+.4f}; "
  f"best 2 {pn[0]:+.3f} {pn[1]:+.3f} -> without them {sum(pn[2:]):+.3f}; worst {pn[-1]:+.3f}")
for lo, hi, name in ((-9, -0.1, "<= -0.10"), (-0.1, -0.03, "-0.10..-0.03"), (-0.03, 0, "-0.03..0"), (0, 0.03, "0..+0.03"), (0.03, 0.1, "+0.03..+0.10"), (0.1, 9, ">= +0.10")):
    v = [p for p in pn if lo < p <= hi] if lo > -9 else [p for p in pn if p <= hi]
    P(f"   PnL {name:13}: {len(v):4} tokens, {sum(v):+.3f} SOL")
FL = {"010000": "normal (low fee)", "010101": "urgent: insider sold (high fee)", "010500": "type 05", "010601": "type 06 (high fee)", "010701": "type 07 (high fee)", "010901": "type 09"}
g = collections.defaultdict(list)
for x in RT.values(): g[x["s"][0]["flags"]].append(x)
P("by sell type (router flag byte):")
for f_, xs in sorted(g.items(), key=lambda kv: -len(kv[1])):
    hold = [(x["s"][0]["slot"] - x["b"]["slot"]) for x in xs]
    mult = [((x["s"][0]["sol"] / x["s"][0]["tok"]) / (x["b"]["sol"] / x["b"]["tok"])) for x in xs if x["s"][0]["tok"] and x["b"]["tok"]]
    P(f"   {f_} {FL.get(f_, ''):34} {len(xs):4} tokens, {sum(x['net'] for x in xs):+7.3f} SOL, median {statistics.median(x['net'] for x in xs):+.4f}, "
      f"hold median {statistics.median(hold)} slots (p25 {sorted(hold)[len(hold) // 4]}, p75 {sorted(hold)[3 * len(hold) // 4]}), sell/entry price median {statistics.median(mult):.3f}")
hold = [x["s"][0]["slot"] - x["b"]["slot"] for x in RT.values()]
P(f"hold (first sell - buy): median {statistics.median(hold)} slots, p10 {sorted(hold)[len(hold) // 10]}, p90 {sorted(hold)[9 * len(hold) // 10]}; sells per token {dict(collections.Counter(len(x['s']) for x in RT.values()))}")
json.dump(dict(window=[t0, t1], profit=profit, parts=dict(cat), per_day={d_: dict(c) for d_, c in per_day.items()},
               tokens={m: dict(net=x["net"], b=x["b"], s=x["s"]) for m, x in RT.items()}, costs=dict(gross=gross, buy_fees=buy_fees, sell_fees=sell_fees, tips_b=tips_b + untip["buy"],
               tips_s=tips_s + untip["sell"], fee_b=fee_b, fee_s=fee_s, fee_failed=fee_f, n=len(B)), stable_rows=stab_rows),
          open(os.path.join(HERE, "pnl.json"), "w"))
open(os.path.join(HERE, "pnl.txt"), "w").write("\n".join(out) + "\n"); print("\n".join(out))
