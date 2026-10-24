#!/usr/bin/env python3
# READ-ONLY RPC: test fixtures for src/dip.rs (direct_sells, trade_events): real direct-trigger txs as wire bytes (base64) plus
# their log lines and the expected decode (from the tx's own TradeEvents). Picks 2 per sell layout, preferring a v1 tx and
# a multi-sell tx. -> /home/moiz/sniper/testdata/dip_sells.json
import json, os, time, base64, urllib.request, collections
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238]); PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
LAY = {"33e685a4017f83ad": (2, 6), "1c92de7726c469d5": (1, 8), "5df6823ce7e940b2": (1, 13)}
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
U = lambda b, o: int.from_bytes(b[o:o + 8], "little")
def rpc(m, p):
    for i in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                                                        headers={"content-type": "application/json"}), timeout=30))
            if "result" in r and r["result"]: return r["result"]
        except Exception: pass
        time.sleep(0.5 * (i + 1))
D = json.load(open("trig_decode.json"))
by = collections.defaultdict(list)
for r in D: by[r["disc"]].append(r)
want = []
for disc in LAY:
    rows = by[disc]
    multi = [r for r in rows if r["n_sell_ev"] > 1][:1]
    rest = [r for r in rows if r["n_sell_ev"] == 1 and r["a8_eq_tok"]][:3]
    want += [r["sig"] for r in multi + rest]
out = []; seen = set()
for sig in want:
    if sig in seen: continue
    seen.add(sig)
    tj = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    tb = rpc("getTransaction", [sig, {"encoding": "base64", "maxSupportedTransactionVersion": 1}])
    if not tj or not tb: continue
    msg = tj["transaction"]["message"]; la = tj["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    exp = []
    for ix in msg["instructions"]:
        if keys[ix["programIdIndex"]] != PUMP: continue
        d = b58dec(ix["data"]); lay = LAY.get(d[:8].hex())
        if not lay or len(d) < 24: continue
        accs = [keys[a] for a in ix["accounts"]]
        exp.append(dict(mint=accs[lay[0]], seller=accs[lay[1]], tokens=U(d, 8), min_sol=U(d, 16)))
    evs = []
    for l in tj["meta"].get("logMessages") or []:
        if not l.startswith("Program data: "): continue
        for part in l[14:].split():
            x = part + "=" * (-len(part) % 4)
            try: raw = base64.b64decode(x)
            except Exception: continue
            if raw[:8] == TD and len(raw) >= 113:
                evs.append(dict(mint=b58enc(raw[8:40]), sol=U(raw, 40), tok=U(raw, 48), buy=raw[56] == 1, user=b58enc(raw[57:89]), vsol=U(raw, 97), vtok=U(raw, 105)))
    out.append(dict(sig=sig, version=tj.get("version"), wire_b64=tb["transaction"][0], loaded=la, logs=tj["meta"].get("logMessages") or [],
                    expected_sells=exp, expected_events=evs))
json.dump(out, open("/home/moiz/sniper/testdata/dip_sells.json", "w"), indent=1)
print("fixtures", len(out), "| versions", collections.Counter(str(o["version"]) for o in out), "| sells per tx", [len(o["expected_sells"]) for o in out],
      "| events per tx", [len(o["expected_events"]) for o in out], "| with lookups", sum(1 for o in out if (o["loaded"] or {}).get("writable") or (o["loaded"] or {}).get("readonly")))
