#!/usr/bin/env python3
# READ-ONLY, offline. Q2 ground-truth PnL (owner-RPC window) by PKT day + cost breakdown, and Q5 exit pattern per position.
# Inputs: truth_FiFawH.json (classified txs, values at constant prices: quote assets at today's price, SOL=106 USD),
#         ledger_FiFawH.json, txc_FiFawH/ (raw txs, for the sell-instruction percent argument).
import json, os, collections, statistics as stt, datetime, base64
W = "FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W"; PKT = datetime.timezone(datetime.timedelta(hours=5))
T = json.load(open("truth_FiFawH.json")); L = {x["sig"]: x for x in json.load(open("ledger_FiFawH.json"))}
X = [t for t in T["txs"] if t["bt"]]
pk = lambda bt: datetime.datetime.fromtimestamp(bt, PKT)
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big"); return b"\0" * (len(s) - len(s.lstrip("1"))) + b
out = {}
for x in X:
    l = L[x["sig"]]
    x["cbonly"] = (not x["err"]) and set(l["top"]) == {"ComputeBudget111111111111111111111111111111"}
    x["kind"] = "cb_only_fee" if x["cbonly"] else x["cat"]
lo, hi = min(x["bt"] for x in X), max(x["bt"] for x in X)
print(f"window {pk(lo):%m-%d %H:%M} -> {pk(hi):%m-%d %H:%M} PKT ({(hi - lo) / 3600:.1f} h), {len(X)} txs signed by FiFawH")
# ---- cost breakdown (landed txs pay fee + tips; failed pay fee only)
fee = lambda xs: sum(x["fee"] for x in xs) / 1e9
tipsum = lambda xs: sum(x["tip"] + x["astz"] for x in xs if not x["err"])
K = collections.defaultdict(list)
for x in X: K[x["kind"]].append(x)
costs = dict(
    buy_fees=fee(K["buy"]), buy_tips=tipsum(K["buy"]), sell_fees=fee(K["sell"]), sell_tips=tipsum(K["sell"]),
    failed_buy_fees=fee(K["failed_buy"]), failed_sell_fees=fee(K["failed_sell"]), noop_guard_total=-sum(x["val"] for x in K["noop_guard"]),
    cb_only_fee_burn=fee(K["cb_only_fee"]), other_admin=-sum(x["val"] for x in K["admin"]))
trade = sum(x["val"] for x in X if x["kind"] in ("buy", "sell", "token_out"))
print("trading result incl. landed buy/sell fees+tips (buy+sell txs):", round(trade, 3))
for k, v in costs.items(): print(f"   {k:20} {v:8.3f} SOL")
net = sum(x["val"] for x in X)
print(f"NET window PnL (all txs, constant prices; no tokens left) {net:+.3f} SOL  = {net / ((hi - lo) / 86400):+.2f} SOL/day")
gross = trade + costs["buy_fees"] + costs["buy_tips"] + costs["sell_fees"] + costs["sell_tips"]
print(f"gross trading (before any fee/tip) {gross:+.3f}; all send costs {sum(costs[k] for k in ('buy_fees','buy_tips','sell_fees','sell_tips','failed_buy_fees','failed_sell_fees','noop_guard_total','cb_only_fee_burn')):.3f}")
out["costs"] = costs; out["trade"] = trade; out["net"] = net; out["gross"] = gross; out["window_pkt"] = [f"{pk(lo):%Y-%m-%d %H:%M}", f"{pk(hi):%Y-%m-%d %H:%M}"]
# ---- PKT days
D = collections.defaultdict(lambda: collections.defaultdict(float)); N = collections.defaultdict(collections.Counter)
for x in X:
    d = f"{pk(x['bt']):%m-%d}"; D[d][x["kind"]] += x["val"]; N[d][x["kind"]] += 1
print("\nPKT day | landed buys | trading (buy+sell) | failed-tx fees | noop guard | CB-only burn | NET | hours covered")
out["days"] = {}
for d in sorted(D):
    hrs = [x["bt"] for x in X if f"{pk(x['bt']):%m-%d}" == d]; h = (max(hrs) - min(hrs)) / 3600
    tr = D[d]["buy"] + D[d]["sell"] + D[d]["token_out"]; nt = sum(D[d].values())
    print(f"{d} | {N[d]['buy']:4} | {tr:+8.3f} | {D[d]['failed_buy'] + D[d]['failed_sell']:+7.3f} | {D[d]['noop_guard']:+7.3f} | {D[d]['cb_only_fee']:+7.3f} | {nt:+8.3f} | {h:4.1f}")
    out["days"][d] = dict(buys=N[d]["buy"], trading=tr, failed=D[d]["failed_buy"] + D[d]["failed_sell"], noop=D[d]["noop_guard"], cbonly=D[d]["cb_only_fee"], net=nt, hours=h)
# ---- per position (mint) exits
POS = collections.defaultdict(lambda: dict(buys=[], sells=[]))
for x in sorted(X, key=lambda x: (x["slot"], x["sig"])):
    if x["kind"] not in ("buy", "sell"): continue
    for m, d in x["pos"].items():
        ev = [e for e in x["ev"] if e["mint"] == m]
        px = (ev[0]["sol"] / ev[0]["tok"]) if ev and ev[0]["tok"] else None
        POS[m]["buys" if d > 0 else "sells"].append(dict(sig=x["sig"], slot=x["slot"], bt=x["bt"], d=d, px=px, val=x["val"] / len(x["pos"]), routers=x["routers"]))
def sell_pct(sig):
    f = os.path.join("txc_FiFawH", sig + ".json")
    if not os.path.exists(f): return None
    t = json.load(open(f))
    for ix in t["transaction"]["message"]["instructions"]:
        if ix.get("programId") in ("2kAA3Bm3npaBzrevWXJfojagG1BEAac4KwayWphYMYQG", "6iemSi2wHcEJoAwEdG69VznRPGHWJr6Y2VRSyj6m9h45", "BCzSQSmV988WPnCM6MXToLvBaL8dmj8uJWG1MaceenvX"):
            d = b58d(ix["data"]); return dict(b0=d[0], pct=int.from_bytes(d[1:9], "little"), minout=int.from_bytes(d[9:17], "little"), n=len(d))
    return None
rows = []
for m, p in POS.items():
    if not p["buys"]: continue
    b0 = p["buys"][0]; tot = sum(b["d"] for b in p["buys"]); bpx = sum(b["px"] or 0 for b in p["buys"][:1])
    ss = p["sells"]
    r = dict(mint=m, nbuys=len(p["buys"]), nsells=len(ss), pnl=sum(b["val"] for b in p["buys"]) + sum(s["val"] for s in ss), spent=-sum(b["val"] for b in p["buys"]),
             buy_slot=b0["slot"], buy_bt=b0["bt"], quote="SOL" if not (set(b0["routers"]) & {"9uGqm7Xh7Vq2EzqTNHVG5Ca4echELK1UjDq9W9Qg5kzF", "5gP7LHpRndFJSjANFB2ZBJtPJ3KhcPf2xgSNKVD7tAfK"}) else "other")
    r["sells"] = [dict(dslot=s["slot"] - b0["slot"], ds=s["bt"] - b0["bt"], frac=-s["d"] / tot if tot else None, mult=(s["px"] / bpx) if (s["px"] and bpx) else None, sig=s["sig"]) for s in ss]
    rows.append(r)
pcts = collections.Counter()
for r in rows:
    for s in r["sells"]:
        sp = sell_pct(s["sig"]); s["arg"] = sp
        if sp: pcts[(sp["b0"], sp["pct"], sp["minout"] == 0)] += 1
print("\nsell instruction args (variant byte, percent arg, min-out==0):", pcts.most_common(12))
print(f"positions {len(rows)} | sells per position {collections.Counter(min(r['nsells'], 6) for r in rows)} | buys per position {collections.Counter(r['nbuys'] for r in rows)}")
fs = [r["sells"][0] for r in rows if r["sells"]]
print("first sell delay slots p10/25/50/75/90:", [sorted(s["dslot"] for s in fs)[int(q * (len(fs) - 1))] for q in (.1, .25, .5, .75, .9)],
      "| seconds:", [sorted(s["ds"] for s in fs)[int(q * (len(fs) - 1))] for q in (.1, .25, .5, .75, .9)])
ls = [r["sells"][-1] for r in rows if r["sells"]]
print("last sell delay seconds p10/25/50/75/90:", [sorted(s["ds"] for s in ls)[int(q * (len(ls) - 1))] for q in (.1, .25, .5, .75, .9)])
f1 = [s["frac"] for s in fs if s["frac"] is not None]
print("first sell fraction of position p10/50/90:", [round(sorted(f1)[int(q * (len(f1) - 1))], 3) for q in (.1, .5, .9)])
m1 = [s["mult"] for s in fs if s["mult"]]
print("first-sell price / buy price (curve prices, no fees) p10/25/50/75/90:", [round(sorted(m1)[int(q * (len(m1) - 1))], 3) for q in (.1, .25, .5, .75, .9)])
for k in (1, 2, 3):
    g = [r for r in rows if r["nsells"] == k]
    if g: print(f"  positions with {k} sell(s): {len(g)}, pnl {sum(r['pnl'] for r in g):+.2f}, win {sum(r['pnl'] > 0 for r in g) / len(g):.0%}, median hold {stt.median(r['sells'][-1]['ds'] for r in g)} s")
g = [r for r in rows if r["nsells"] > 3]
if g: print(f"  positions with 4+ sells: {len(g)}, pnl {sum(r['pnl'] for r in g):+.2f}")
# multi-sell ladders: fraction and time of each step
lad = [r for r in rows if r["nsells"] >= 2]
for r in sorted(lad, key=lambda r: -r["spent"])[:8]:
    print("   ladder", r["mint"][:6], f"spent {r['spent']:.2f}", [(s["dslot"], round(s["ds"]), round(s["frac"] or 0, 2), round(s["mult"] or 0, 2), (s["arg"] or {}).get("pct")) for s in r["sells"]])
# hold time vs pnl
for lo_, hi_ in ((0, 2), (2, 5), (5, 15), (15, 60), (60, 10 ** 9)):
    g = [r for r in rows if r["sells"] and lo_ <= r["sells"][-1]["ds"] < hi_]
    if g: print(f"  last sell {lo_}-{hi_}s: {len(g)} pos, pnl {sum(r['pnl'] for r in g):+.2f}, win {sum(r['pnl'] > 0 for r in g) / len(g):.0%}")
for qq in ("SOL", "other"):
    g = [r for r in rows if r["quote"] == qq]
    print(f"  quote {qq}: {len(g)} positions, pnl {sum(r['pnl'] for r in g):+.2f}, win {sum(r['pnl'] > 0 for r in g) / len(g):.0%}, median {stt.median(r['pnl'] for r in g):+.4f}")
# size tiers vs pnl
for a, b in ((0, 1.2), (1.2, 1.8), (1.8, 2.6), (2.6, 4.5), (4.5, 100)):
    g = [r for r in rows if a <= r["spent"] < b]
    if g: print(f"  spent {a}-{b} SOL: {len(g)} pos, pnl {sum(r['pnl'] for r in g):+.2f}, mean ret {stt.mean(r['pnl'] / r['spent'] for r in g if r['spent'] > 0):+.3f}, win {sum(r['pnl'] > 0 for r in g) / len(g):.0%}")
out["positions"] = rows
json.dump(out, open("q25_pnl_exits.json", "w"))
