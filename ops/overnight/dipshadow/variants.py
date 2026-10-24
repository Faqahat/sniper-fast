#!/usr/bin/env python3
# Map every TOP-LEVEL pump.fun instruction variant in the sample: discriminator, data length, the account positions holding the
# mint and the trade's user (from the tx's own TradeEvent), and how the u64 args relate to the event's SOL / token amounts.
import sys, json, collections, base64
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
U = lambda b, o: int.from_bytes(b[o:o + 8], "little") if len(b) >= o + 8 else None
V = collections.defaultdict(lambda: dict(n=0, lens=collections.Counter(), mintpos=collections.Counter(), userpos=collections.Counter(), buy=collections.Counter(),
                                          a8=collections.Counter(), a16=collections.Counter(), nacc=collections.Counter()))
routed = 0; total = 0
for l in open(sys.argv[1]):
    r = json.loads(l); t = r["tx"]
    if not t or t.get("meta", {}).get("err") is not None: continue
    total += 1
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    top = [ix for ix in msg["instructions"] if keys[ix["programIdIndex"]] == PUMP]
    if not top: routed += 1; continue
    for ix in top:
        d = b58dec(ix["data"]); disc = d[:8].hex(); v = V[disc]; v["n"] += 1; v["lens"][len(d)] += 1; v["nacc"][len(ix["accounts"])] += 1
        accs = [keys[i] for i in ix["accounts"]]
        if r["mint"] in accs: v["mintpos"][accs.index(r["mint"])] += 1
        if r["ev_user"] in accs: v["userpos"][accs.index(r["ev_user"])] += 1
        v["buy"][r["ev_buy"]] += 1
        a8, a16 = U(d, 8), U(d, 16)
        sol, tok = r["ev_sol"], r["ev_tok"]
        def rel(a):
            if a is None: return "none"
            if a == tok: return "=tok"
            if a == sol: return "=sol"
            if sol and 0.9 < a / sol < 1.2: return "~sol(+fee)"
            if tok and a <= tok and a > 0.5 * tok: return "<=tok(min out)"
            if tok and a >= tok * 0.98 and a < tok * 1.5: return "~tok"
            if sol and a > sol: return ">sol(max cost)"
            if tok and a < tok: return "<tok(min out)"
            return "other"
        v["a8"][rel(a8)] += 1; v["a16"][rel(a16)] += 1
print(f"successful txs {total}, with no top-level pump ix (routed/CPI) {routed} ({routed / max(total, 1):.0%})")
for disc, v in sorted(V.items(), key=lambda kv: -kv[1]["n"]):
    print(f"{disc} n {v['n']:4d} len {dict(v['lens'])} accounts {dict(v['nacc'])} buy {dict(v['buy'])} mintpos {dict(v['mintpos'])} userpos {dict(v['userpos'])} | a8 {dict(v['a8'])} | a16 {dict(v['a16'])}")
