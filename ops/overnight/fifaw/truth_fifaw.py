#!/usr/bin/env python3
# READ-ONLY, offline ground truth for FiFawH over the owner-RPC window (every tx it signed, failed ones too).
# Value of a tx = SOL change + WSOL + every QUOTE asset change (USDC, PUMP, WBTC, xStocks, ...) at TODAY's price, SOL = 106 USD.
# Launch tokens (positions) are separate; ones still held are valued at today's price (Jupiter) or the curve sell-all value.
# Output: truth_FiFawH.json (per tx + per token + totals) and a printed summary.
import json, collections, datetime, statistics
SOLUSD = 106.0; W = "FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W"; WSOL = "So11111111111111111111111111111111111111112"
P = json.load(open("prices_now.json")); H = json.load(open("holdings_now.json")); L = json.load(open("ledger_FiFawH.json"))
QUOTE = {WSOL, "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB",
         "pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn", "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh", "Xsc9qvGR1efVDFGLrVsmkzv3qi45LTBjeUKSPmx9qEh", "A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS",
         "SPCXxcqXj6e5dJDVNovHN8744zkbhM2bYudU45BimGb", "Pren1FvFX6J3E4kXhJuCiAD5aDmGEb7qJRncwA8Lkhw", "XsoCS1TfEyfFhfvj8EtZ528L3CaKBDBRqRapnBbDF2W", "DJTu7vi8norVzdVAffgvb39VP7wjKeTsgaMBJrzfxvoF",
         "PreweJYECqtQwBtpxHL171nL2K6umo692gTm7Q3rpgF", "PresTj4Yc2bAR197Er7wz4UUKSfqt6FryBEdAriBoQB", "TSLAqBbv4CNCnzWFeB7LmydAyEiNMJtve7DYKLpdK4S"}
QNAME = {WSOL: "SOL", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC", "pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn": "PUMP", "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh": "WBTC",
         "Xsc9qvGR1efVDFGLrVsmkzv3qi45LTBjeUKSPmx9qEh": "NVDAx", "A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS": "ZEC", "SPCXxcqXj6e5dJDVNovHN8744zkbhM2bYudU45BimGb": "SPCX",
         "XsoCS1TfEyfFhfvj8EtZ528L3CaKBDBRqRapnBbDF2W": "SPYx", "DJTu7vi8norVzdVAffgvb39VP7wjKeTsgaMBJrzfxvoF": "DJT", "PresTj4Yc2bAR197Er7wz4UUKSfqt6FryBEdAriBoQB": "PreStock", "PreweJYECqtQwBtpxHL171nL2K6umo692gTm7Q3rpgF": "PreStock", "Pren1FvFX6J3E4kXhJuCiAD5aDmGEb7qJRncwA8Lkhw": "PreStock"}
SELLR = {"2kAA3Bm3npaBzrevWXJfojagG1BEAac4KwayWphYMYQG", "6iemSi2wHcEJoAwEdG69VznRPGHWJr6Y2VRSyj6m9h45", "BCzSQSmV988WPnCM6MXToLvBaL8dmj8uJWG1MaceenvX"}
def qpx(m): return 1.0 if m == WSOL else (P.get(m, {}).get("usd") or 0.0) / SOLUSD
def val(x): return x["sol_chg"] + sum(d * qpx(m) for m, d in x["tok"].items() if m in QUOTE)
def day(bt): return datetime.datetime.fromtimestamp(bt, datetime.timezone.utc).strftime("%m-%d")
M = [x for x in L if x["signer"] == W]
for x in M:
    pos = {m: d for m, d in x["tok"].items() if m not in QUOTE and d}
    x["val"] = val(x); x["pos"] = pos
    ixn = " ".join(x["ixnames"])
    if x["err"]: x["cat"] = "failed_sell" if (set(x["routers"]) & SELLR or "Sell" in ixn) else "failed_buy"
    elif "DeJBGdMFa1uynnnKiwrVioatTuHmNLpyFKnmB5kaFdzQ" in x["top"] and pos: x["cat"] = "token_out"
    elif any(d > 0 for d in pos.values()): x["cat"] = "buy"
    elif any(d < 0 for d in pos.values()): x["cat"] = "sell"
    elif any(m in QUOTE for m in x["tok"]): x["cat"] = "convert"
    elif x["routers"]: x["cat"] = "noop_guard"
    else: x["cat"] = "admin"
    x["tip"] = sum(t[1] for t in x["tips"]) / 1e9 if not x["err"] else 0.0
    x["tip_sent"] = sum(t[1] for t in x["tips"]) / 1e9
    x["astz"] = sum(l for d, l in x["xout"] if d == "AsTzjKRAZ91h6VpiR7Za5EWP8MPYRhfnRxAG4CUXL3oT") / 1e9
    x["prio"] = (x["fee"] - 5000 * x["nsig"]) / 1e9
cats = collections.defaultdict(lambda: [0, 0.0]); D = collections.defaultdict(lambda: collections.defaultdict(float))
for x in M:
    cats[x["cat"]][0] += 1; cats[x["cat"]][1] += x["val"]
    D[day(x["bt"])][x["cat"]] += x["val"]
# ---- per token
T = collections.defaultdict(lambda: dict(buys=[], sells=[], other=[], pnl=0.0))
for x in sorted(M, key=lambda x: x["slot"]):
    if x["cat"] not in ("buy", "sell", "token_out"): continue
    ms = list(x["pos"])
    for m in ms:
        r = T[m]; r["pnl"] += x["val"] / len(ms)
        (r["buys"] if x["pos"][m] > 0 else r["sells"] if x["cat"] == "sell" else r["other"]).append(dict(sig=x["sig"], slot=x["slot"], bt=x["bt"], d=x["pos"][m], v=x["val"] / len(ms),
                                                                                                     q=[QNAME.get(q, q[:6]) for q in x["tok"] if q in QUOTE], venues=x["venues"], routers=[r_[:6] for r_ in x["routers"]], tip=x["tip"], prio=x["prio"], tips=x["tips"], astz=x["astz"]))
held = {a["mint"]: a for a in H["accounts"] if a["ui"]}
def tokval(m, amt):
    if m in P and P[m].get("usd") is not None: return amt * P[m]["usd"] / SOLUSD
    a = held.get(m)
    if a and a.get("value_sol_curve") is not None and a["ui"]: return a["value_sol_curve"] * amt / a["ui"]
    return 0.0
unreal = 0.0
for m, r in T.items():
    net = sum(b["d"] for b in r["buys"]) + sum(s["d"] for s in r["sells"]) + sum(o["d"] for o in r["other"])
    r["left"] = net if net > 1e-6 else 0.0; r["left_val"] = tokval(m, r["left"]) if r["left"] else 0.0
    if r["buys"] and not r["other"]: unreal += r["left_val"]
    b0 = r["buys"][0] if r["buys"] else None
    r["quote"] = (b0["q"][0] if b0 and b0["q"] else ("SOL" if b0 else None)) if b0 else None
    vv = (b0 or {}).get("venues", [])
    r["venue"] = "LaunchLab" if "launchlab" in vv else ("pump " + ("SOL" if r["quote"] in ("SOL", None) else "other-quote")) if "pump" in vv else ("AMM" if vv else "?")
    r["spent"] = -sum(b["v"] for b in r["buys"])
    r["n_sells"] = len(r["sells"])
    if b0 and r["sells"]:
        r["first_sell_s"] = r["sells"][0]["bt"] - b0["bt"]; r["last_sell_s"] = r["sells"][-1]["bt"] - b0["bt"]
        r["first_sell_slots"] = r["sells"][0]["slot"] - b0["slot"]; r["last_sell_slots"] = r["sells"][-1]["slot"] - b0["slot"]
fees_ok = sum(x["fee"] for x in M if not x["err"]) / 1e9; fees_fail = sum(x["fee"] for x in M if x["err"]) / 1e9
tips_svc = collections.Counter()
for x in M:
    if x["err"]: continue
    for t in x["tips"]: tips_svc[t[0]] += t[1] / 1e9
    if x["astz"]: tips_svc["AsTzjKRA (private?)"] += x["astz"]
dV = sum(x["val"] for x in M) + unreal
vnow = H["balance"] + sum(tokval(a["mint"], a["ui"]) if a["mint"] not in QUOTE else a["ui"] * qpx(a["mint"]) for a in H["accounts"] if a["ui"])
print(f"window: {datetime.datetime.fromtimestamp(M[0]['bt'], datetime.timezone.utc):%m-%d %H:%M} -> {datetime.datetime.fromtimestamp(M[-1]['bt'], datetime.timezone.utc):%m-%d %H:%M} UTC, {len(M)} txs signed by the wallet")
print(f"value now {vnow:.2f} SOL (SOL {H['balance']:.2f} + WSOL/USDC/quote assets + held tokens at today's prices, SOL=106 USD)")
print("by category (count, SOL value at constant prices):", {k: (v[0], round(v[1], 3)) for k, v in sorted(cats.items())})
print(f"unrealized: launch tokens still held from window buys {unreal:+.3f}")
print(f"WINDOW PROFIT (all txs + held tokens) {dV:+.3f} SOL")
print(f"fees: successful txs {fees_ok:.3f} | failed txs {fees_fail:.3f} | tips paid (landed txs) {dict((k, round(v, 3)) for k, v in tips_svc.most_common())}")
for d in sorted(D): print("  day", d, {k: round(v, 3) for k, v in sorted(D[d].items())}, "total", round(sum(D[d].values()), 3))
R = [dict(m=m, **{k: v for k, v in r.items()}) for m, r in T.items() if r["buys"]]
print(f"position tokens bought in window: {len(R)}; fully exited {sum(1 for r in R if not r['left'])}; trading pnl (realized+held) {sum(r['pnl'] + r['left_val'] for r in R):+.3f}")
g = collections.defaultdict(list)
for r in R: g[r["venue"]].append(r["pnl"] + r["left_val"])
for k, v in g.items(): print(f"   {k:18} {len(v):4} tokens {sum(v):+8.3f} SOL  win {sum(1 for z in v if z > 0) / len(v):.0%} median {statistics.median(v):+.4f}")
json.dump(dict(window=[M[0]["bt"], M[-1]["bt"]], value_now=vnow, profit=dV, unreal=unreal, cats={k: v for k, v in cats.items()}, daily={d: dict(v) for d, v in D.items()},
               fees_ok=fees_ok, fees_fail=fees_fail, tips=dict(tips_svc), tokens=R,
               txs=[{k: x[k] for k in ("sig", "slot", "bt", "cat", "val", "pos", "fee", "prio", "tip", "tip_sent", "astz", "tips", "routers", "venues", "err", "errinfo", "cu", "cu_price", "cu_limit", "lds", "nonce", "v", "ixnames", "tok", "sol_chg", "ev")} for x in M]),
          open("truth_FiFawH.json", "w"))
