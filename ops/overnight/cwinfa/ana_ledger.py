#!/usr/bin/env python3
# READ-ONLY, offline: ground-truth ledger analysis of CWiNFA (questions 1, 2, 5) from ledger_CWiNFA.json.
#  - tx inventory (buys / sells / failed / nonce-only / account closes / transfers / other swaps)
#  - infrastructure: versions, tip services and amounts, priority fee, CU, nonce accounts
#  - PnL after ALL costs over the window: balance change - deposits + withdrawals, and the same from the parts
#    (per-token trading incl. tips / fees / rent, failed-tx fees, nonce-only fees, rent refunds, other swaps)
#  - daily breakdown, by venue, per-token distribution, sells by router flag (exit triggers)
import os, sys, json, collections, statistics, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
W = "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J"; WSOL = "So11111111111111111111111111111111111111112"
D = json.load(open(os.path.join(HERE, "ledger_CWiNFA.json"))); T = [r for r in D["txs"] if not r.get("missing")]
SOLPRICE = None
try: SOLPRICE = float(sys.argv[1])
except Exception: pass
day = lambda r: datetime.datetime.fromtimestamp(r["bt"], datetime.timezone.utc).strftime("%m-%d") if r.get("bt") else "?"
out = []; P = lambda *a: out.append(" ".join(str(z) for z in a))
def kind(r):
    rt = (r.get("router") or {}).get("tag")
    if rt == 2: return "buy" if not r["err"] else "buy FAILED"
    if rt == 3: return "sell" if not r["err"] else "sell FAILED"
    if r["names"] and all(n == "CloseAccount" for n in r["names"]) or (r["nclose"] and not r["ev"] and not r["tok"]): return "close accounts" + (" FAILED" if r["err"] else "")
    if r.get("nonce") and not r["names"] and not r["xfers"] and not r["tips"] and len(r["progs"]) == 1: return "nonce advance only" + (" FAILED" if r["err"] else "")
    if r["tok"] and any(m != WSOL for m in r["tok"]): return "other token tx" + (" FAILED" if r["err"] else "")
    if r["xfers"] and not r["names"]: return "SOL transfer" + (" FAILED" if r["err"] else "")
    return "other" + (" FAILED" if r["err"] else "")
for r in T: r["kind"] = kind(r)
t0 = min(r["bt"] for r in T if r.get("bt")); t1 = max(r["bt"] for r in T if r.get("bt"))
fmt = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%m-%d %H:%M")
P(f"window: {fmt(t0)} -> {fmt(t1)} UTC ({(t1 - t0) / 3600:.1f} h), slots {T[0]['slot']}..{T[-1]['slot']}, {len(T)} txs ({len(D['txs']) - len(T)} missing)")
P("inventory:", dict(collections.Counter(r["kind"] for r in T).most_common()))
# ---------------- infrastructure
B = [r for r in T if r["kind"] == "buy"]; S = [r for r in T if r["kind"] == "sell"]; BF = [r for r in T if r["kind"] == "buy FAILED"]
P(f"buys {len(B)}, sells {len(S)}, failed buys {len(BF)}")
for name, G in (("buys", B), ("sells", S), ("failed buys", BF)):
    P(f"[{name}] version: {dict(collections.Counter(str(r['v']) for r in G))}; nonce used: {sum(1 for r in G if r['nonce'])}/{len(G)}; distinct nonce accounts: {len({r['nonce'] for r in G if r['nonce']})}")
    P(f"   tips: {dict(collections.Counter((t[0], t[1]) for r in G for t in r['tips']).most_common(8))}; no tip: {sum(1 for r in G if not r['tips'])}")
    P(f"   tip service by version: {dict(collections.Counter((str(r['v']), r['tips'][0][0] if r['tips'] else 'none') for r in G).most_common(10))}")
    P(f"   fee (base+priority) SOL: {dict(collections.Counter(round(r['fee'], 7) for r in G).most_common(5))}; CU limit/price (v0): {dict(collections.Counter((r['cul'], r['cup']) for r in G).most_common(4))}")
    cu = [r["cu"] for r in G if r["cu"]]
    if cu: P(f"   CU consumed: median {statistics.median(cu)} (min {min(cu)}, max {max(cu)}); signers {dict(collections.Counter(r['nsig'] for r in G))}")
P("nonce accounts (buys+sells):", collections.Counter(r["nonce"] for r in B + S).most_common(12))
P("buy amounts (router):", collections.Counter(r["router"]["amount"] for r in B + BF).most_common(4))
P("sell min-out (router):", collections.Counter(r["router"]["min_out"] for r in S).most_common(3), "| sell flags:", dict(collections.Counter(r["router"].get("flags") for r in S)))
P("buy pump ix:", collections.Counter((r["pump_ix"] or {}).get("name") for r in B).most_common(3), "| sell pump ix:", collections.Counter((r["pump_ix"] or {}).get("name") for r in S).most_common(3))
P("failed tx errors:", collections.Counter((r["kind"], r["errname"]) for r in T if r["err"]).most_common(12))
# other transfers in buy/sell txs (bot fees?)
fx = collections.Counter()
for r in B + S:
    for s, d, l, top in r["xfers"]:
        if s == W and top: fx[(d, round(l, 6))] += 1
P("top-level SOL transfers out of the wallet inside buy/sell txs (besides tips):", fx.most_common(6))
# ---------------- PnL
first = next(r for r in T if r.get("pre_bal") is not None); last = [r for r in T if r.get("post_bal") is not None][-1]
ext = collections.defaultdict(float); cat = collections.Counter(); per_day = collections.defaultdict(collections.Counter)
for r in T:
    k = r["kind"]
    if k in ("SOL transfer",):
        v = r["sol_chg"]
        cps = [d if s == W else s for s, d, l, top in r["xfers"] if l >= 0.001]
        c_ = "deposit" if v > 0 else "withdrawal"
        ext[(c_, cps[0] if cps else "?")] += v; cat[c_] += v; per_day[day(r)][c_] += v; continue
    if k in ("buy", "sell"): c_ = "trading (pump buys+sells incl. fees, tips, rent)"
    elif k.endswith("FAILED"): c_ = "failed-tx fees"
    elif k == "nonce advance only": c_ = "nonce-advance txs"
    elif k == "close accounts": c_ = "rent refunds (account closes)"
    elif k == "other token tx": c_ = "other token txs (swaps / token transfers)"
    else: c_ = "other"
    cat[c_] += r["sol_chg"]; per_day[day(r)][c_] += r["sol_chg"]
P(f"balance: start {first['pre_bal']:.4f} SOL (before {first['sig'][:10]}..., {fmt(first['bt'])}) -> end {last['post_bal']:.4f} SOL ({fmt(last['bt'])})")
dep = cat["deposit"]; wd = cat["withdrawal"]
prof = last["post_bal"] - first["pre_bal"] - dep - wd
P(f"deposits {dep:+.4f} | withdrawals {wd:+.4f} | PROFIT over the window (balance change - net external) {prof:+.4f} SOL")
parts = {k: v for k, v in cat.items() if k not in ("deposit", "withdrawal")}
P("parts:", {k: round(v, 4) for k, v in sorted(parts.items(), key=lambda kv: kv[1])}, f"sum {sum(parts.values()):+.4f}")
P("external flows by counterparty:", [(k[0], k[1], round(v, 4)) for k, v in sorted(ext.items(), key=lambda kv: kv[1])])
P("per day (profit, excl. external):")
for d_ in sorted(per_day):
    c = per_day[d_]; pr = sum(v for k, v in c.items() if k not in ("deposit", "withdrawal"))
    P(f"   {d_}: {pr:+.4f} SOL | " + ", ".join(f"{k.split(' (')[0]} {v:+.3f}" for k, v in sorted(c.items()) if k not in ("deposit", "withdrawal")) +
      (f" | deposits {c['deposit']:+.2f} withdrawals {c['withdrawal']:+.2f}" if c["deposit"] or c["withdrawal"] else ""))
# per token (pump): buy + sells + failed attempts on that mint (+ the 0.00203928 rent comes back in a later close tx)
tok = collections.defaultdict(lambda: dict(pnl=0.0, buys=0, sells=0, fails=0, t_buy=None, t_sell=None, sol_in=0.0, tips=0.0, fees=0.0, first_sell_s=None, nsell=0, slots=[], v_sell_flags=[]))
for r in T:
    if r["kind"] not in ("buy", "sell", "buy FAILED", "sell FAILED"): continue
    m = next(iter(r["tok"]), None) or (r["ev"][0]["mint"] if r["ev"] else None)
    if r["kind"] == "buy FAILED": m = "FAILED:" + (r["router"].get("seed") or "?")
    if m is None: continue
    x = tok[m]; x["pnl"] += r["sol_chg"]; x["tips"] += sum(t[1] for t in r["tips"]); x["fees"] += r["fee"]
    if r["kind"] == "buy": x["buys"] += 1; x["t_buy"] = x["t_buy"] or r["bt"]; x["sol_in"] += -r["sol_chg"]; x["slot_buy"] = r["slot"]
    elif r["kind"] == "sell":
        x["sells"] += 1; x["t_sell"] = r["bt"]; x["v_sell_flags"].append(r["router"].get("flags"))
        if x.get("slot_buy") and x["first_sell_s"] is None: x["first_sell_s"] = r["slot"] - x["slot_buy"]
    else: x["fails"] += 1
RT = {m: x for m, x in tok.items() if x["buys"] and x["sells"]}
rent = 0.00203928
pn = [x["pnl"] + rent * x["buys"] for x in RT.values()]   # rent is refunded later by the close txs
P(f"round-tripped pump tokens: {len(RT)}; trading PnL incl. rent refund {sum(pn):+.4f} SOL; win {sum(p > 0 for p in pn) / len(pn):.1%}; median {statistics.median(pn):+.4f}; mean {statistics.mean(pn):+.4f}")
w = sorted(pn, reverse=True); P(f"   best 5 {[round(v, 3) for v in w[:5]]}, worst 5 {[round(v, 3) for v in w[-5:]]}; without best 2: {sum(w[2:]):+.3f}")
P(f"   open (bought, not sold): {[m for m, x in tok.items() if x['buys'] and not x['sells']][:5]}")
P(f"   tips total {sum(x['tips'] for x in tok.values()):.4f} SOL, tx fees total {sum(x['fees'] for x in tok.values()):.4f} SOL (trading + failed)")
by_flag = collections.defaultdict(list)
for m, x in RT.items(): by_flag[x["v_sell_flags"][0] if x["v_sell_flags"] else None].append(x["pnl"] + rent)
P("per-token PnL by sell flag:", {k: (len(v), round(sum(v), 3), round(statistics.median(v), 4)) for k, v in by_flag.items()})
json.dump(dict(window=[t0, t1], profit=prof, parts=parts, deposits=dep, withdrawals=wd, start=first["pre_bal"], end=last["post_bal"], ext=[[k[0], k[1], v] for k, v in ext.items()],
               per_day={d_: dict(c) for d_, c in per_day.items()}, tokens={m: {k: v for k, v in x.items() if k != "slots"} for m, x in tok.items()}),
          open(os.path.join(HERE, "ledger_summary.json"), "w"))
open(os.path.join(HERE, "ledger_summary.txt"), "w").write("\n".join(out) + "\n"); print("\n".join(out))
