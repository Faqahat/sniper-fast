#!/usr/bin/env python3
# READ-ONLY: validate the router decode (disc 7aba70893251ee63, rest 53 B: creator 32 | 00 | usdc_in u64 | min_tokens u64 | 4 B)
# on every CPI create in a truth file: mint = acct[1], dev_est = curve cost of min_tokens (lower bound), vs TradeEvent truth.
import sys, json, collections as C
sys.path.insert(0, "/root/det")
from dlib import *
ROUTER = "6Vo3245eszAb5wuqEMw8mGdbfRUdKbHhDHP5LcaGuTAB"
R = [json.loads(l) for l in open(sys.argv[1])]
cpi = [r for r in R if r.get("top") is False and not r.get("err")]
band = lambda x: 0.5e9 <= x <= 8e9
agree, rows, kinds = C.Counter(), [], C.Counter()
for r in cpi:
    t = rpc("getTransaction", [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    nst = len(msg["accountKeys"])
    for ix in msg["instructions"]:
        if keys[ix["programIdIndex"]] != ROUTER:
            continue
        d = b58dec(ix["data"])
        kinds[(d[:8].hex(), (r.get("ev") or {}).get("quote_mint", "")[:6] == "111111")] += 1
        if d[:8].hex() != "7aba70893251ee63":
            continue
        p = 8
        for _ in range(3):
            n = int.from_bytes(d[p:p + 4], "little"); p += 4 + n
        rest = d[p:]
        if len(rest) < 49:
            agree["short"] += 1; continue
        mint = keys[ix["accounts"][1]] if ix["accounts"][1] < nst else None
        mint_ok = mint == r["mint"]
        creator = b58enc(rest[0:32])
        usdc = int.from_bytes(rest[33:41], "little")
        mt = int.from_bytes(rest[41:49], "little")
        est, _, _ = cap_cost(VQ0, VT0, mt)
        same = band(est) == band(r["true_dev"])
        agree[("mint_ok", mint_ok)] += 1
        agree[("band_agree", same)] += 1
        agree[("creator==ev", creator == (r.get("ev") or {}).get("creator"))] += 1
        rows.append((r["mint"][:8], r["true_dev"] / 1e9, est / 1e9, usdc / 1e6, round(est / max(r["true_dev"], 1), 3)))
        e = r.get("ev") or {}
        agree[("tail", rest[32:33].hex(), rest[49:].hex(), "ev(mayhem,cashback,fee,holder)", e.get("mayhem"), e.get("cashback"), e.get("fee_bps"), e.get("holder"))] += 1
print("router create kinds (disc, SOL quote):", dict(kinds))
print("decode checks:", dict(agree))
for x in rows[:20]:
    print("  mint %s true %.4f SOL est(min_tokens) %.4f SOL usdc_in %.2f ratio %.3f" % x)
rat = sorted(x[4] for x in rows if x[1] > 0)
if rat:
    print("est/true ratio: min %.3f p10 %.3f median %.3f max %.3f (n=%d)" % (rat[0], rat[len(rat)//10], rat[len(rat)//2], rat[-1], len(rat)))
