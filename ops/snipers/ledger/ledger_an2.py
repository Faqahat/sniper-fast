#!/usr/bin/env python3
# READ-ONLY, offline: full-value accounting (SOL + WSOL + stablecoins + PUMP) of a wallet ledger. A tx is "trading" if it has a
# pump.fun trade by the wallet or touches a swap program; else token/SOL movements are external (deposits / withdrawals).
# Stablecoins valued at SOLUSD (arg), PUMP at its observed price; other tokens only through what they were sold for.
import sys, json, collections, datetime
D = json.load(open(sys.argv[1])); W = D["wallet"]; SOLUSD = float(sys.argv[2]) if len(sys.argv) > 2 else 106.0
T = sorted([x for x in D["txs"] if not x.get("missing")], key=lambda x: (x["slot"], x["sig"])); miss = sum(1 for x in D["txs"] if x.get("missing"))
WSOL = "So11111111111111111111111111111111111111112"; STABLE = {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT", "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB": "USD1"}
PUMPTOK = "pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn"; PUMP_SOL = 0.004673 / SOLUSD
SWAP = ("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "akbotssn", "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",
        "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C")
def val(x):
    v = x["sol_chg"]; tv = {}
    for m, d in x["tok"].items():
        if m == WSOL: tv["WSOL"] = d
        elif m in STABLE: tv[STABLE[m]] = d / SOLUSD
        elif m == PUMPTOK: tv["PUMP"] = d * PUMP_SOL
    return v + sum(tv.values()), tv
cat = collections.Counter(); day = collections.defaultdict(collections.Counter); stable_ext = collections.Counter()
for x in T:
    v, tv = val(x)
    trading = bool(x["trades"]) or any(any(p and p.startswith(s) for s in SWAP) for p in x.get("progs", []))
    if x.get("err"): k = "failed tx fees"
    elif trading: k = "trading (value incl. WSOL/stable/PUMP legs)"
    elif any(d and d.startswith("AKbot") for s, d, l in x["xfers"] if s == W): k = "bot fees (AKbot)"
    elif v >= 0.05: k = "deposits (SOL + tokens)"
    elif v <= -0.05: k = "withdrawals (SOL + tokens)"
    else: k = "other (rent, nonce, dust)"
    cat[k] += v
    d = datetime.datetime.fromtimestamp(x["bt"], datetime.timezone.utc).strftime("%m-%d") if x["bt"] else "?"
    day[d][k] += v
    if k.startswith(("deposits", "withdrawals")):
        for kk, vv in tv.items(): stable_ext[kk] += vv
hold_val = D["balance_now"]; extra = []
for m, a in D["holdings_now"]:
    if m == WSOL: hold_val += a; extra.append(f"WSOL {a:.2f}")
    elif m in STABLE: hold_val += a / SOLUSD; extra.append(f"{STABLE[m]} {a:,.0f} (= {a / SOLUSD:.2f} SOL)")
    elif m == PUMPTOK: hold_val += a * PUMP_SOL; extra.append(f"PUMP {a:,.0f}")
tot = sum(cat.values())
trade_res = sum(v for k, v in cat.items() if k.startswith(("trading", "failed", "bot", "other")))
print(f"== {W}  ({len(T)} txs, {miss} missing; SOL = ${SOLUSD})")
print(f"   value now: {hold_val:.3f} SOL ({D['balance_now']:.3f} SOL + {', '.join(extra)}; other tokens not counted)")
print(f"   sum of all value changes {tot:.3f} SOL vs value now {hold_val:.3f}  -> {'CONSISTENT' if abs(tot - hold_val) < 0.5 else 'gap ' + format(hold_val - tot, '+.3f')}")
for k, v in sorted(cat.items(), key=lambda kv: kv[1]): print(f"   {k:46} {v:+10.3f} SOL")
print(f"   => TRADING RESULT after every fee: {trade_res:+.3f} SOL   (token parts of external flows: { {k: round(v, 2) for k, v in stable_ext.items()} })")
print("   per day: " + " | ".join(f"{d} {sum(v for k, v in c.items() if k.startswith(('trading', 'failed', 'bot', 'other'))):+.2f}" for d, c in sorted(day.items())))
