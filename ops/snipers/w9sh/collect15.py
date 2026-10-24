#!/usr/bin/env python3
# READ-ONLY: everything the HTML report needs for 9Sh2fd's last N create-block snipes (SOL-quoted), from deep.json (his txs),
# bs_9sh.json (each create block's buyers, Jito-verified) and a few fresh getTransaction calls (create event names, his buy tx
# details: version, nonce, compute units, LandX tip account). usage: RPC_URL=... python3 -I collect15.py [N=15]
import os, sys, json, base64, hashlib, urllib.request, datetime, statistics, collections
HERE = os.path.dirname(os.path.abspath(__file__)); N = int(sys.argv[1]) if len(sys.argv) > 1 else 15
EP = os.environ["RPC_URL"]; W = "9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1"
def rpc(m, p):
    for _ in range(5):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
CDISC = hashlib.sha256(b"event:CreateEvent").digest()[:8]
def create_event(tx):
    for l in tx["meta"]["logMessages"] or []:
        if not l.startswith("Program data: "): continue
        s = l[14:].strip(); s += "=" * (-len(s) % 4)
        try: raw = base64.b64decode(s)
        except Exception: continue
        if raw[:8] != CDISC: continue
        o = 8; out = []
        for _ in range(3):
            n = int.from_bytes(raw[o:o + 4], "little"); out.append(raw[o + 4:o + 4 + n].decode("utf-8", "replace")); o += 4 + n
        return dict(name=out[0], symbol=out[1], uri=out[2], mint=b58(raw[o:o + 32]), creator=b58(raw[o + 96:o + 128]) if len(raw) >= o + 128 else b58(raw[o + 64:o + 96]))
D = json.load(open(os.path.join(HERE, "deep.json"))); T = sorted(D["txs"], key=lambda t: t["slot"])
BS = {x["mint"]: x for x in json.load(open(os.path.join(HERE, "bs_9sh.json"))) if x}
buys = [t for t in T if any(e["buy"] for e in t["ev"])]
fees = [t for t in T if not t["ev"] and t["sol_chg"] is not None and -0.2 < t["sol_chg"] < -0.001]
picks = []
for t in reversed(buys):
    e = next(e for e in t["ev"] if e["buy"])
    if t.get("delta") != 0 or e["sol"] == 0 or e["mint"] not in BS: continue
    x = BS[e["mint"]]; rows = [r for r in x["rows"] if r["buy"] and r["ok"]]
    me = [r for r in rows if W in r["users"] and r["cls"] == "sniper"]
    if not me: continue
    picks.append((t, e, x, me[0]))
    if len(picks) >= N: break
out = []
for t, e, x, me in picks:
    S = x["S"]; size = e["sol"] / 1e9
    ct = rpc("getTransaction", [t["create_sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1}]) if t.get("create_sig") else None
    ce = create_event(ct) if ct else None
    bt = rpc("getTransaction", [t["sig"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
    ixs = bt["transaction"]["message"]["instructions"]
    nonce = next((ix["parsed"]["info"]["nonceAccount"] for ix in ixs if ix.get("parsed") and ix["parsed"].get("type") == "advanceNonce"), None)
    tip_to = [(ix["parsed"]["info"]["destination"], ix["parsed"]["info"]["lamports"] / 1e9) for ix in ixs if ix.get("parsed") and ix["parsed"].get("type") == "transfer"]
    rows = [r for r in x["rows"] if r["buy"] and r["ok"]]
    fee = lambda r: r["prio"] + sum(tt[1] for tt in r["tips"])
    block = [dict(pos=r["pos"], cls=r["cls"], who=r["users"][0], sol=r["sol"], prio=r["prio"], tips=r["tips"], fee=fee(r), bundle=r["bundle"], sig=r["sig"]) for r in rows]
    # his sells of this token, the 1% bot fee after the buy, realized result (sum of his wallet's SOL changes)
    sells = [s for s in T if s["slot"] >= t["slot"] and any((not ev["buy"]) and ev["mint"] == e["mint"] for ev in s["ev"])]
    botfee = next((f for f in fees if f["slot"] > t["slot"] and abs((-f["sol_chg"] - 0.000005) - 0.01 * size) < 0.00001), None)
    realized = (t["sol_chg"] or 0) + sum(s["sol_chg"] or 0 for s in sells) + ((botfee["sol_chg"] or 0) if botfee else 0)
    out.append(dict(mint=e["mint"], name=(ce or {}).get("name"), symbol=(ce or {}).get("symbol"), creator=(ce or {}).get("creator") or e.get("creator"), create_sig=t.get("create_sig"),
                    S=S, bt=t["bt"], create_bt=(ct or {}).get("blockTime"), buy_sig=t["sig"], buy_slot=t["slot"], size=size, prio=t["prio"], tips=t["tips"], tip_to=tip_to,
                    version=bt.get("version"), cu=bt["meta"].get("computeUnitsConsumed"), nonce=nonce, pos=me["pos"], in_bundle=me["bundle"],
                    rank=1 + sum(1 for r in rows if r["cls"] == "sniper" and r["pos"] < me["pos"]), n_out=sum(1 for r in rows if r["cls"] == "sniper"),
                    dev_sol=sum(r["sol"] for r in rows if r["cls"] == "create"), bundle_sol=sum(r["sol"] for r in rows if r["cls"] in ("glued", "creator-bundle")),
                    bundle_legs=sum(1 for r in rows if r["cls"] in ("glued", "creator-bundle")), block=block, buy_chg=t["sol_chg"],
                    sells=[dict(sig=s["sig"], slot=s["slot"], chg=s["sol_chg"], bt=s["bt"]) for s in sells], botfee=dict(sig=botfee["sig"], slot=botfee["slot"], amt=-botfee["sol_chg"] - 0.000005, bt=botfee["bt"]) if botfee else None,
                    realized=realized))
json.dump(dict(wallet=W, snipes=out), open(os.path.join(HERE, "snipes15.json"), "w"), indent=1)
for s in out:
    print(f"{s['symbol'] or s['mint'][:6]:10} S={s['S']} pos +{s['pos']} rank {s['rank']}/{s['n_out']} size {s['size']:.3f} prio {s['prio']:.4f} tips {s['tips']} v{s['version']} cu {s['cu']} nonce {bool(s['nonce'])} sells {len(s['sells'])} botfee {bool(s['botfee'])} realized {s['realized']:+.4f}")
