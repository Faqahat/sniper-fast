#!/usr/bin/env python3
# who buys right after each wallet's first buy? repeat followers (= copy bots aimed at that wallet) vs their base rate,
# how fast they land (same slot / txs after), and how much of the wallet's exit liquidity they provide. Read-only, tapes. -> out/followers.json
import os, sys, json, collections, statistics, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat, lib3
T, F = lib3.load_tapes(); P = json.load(open(os.path.join(lib3.HERE, "out/pos3.json"))); L = lib3.load_launches()
def msf(t):
    n = lib3.slot_size(t["s"]) or 450
    return t["s"] * 212.0 + min(t["i"] / max(n, t["i"] + 1), 0.999) * 212.0
out = {}
for w8, W in lib3.W3.items():
    pos = [p for p in P if p["w"] == w8 and not p.get("nobuy") and not p["mayhem"]]
    cnt = collections.Counter(); sol = collections.defaultdict(float); lag_ms = collections.defaultdict(list); lag_tx = collections.defaultdict(list)
    tokens_any = collections.Counter()   # follower -> tokens where it traded at all (any time)
    first_tx_after = []; same_slot = 0; fails_after = []
    for p in pos:
        tr = T[p["m"]]; k0 = p["k0"]; b0 = tr[k0]; m0 = msf(b0)
        seen = set()
        for k in range(k0 + 1, len(tr)):
            t = tr[k]
            if t["s"] - b0["s"] > 2: break
            if t["buy"] and t["user"] != W and t["user"] not in seen:
                seen.add(t["user"]); cnt[t["user"]] += 1; sol[t["user"]] += t["sol"] / 1e9
                lag_ms[t["user"]].append(msf(t) - m0); lag_tx[t["user"]].append(t["i"] - b0["i"] if t["s"] == b0["s"] else None)
        for u in {t["user"] for t in tr}: tokens_any[u] += 1
        # failed txs touching the token in the 2 slots after their buy (slippage losers / copy spam)
        fl = [x for x in F.get(p["m"], []) if 0 <= x[0] - b0["s"] <= 2 and (x[0], x[1]) > (b0["s"], b0["i"])]
        fails_after.append(len(fl))
    top = []
    for u, c in cnt.most_common(15):
        lt = [x for x in lag_tx[u] if x is not None]
        top.append(dict(wallet=u, hits=c, of=len(pos), rate=c / len(pos), traded_tokens_of_these=tokens_any[u], sol=sol[u] / c,
                        lag_ms_med=statistics.median(lag_ms[u]), same_slot=len(lt) / c, tx_after_med=statistics.median(lt) if lt else None))
    out[w8] = dict(n=len(pos), top=top, fails_after_med=statistics.median(fails_after) if fails_after else None, fails_after_mean=statistics.mean(fails_after) if fails_after else None,
                   repeat_followers_ge20pct=sum(1 for u, c in cnt.items() if c >= 0.2 * len(pos)), repeat_followers_ge10pct=sum(1 for u, c in cnt.items() if c >= 0.1 * len(pos)))
json.dump(out, open(os.path.join(lib3.HERE, "out/followers.json"), "w"), indent=1)
for w8, o in out.items():
    print(f"\n## {w8}: {o['n']} first buys | followers hitting >=20% of them: {o['repeat_followers_ge20pct']}, >=10%: {o['repeat_followers_ge10pct']} | failed txs in the 2 slots after: med {o['fails_after_med']} mean {o['fails_after_mean']:.1f}")
    for x in o["top"][:12]:
        print(f"  {x['wallet'][:8]} buys within 2 slots after on {x['hits']}/{x['of']} ({x['rate']:.0%}) | traded {x['traded_tokens_of_these']} of these tokens at all | "
              f"avg {x['sol']:.2f} SOL | lag med {x['lag_ms_med']:.0f} ms | same slot {x['same_slot']:.0%} (tx after med {x['tx_after_med']})")
