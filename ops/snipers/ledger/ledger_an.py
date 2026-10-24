#!/usr/bin/env python3
# READ-ONLY, offline: ground-truth accounting of a wallet ledger (ledger.py). Profit = what came out of trading, with no model:
# every SOL change of the wallet, split into deposits / withdrawals (external transfers), trades (per token), failed-tx fees,
# bot fees (AKbot billing transfers) and other. Consistency check: sum of all changes == balance now.
import sys, json, collections, datetime
D = json.load(open(sys.argv[1])); W = D["wallet"]; T = sorted(D["txs"], key=lambda x: (x["slot"], x["sig"]))
TIPS = set(json.load(open("/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/run1/tipmap.json")))
day = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%m-%d") if t else "?"
cat = collections.Counter(); per_mint = collections.defaultdict(float); per_day = collections.defaultdict(lambda: collections.Counter())
ext = collections.defaultdict(float); n_missing = 0; first = None
for x in T:
    if x.get("missing"): n_missing += 1; continue
    first = first or x["bt"]
    c = x["sol_chg"]
    if x.get("err"): k = "failed tx fees"
    elif x["trades"]:
        k = "trading"
        mints = {tr["mint"] for tr in x["trades"]}
        for m in mints: per_mint[m] += c / len(mints)
    else:
        outs = [(d, l) for s, d, l in x["xfers"] if s == W and d not in TIPS]; ins = [(s, l) for s, d, l in x["xfers"] if d == W]
        if any(d.startswith("AKbot") for d, _ in outs): k = "bot fees (AKbot)"
        elif outs and sum(l for _, l in outs) >= 0.05: k = "withdrawals"; [ext.__setitem__("-> " + d, ext["-> " + d] + l) for d, l in outs]
        elif ins and sum(l for _, l in ins) >= 0.05: k = "deposits"; [ext.__setitem__("<- " + s, ext["<- " + s] + l) for s, l in ins]
        else: k = "other (accounts, nonce, dust)"
    cat[k] += c; per_day[day(x["bt"])][k] += c
tot = sum(cat.values())
print(f"== {W}  (first tx {day(first)}; {len(T)} txs, {n_missing} missing)")
print(f"   balance now {D['balance_now']:.4f} SOL | sum of all SOL changes {tot:.4f} SOL  -> {'CONSISTENT' if abs(tot - D['balance_now']) < 0.05 else 'MISMATCH ' + format(tot - D['balance_now'], '+.4f')}")
for k, v in sorted(cat.items(), key=lambda kv: kv[1]): print(f"   {k:32} {v:+10.4f} SOL")
trade_pnl = cat["trading"] + cat["failed tx fees"] + cat["bot fees (AKbot)"] + cat["other (accounts, nonce, dust)"]
print(f"   => TRADING RESULT (trades + failed fees + bot fees + other) {trade_pnl:+.4f} SOL; deposits {cat['deposits']:+.3f}, withdrawals {cat['withdrawals']:+.3f}")
print(f"   holdings now (token accounts with a balance): {len(D['holdings_now'])} {D['holdings_now'][:4]}")
print("   per day (trading | failed | bot fees):")
for d in sorted(per_day): c = per_day[d]; print(f"      {d}: {c['trading']:+8.3f} | {c['failed tx fees']:+7.3f} | {c['bot fees (AKbot)']:+7.3f}   net {c['trading'] + c['failed tx fees'] + c['bot fees (AKbot)'] + c['other (accounts, nonce, dust)']:+8.3f}")
print("   biggest external counterparties:", sorted(((round(v, 3), k[:14]) for k, v in ext.items()), reverse=True)[:6])
w = sorted(per_mint.values()); n = len(w)
print(f"   tokens traded {n}: winners {sum(1 for v in w if v > 0)} ({sum(v for v in w if v > 0):+.2f}), losers {sum(1 for v in w if v <= 0)} ({sum(v for v in w if v <= 0):+.2f}); top 5 {[round(v, 2) for v in w[-5:]]}")
json.dump(dict(per_mint=per_mint, cat=cat), open(sys.argv[1].replace(".json", "_an.json"), "w"))
