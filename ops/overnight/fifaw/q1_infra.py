#!/usr/bin/env python3
# READ-ONLY, offline: infrastructure fingerprint of FiFawH from its own txs (ledger_FiFawH.json + truth_FiFawH.json).
import json, collections, statistics as stt
W = "FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W"
L = {x["sig"]: x for x in json.load(open("ledger_FiFawH.json"))}
T = json.load(open("truth_FiFawH.json"))
X = [dict(L[t["sig"]], cat=t["cat"]) for t in T["txs"]]
def q(v, ps=(0.1, 0.5, 0.9)):
    v = sorted(v)
    return [round(v[int(p * (len(v) - 1))], 6) for p in ps] if v else None
out = {}
P = lambda *a: print(*a)
P("txs signed by FiFawH in window:", len(X), collections.Counter(x["cat"] for x in X))
P("versions:", collections.Counter(str(x["v"]) for x in X), "| signers per tx:", collections.Counter(x["nsig"] for x in X))
for cat in ("buy", "failed_buy", "noop_guard", "sell", "failed_sell"):
    S = [x for x in X if x["cat"] == cat]
    if not S: continue
    non = sum(1 for x in S if x["nonce"]); prio = [(x["fee"] - 5000 * x["nsig"]) / 1e9 for x in S]
    tipn = collections.Counter(t[0] for x in S for t in x["tips"]); tipamt = collections.defaultdict(list)
    for x in S:
        for t in x["tips"]: tipamt[t[0]].append(t[1] / 1e9)
    astz = [l / 1e9 for x in S for d, l in x["xout"] if d == "AsTzjKRAZ91h6VpiR7Za5EWP8MPYRhfnRxAG4CUXL3oT"]
    notip = sum(1 for x in S if not x["tips"] and not any(d == "AsTzjKRAZ91h6VpiR7Za5EWP8MPYRhfnRxAG4CUXL3oT" for d, _ in x["xout"]))
    seed = sum(1 for x in S if "createAccountWithSeed" in json.dumps(x.get("top"))) # placeholder (top holds program ids only)
    P(f"\n[{cat}] n={len(S)} durable-nonce {non} ({non/len(S):.0%}) | CU limit p10/50/90 {q([x['cu_limit'] or 0 for x in S])} | CU used {q([x['cu'] or 0 for x in S])}")
    P(f"   priority fee SOL p10/50/90 {q(prio)} total {sum(prio):.3f} | CU price uL p10/50/90 {q([x['cu_price'] or 0 for x in S])}")
    P(f"   tips: {dict(tipn)} | no tip at all {notip} | AsTz transfers {len(astz)} median {stt.median(astz) if astz else None}")
    for k, v in tipamt.items(): P(f"      {k:10} n={len(v)} SOL p10/50/90 {q(v)} sum {sum(v):.3f}")
    P(f"   routers: {collections.Counter(tuple(r[:6] for r in x['routers']) for x in S).most_common(6)} | venues {collections.Counter(tuple(x['venues']) for x in S).most_common(5)}")
    out[cat] = dict(n=len(S), nonce=non, prio_q=q(prio), prio_sum=sum(prio), tips={k: dict(n=len(v), q=q(v), sum=sum(v)) for k, v in tipamt.items()}, notip=notip, astz=len(astz))
# buy size vs costs (landed buys with a pump TradeEvent of W)
rows = []
for x in X:
    if x["cat"] != "buy": continue
    e = [e for e in x["ev"] if e["buy"]]
    if not e: continue
    if not (20e9 < e[0]["vsol"] < 200e9):                 # other-quote curve (USDC etc.): size from the quote spent at 106 USD/SOL
        usd = -sum(d for m, d in x["tok"].items() if m in ("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"))
        sol = usd / 106.0 if usd > 0 else None
        if not sol: continue
    else: sol = sum(e_["sol"] for e_ in e) / 1e9
    tip = sum(t[1] for t in x["tips"]) / 1e9 + sum(l for d, l in x["xout"] if d == "AsTzjKRAZ91h6VpiR7Za5EWP8MPYRhfnRxAG4CUXL3oT") / 1e9
    prio = (x["fee"] - 5000 * x["nsig"]) / 1e9
    rows.append(dict(oq=not (20e9 < e[0]["vsol"] < 200e9), sol=sol, tip=tip, prio=prio, svc=[t[0] for t in x["tips"]] or (["AsTz"] if tip else ["none(prio only)"]), q=x["routers"][:1]))
P(f"\nlanded buys with a W trade event: {len(rows)} (other-quote, sized via USD: {sum(r['oq'] for r in rows)})")
sz = collections.Counter(round(r["sol"] * 4) / 4 for r in rows)
P("size tiers (curve SOL in, rounded to 0.25):", sorted(sz.items()))
P("total send cost (tip+prio)/size p10/50/90:", q([(r["tip"] + r["prio"]) / r["sol"] for r in rows if r["sol"] > 0]))
for svc in sorted({r["svc"][0] for r in rows}):
    v = [r for r in rows if r["svc"][0] == svc]
    P(f"   landed via {svc:16} n={len(v):3}  cost/size median {stt.median([(r['tip'] + r['prio']) / r['sol'] for r in v]):.4f}")
by = collections.defaultdict(list)
for r in rows: by[round(r["sol"] * 2) / 2].append((r["tip"] + r["prio"]) / r["sol"])
P("cost/size by size:", {k: (len(v), round(stt.median(v), 4)) for k, v in sorted(by.items())})
# failed buy reasons
fr = collections.Counter()
for x in X:
    if x["cat"] in ("failed_buy", "failed_sell") and x["errinfo"]:
        e = x["errinfo"]; code = e.get("code") or (str(e.get("raw"))[:60])
        fr[(x["cat"], code)] += 1
P("\nfailure reasons:", fr.most_common(20))
P("failed-tx fees SOL:", round(sum(x["fee"] for x in X if x["err"]) / 1e9, 3), "| failed buys with a tip ix:", sum(1 for x in X if x["cat"] == "failed_buy" and x["tips"]))
# CB extra (marker) accounts
P("CB-instruction extra accounts on buys:", sum(1 for x in X if x["cat"] in ("buy", "failed_buy", "noop_guard") and x["cb_extra"]), "of", sum(1 for x in X if x["cat"] in ("buy", "failed_buy", "noop_guard")),
  "| distinct", len({a for x in X for a in x["cb_extra"]}))
# blockhash: nonce vs recent
P("sells using durable nonce:", sum(1 for x in X if x["cat"] == "sell" and x["nonce"]), "of", sum(1 for x in X if x["cat"] == "sell"))
P("LoadedAccountsDataSize limit set:", collections.Counter((x["cat"], x["lds"]) for x in X if x["lds"]).most_common(5))
json.dump(out, open("q1_infra.json", "w"), indent=1)
