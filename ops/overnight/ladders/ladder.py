#!/usr/bin/env python3
# DGmspi's recent ladders, decoded from balance changes (works for SOL- and PUMP/USDC-quoted tokens): per sell, time
# since the buy, % of the position sold, WSOL+SOL received, effective price vs the buy price.
import json, os, collections, datetime, sys
W = "DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3"; WSOL = "So11111111111111111111111111111111111111112"
R = json.load(open("dg_trades.json"))
def deltas(t):
    pre = {(b["mint"], b.get("owner")): float(b["uiTokenAmount"]["uiAmount"] or 0) for b in t["meta"].get("preTokenBalances") or []}
    post = {(b["mint"], b.get("owner")): float(b["uiTokenAmount"]["uiAmount"] or 0) for b in t["meta"].get("postTokenBalances") or []}
    out = collections.defaultdict(float)
    for k in set(pre) | set(post):
        if k[1] == W: out[k[0]] += post.get(k, 0) - pre.get(k, 0)
    keys = [a["pubkey"] for a in t["transaction"]["message"]["accountKeys"]]
    i = keys.index(W); out["SOL"] = (t["meta"]["postBalances"][i] - t["meta"]["preBalances"][i]) / 1e9
    return out
by = collections.defaultdict(list)
for r in R: by[r["mint"]].append(r)
f = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%H:%M:%S")
out = {}
for m, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
    v.sort(key=lambda r: (r["slot"], r["bt"] or 0)); seen = set(); seq = []
    for x in v:
        if x["sig"] in seen: continue
        seen.add(x["sig"]); d = deltas(json.load(open(os.path.join("txc", x["sig"] + ".json"))))
        seq.append(dict(sig=x["sig"], slot=x["slot"], bt=x["bt"], buy=x["buy"], tok=d.get(m, 0), sol=d.get(WSOL, 0) + d["SOL"], quote="SOL" if x["vsol"] else "non-SOL"))
    b = next(s for s in seq if s["buy"]); pos = b["tok"]; cost = -b["sol"]; p_in = cost / pos
    sells = [s for s in seq if not s["buy"]]; got = sum(s["sol"] for s in sells)
    out[m] = dict(buy=b, sells=sells, cost=cost, got=got)
    if len(sells) < 3: continue
    print(f"\n{m[:10]} ({b['quote']}-quoted): buy {cost:.3f} SOL at {f(b['bt'])}; {len(sells)} sells over {sells[-1]['bt'] - b['bt']} s; got {got:.3f} -> PnL {got - cost:+.3f} SOL ({(got - cost) / cost:+.1%})")
    left = pos
    for k, s in enumerate(sells):
        pr = (s["sol"] / -s["tok"]) / p_in if s["tok"] else 0
        if k < 14 or k >= len(sells) - 6:
            print(f"   #{k + 1:2} +{s['slot'] - b['slot']:4} slots (+{s['bt'] - b['bt']:3}s) sold {-s['tok'] / pos:6.2%} of pos ({-s['tok'] / left:6.2%} of what was left) at x{pr:4.2f} of entry -> {s['sol']:.4f} SOL")
        elif k == 14: print("   ...")
        left += s["tok"]
json.dump(out, open("ladders.json", "w"))
