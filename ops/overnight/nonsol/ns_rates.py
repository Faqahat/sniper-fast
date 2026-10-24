#!/usr/bin/env python3
# MEASURED quote -> SOL rates (and the cost of the SOL<->quote swap legs) from txs that buy or sell a non-SOL-quoted curve
# and convert SOL<->quote inside the same tx (Jupiter / AMM routes): the payer's SOL delta (+fee +tips) against the quote
# that went into (buy: q + fees) or came out of (sell: q - fees) the curve. Per quote and hour: median buy-side rate,
# median sell-side rate; mid = geometric mean; swap cost per leg ~ sqrt(buy/sell) - 1 (includes pool fees, price impact,
# router fees; rent noise kept small by using trades >= 0.3 SOL). -> data/rates.json
import sys, json, collections, statistics, math
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/nonsol")
import ns
L, CR, TR, W = ns.load()
P = json.load(open("/home/moiz/sniper/ops/overnight/q9z/prices.json")); SOLUSD = P["sol_usd"]
REF = {}
for m, v in P["prices"].items():
    if v.get("usd") and v.get("dec") is not None: REF[m] = v["usd"] / SOLUSD / 10 ** v["dec"] * 1e9      # lamports per raw quote unit (end of R2)
SWAPP = {"JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4", "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc", "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",
         "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
         "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C", "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG", "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB"}
by = collections.defaultdict(lambda: ([], []))          # (quote, hour) -> (buy rates, sell rates)
cnt = collections.Counter()
for m, tr in TR.items():
    cr = CR.get(m)
    if not cr or cr["mayhem"]: continue
    nsig = collections.Counter(t["sig"] for t in tr)
    for t in tr:
        w = W.get(t["sig"])
        if not w or nsig[t["sig"]] != 1 or w["payer"] != t["user"]: continue
        sw = bool(SWAPP & set(w["progs"] or [])) or any(("Swap" in x or "Route" in x) for x in (w["ixn"] or []) if x not in ("MultiHopSwap", "MultiHopCurveSwap"))
        if not sw: cnt["noswap"] += 1; continue
        ref = REF.get(t["qm"])
        if t["buy"]:
            qin = t["sol"] + t["feeq"] + t["cfeeq"]; lam = -w["sdp"] - (w["fee"] or 0) - (w["tips"] or 0)
            if qin <= 0 or lam <= 0: continue
            r = lam / qin; side = 0
        else:
            qout = t["sol"] - t["feeq"] - t["cfeeq"]; lam = w["sdp"] + (w["fee"] or 0) + (w["tips"] or 0)
            if qout <= 0 or lam <= 0: continue
            r = lam / qout; side = 1
        if lam < 0.3e9: continue
        if ref and not (0.33 < r / ref < 3): cnt["off_ref"] += 1; continue
        h = int((t["bt"] or 0) // 3600)
        by[(t["qm"], h)][side].append(r); cnt["ok"] += 1
print(cnt)
out = {}
for (q, h), (b, s) in by.items():
    out.setdefault(q, {})[h] = dict(nb=len(b), ns=len(s), b=statistics.median(b) if b else None, s=statistics.median(s) if s else None)
# per quote overall + per-leg cost where both sides exist in the same hour
summ = {}
for q, hs in out.items():
    legs = [math.sqrt(v["b"] / v["s"]) - 1 for v in hs.values() if v["b"] and v["s"] and v["nb"] >= 3 and v["ns"] >= 3]
    mids = {h: (math.sqrt(v["b"] * v["s"]) if (v["b"] and v["s"]) else (v["b"] or v["s"])) for h, v in hs.items()}
    summ[q] = dict(n=sum(v["nb"] + v["ns"] for v in hs.values()), leg_med=statistics.median(legs) if legs else None, nh_legs=len(legs),
                   ref=REF.get(q), mid_med=statistics.median(mids.values()))
json.dump(dict(hourly=out, summ=summ, ref=REF, solusd=SOLUSD), open("/home/moiz/sniper/ops/overnight/nonsol/data/rates.json", "w"))
for q, v in sorted(summ.items(), key=lambda x: -x[1]["n"])[:15]:
    rr = (v["mid_med"] / v["ref"]) if v["ref"] else None
    print(f"{ns.qname(q):8s} n={v['n']:6d} leg cost median {v['leg_med'] if v['leg_med'] is None else round(100*v['leg_med'],3)}% over {v['nh_legs']} hours | mid/ref(end R2 price) {rr if rr is None else round(rr,3)}")
