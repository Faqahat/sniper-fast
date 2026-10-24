#!/usr/bin/env python3
# READ-ONLY, offline ground truth. A tx is TRADING if the wallet has a pump trade, or ANY token other than SOL/WSOL/stables
# moved in its accounts, or it swapped between SOL and a stablecoin. Bot fees = transfers to AKbot accounts. Failed = fees of
# failed txs. Everything else that moves value is EXTERNAL (deposit / withdrawal), with the counterparty shown.
# PROFIT = value now - deposits + withdrawals  ==  trading + bot fees + failed + other   (checked against each other)
import sys, json, collections, datetime
SOLUSD = float(sys.argv[2]) if len(sys.argv) > 2 else 106.0
WSOL = "So11111111111111111111111111111111111111112"; STABLE = {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB"}
D = json.load(open(sys.argv[1])); W = D["wallet"]; T = [x for x in D["txs"] if not x.get("missing")]
val = lambda x: x["sol_chg"] + x["tok"].get(WSOL, 0) + sum(v for m, v in x["tok"].items() if m in STABLE) / SOLUSD
cat = collections.Counter(); ext = collections.defaultdict(float); day = collections.defaultdict(collections.Counter)
for x in T:
    v = val(x); other_tok = any(m != WSOL and m not in STABLE and abs(d) > 0 for m, d in x["tok"].items())
    stab = sum(d for m, d in x["tok"].items() if m in STABLE); solish = x["sol_chg"] + x["tok"].get(WSOL, 0)
    swap = abs(stab) > 1 and abs(solish) > 0.01 and (stab > 0) != (solish > 0)
    if x.get("err"): k = "failed tx fees"
    elif x["trades"] or other_tok or swap: k = "trading"
    elif any(d and d.startswith("AKbot") for s, d, l in x["xfers"] if s == W): k = "bot fees"
    elif abs(v) < 0.05: k = "other"
    else:
        k = "deposit" if v > 0 else "withdrawal"
        cps = [s for s, d, l in x["xfers"] if d == W and l >= 0.01] if v > 0 else [d for s, d, l in x["xfers"] if s == W and l >= 0.01]
        ext[(k, cps[0] if cps else "token transfer")] += v
    cat[k] += v
    if x.get("bt"): day[datetime.datetime.fromtimestamp(x["bt"], datetime.timezone.utc).strftime("%m-%d")][k] += v
vnow = D["balance_now"] + sum(a for m, a in D["holdings_now"] if m == WSOL) + sum(a for m, a in D["holdings_now"] if m in STABLE) / SOLUSD
prof_flow = vnow - cat["deposit"] - cat["withdrawal"]
prof_sum = cat["trading"] + cat["bot fees"] + cat["failed tx fees"] + cat["other"]
other_held = [(m[:6], round(a)) for m, a in D["holdings_now"] if m != WSOL and m not in STABLE]
print(f"== {W}: {len(T)} txs ({len(D['txs']) - len(T)} missing)")
print(f"   value now {vnow:.2f} SOL | deposits {cat['deposit']:+.2f} | withdrawals {cat['withdrawal']:+.2f}")
print(f"   PROFIT (value now - money in + money out) {prof_flow:+.2f} SOL | same from the parts {prof_sum:+.2f} (difference {prof_flow - prof_sum:+.2f})")
print(f"   parts: trading {cat['trading']:+.2f} | bot fees {cat['bot fees']:+.2f} | failed tx fees {cat['failed tx fees']:+.2f} | other {cat['other']:+.2f}")
print("   external:", [(k[0], k[1][:10], round(v, 2)) for k, v in sorted(ext.items(), key=lambda kv: kv[1])])
print("   per day (profit):", " | ".join(f"{d} {c['trading'] + c['bot fees'] + c['failed tx fees'] + c['other']:+.2f}" for d, c in sorted(day.items())))
print("   pump tokens still held (not valued):", other_held[:6])
