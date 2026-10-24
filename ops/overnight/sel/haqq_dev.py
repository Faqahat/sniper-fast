#!/usr/bin/env python3
# Owner 10-24 06:05 PKT: a contact says "haqq wallet is mostly buying from this dev" (bwamJzzt...fSXa, gmgn link). Verify on the
# collector window (RP_PHASEA_R3 = phaseA_r3all: tokens launched 01:35 -> ~05:55 PKT, full tapes): who created each token the
# wallets traded; their buys / SOL / P&L on that dev's tokens vs the dev's share of all launches and of all >= 1 SOL dumps (the
# base rate); whether their buys come right after the DEV's own sell; the same for the other imitated bots and for our fills.
# usage: python3 -I haqq_dev.py [dev]
import os, sys, json, collections
os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3all"); os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd")
os.environ.update(SELL_LAT="75", DIP_LATS="35,50,75", DIP_B="0.35", DIP_COHORT_FILE="/home/moiz/sniper/ops/overnight/sel/cohort_train.json")
D = "/home/moiz/sniper/ops/overnight/sel"; sys.path.insert(0, D)
import selexit2 as X
DEV = sys.argv[1] if len(sys.argv) > 1 else "bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa"
WAL = {"haqqiUUX": "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq", "HkQ7hMjy": "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ",
       "DYXDDrZC": "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw", "us (2g)": "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
T0 = int(os.environ.get("EXTRACT_T0", "1792787700"))
creator = lambda c: c.get("creator") or c.get("user")
# the dev SIGNS ~30 creates/h; in ~60% the pump creator field is a fresh one-off wallet -> a token is "this dev's" if it signed OR is creator
is_dev = lambda c: DEV in (c.get("user"), c.get("creator"), c.get("payer"))
recent = {m for m, c in X.L.items() if c["run"] == "R3" and c["bt"] >= T0 + 60}
byb = collections.defaultdict(set)
for m in recent: byb[("R3", X.rp.bucket(m))].add(m)
base = collections.Counter(); dumps = collections.Counter(); dev_sells = collections.Counter(); seen = set()
st = {n: collections.defaultdict(lambda: collections.Counter()) for n in WAL}     # name -> dev/other -> counters
tok_pnl = {n: collections.defaultdict(list) for n in WAL}
first_buy_after = {n: collections.Counter() for n in WAL}
for key in sorted(byb):
    for m, tr in X.rp.read_bucket(key[0], key[1], byb[key]).items():
        seen.add(m); cls = "dev" if is_dev(X.L[m]) else "other"; base[cls] += 1
        for t in tr:
            if not t["buy"] and t["sol"] >= 1e9 and not t.get("syn"):
                dumps[cls] += 1
                if t.get("user") in (DEV, creator(X.L[m])): dev_sells[cls] += 1
        for n, W in WAL.items():
            mine = [k for k, t in enumerate(tr) if t.get("user") == W]
            if not mine: continue
            c = st[n][cls]; c["tokens"] += 1; sin = sout = 0.0; left = 0
            for k in mine:
                t = tr[k]
                if t["buy"]:
                    c["buys"] += 1; c["sol_in"] += t["sol"] / 1e9; sin += t["sol"] / 1e9; left += t["tok"]
                    big = next((tr[j] for j in range(k - 1, max(-1, k - 40), -1) if not tr[j]["buy"] and tr[j]["sol"] >= 1e9 and X.arr(t) - X.arr(tr[j]) <= 1500), None)
                    if big is None: first_buy_after[n]["no >= 1 SOL dump within 1.5 s"] += 1
                    elif big.get("user") == DEV or (cls == "dev" and big.get("user") == creator(X.L[m])): first_buy_after[n]["right after a sell BY THIS DEV (or its creator wallet)"] += 1
                    elif big.get("user") == creator(X.L[m]): first_buy_after[n]["right after a sell by that token's own (other) dev"] += 1
                    else: first_buy_after[n]["right after a sell by a non-dev wallet"] += 1
                else: c["sells"] += 1; sout += t["sol"] / 1e9; left -= t["tok"]
            if left > 0:                                                     # still holding at the end of the tape: mark to market
                z = tr[-1]; kk = z["vsol"] * z["vtok"]; sout += (z["vsol"] - kk / (z["vtok"] + left)) / 1e9; c["open"] += 1
            tok_pnl[n][cls].append(sout * (1 - 0.0125) - sin * (1 + 0.0125))
            if n == "us (2g)" and cls == "dev": print(f"  our fill on this dev's token: {m}")
print(f"window: {len(seen)} tokens launched {X.L and ''}01:35 -> ~05:55 PKT 10-24 (collector tapes); dev {DEV}")
tb = sum(base.values()); td = sum(dumps.values())
print(f"  this dev created {base['dev']} of {tb} tokens ({100 * base['dev'] / tb:.1f}%); {dumps['dev']} of {td} sells >= 1 SOL ({100 * dumps['dev'] / max(1, td):.1f}%) were on its tokens"
      f" ({dev_sells['dev']} of those by the dev / its creator wallet; on other tokens {dev_sells['other']} of {dumps['other']} by their dev)")
for n in WAL:
    a, b = st[n]["dev"], st[n]["other"]; nb = a["buys"] + b["buys"]
    if not nb: print(f"\n{n}: no trades in the window"); continue
    pa, pb = tok_pnl[n]["dev"], tok_pnl[n]["other"]
    print(f"\n{n}: {nb} buys on {a['tokens'] + b['tokens']} tokens; ON THIS DEV'S TOKENS: {a['buys']} buys ({100 * a['buys'] / nb:.0f}%), "
          f"{a['tokens']} tokens, {a['sol_in']:.1f} of {a['sol_in'] + b['sol_in']:.1f} SOL ({100 * a['sol_in'] / max(1e-9, a['sol_in'] + b['sol_in']):.0f}%)")
    print(f"  traded {a['tokens']} of this dev's {base['dev']} tokens ({100 * a['tokens'] / max(1, base['dev']):.0f}%) vs {b['tokens']} of {base['other']} other tokens ({100 * b['tokens'] / max(1, base['other']):.1f}%); open at tape end: {a['open']} / {b['open']}")
    print(f"  P&L (sells - buys, ~1.25% fee each way, open positions marked at the last price): this dev {sum(pa):+.2f} SOL on {len(pa)} tokens "
          f"(win {100 * sum(1 for x in pa if x > 0) / max(1, len(pa)):.0f}%) | other devs {sum(pb):+.2f} SOL on {len(pb)} tokens (win {100 * sum(1 for x in pb if x > 0) / max(1, len(pb)):.0f}%)")
    print("  what came right before each buy: " + "; ".join(f"{k} {v}" for k, v in first_buy_after[n].most_common()))
