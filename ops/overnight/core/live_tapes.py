#!/usr/bin/env python3
# READ-ONLY: what really happened around OUR live round trips. For every pump.fun mint the wallet bought and sold in
# [since, until), fetch every trade on that mint from the create to a few slots after our last sell, with its exact
# block position (getBlock signature order), and print the tape: who traded between our buy and our sell, how much,
# and how the price moved. RPC = the owner's endpoint from ~/.config/sniper/ck_rpc_url (never printed).
# usage: python3 -I live_tapes.py <wallet> <since_unix> <until_unix> [out.json]
import sys, os, json, time, base64, urllib.request, concurrent.futures as cf
W, SINCE, UNTIL = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
OUT = sys.argv[4] if len(sys.argv) > 4 else None
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])           # TradeEvent
CD = bytes([27, 114, 169, 77, 222, 235, 99, 118])            # CreateEvent
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def b58d(s):
    n = 0
    for ch in s: n = n * 58 + B58.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw
def rpc(m, p, tries=6):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                                                        headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.5 + i)
    return None
U = lambda raw, a: int.from_bytes(raw[a:a + 8], "little")
def events(t):
    """pump.fun Trade/Create events of a tx (logs, then self-CPI inner instructions)"""
    out, seen = [], set()
    blobs = []
    for l in (t["meta"].get("logMessages") or []):
        if l.startswith("Program data: "):
            x = l[14:].strip(); x += "=" * (-len(x) % 4)
            try: blobs.append(base64.b64decode(x))
            except Exception: pass
    for inn in (t["meta"].get("innerInstructions") or []):
        for ix in inn["instructions"]:
            d = ix.get("data")
            if d:
                try:
                    raw = b58d(d)
                    if len(raw) > 16: blobs.append(raw[8:])
                except Exception: pass
    for raw in blobs:
        if raw[:8] == TD and len(raw) >= 129:
            k = raw[8:129]
            if k in seen: continue
            seen.add(k)
            out.append(dict(kind="T", mint=b58(raw[8:40]), sol=U(raw, 40), tok=U(raw, 48), buy=raw[56] == 1, user=b58(raw[57:89]),
                            vsol=U(raw, 97), vtok=U(raw, 105)))
        elif raw[:8] == CD and len(raw) > 100:
            out.append(dict(kind="C"))
    return out
# 1) the wallet's signatures in the window
sigs, before = [], None
while True:
    p = {"limit": 1000}
    if before: p["before"] = before
    r = rpc("getSignaturesForAddress", [W, p]) or []
    sigs += r
    if len(r) < 1000 or (r and (r[-1].get("blockTime") or 0) < SINCE): break
    before = r[-1]["signature"]
sigs = [s for s in sigs if SINCE <= (s.get("blockTime") or 0) < UNTIL and s.get("err") is None]
def gt(sig): return rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
with cf.ThreadPoolExecutor(8) as ex: txs = list(ex.map(lambda s: (s, gt(s["signature"])), sigs))
mine = {}
for s, t in txs:
    if not t: continue
    for e in events(t):
        if e["kind"] == "T" and e["user"] == W:
            mine.setdefault(e["mint"], []).append(dict(e, sig=s["signature"], slot=t["slot"], bt=t.get("blockTime"), fee=t["meta"]["fee"]))
trips = {m: v for m, v in mine.items() if any(x["buy"] for x in v) and any(not x["buy"] for x in v)}
print(f"{W[:8]}: {len(sigs)} ok txs in window, {len(trips)} round trips", flush=True)
blk_cache = {}
def block_sigs(slot):
    if slot not in blk_cache:
        b = rpc("getBlock", [slot, {"transactionDetails": "signatures", "rewards": False, "maxSupportedTransactionVersion": 1}])
        blk_cache[slot] = (b or {}).get("signatures") or []
    return blk_cache[slot]
res = []
for m, ours in sorted(trips.items(), key=lambda kv: min(x["slot"] for x in kv[1])):
    ours.sort(key=lambda x: x["slot"])
    last = max(x["slot"] for x in ours) + 3
    # 2) every tx touching the mint, newest first, back past the create
    ms, before = [], None
    while True:
        p = {"limit": 1000}
        if before: p["before"] = before
        r = rpc("getSignaturesForAddress", [m, p]) or []
        ms += r
        if len(r) < 1000 or min(x["slot"] for x in r) < min(x["slot"] for x in ours) - 5: break
        before = r[-1]["signature"]
    ms = [x for x in ms if x["slot"] <= last]
    with cf.ThreadPoolExecutor(8) as ex: mt = list(ex.map(lambda s: (s, gt(s["signature"])), ms))
    rows, cslot = [], None
    for s, t in mt:
        if not t: continue
        ev = events(t)
        if any(e["kind"] == "C" for e in ev): cslot = t["slot"] if cslot is None else min(cslot, t["slot"])
        for j, e in enumerate(e for e in ev if e["kind"] == "T" and e["mint"] == m):
            rows.append(dict(e, sig=s["signature"], slot=t["slot"], err=t["meta"].get("err") is not None, j=j,
                             signer=t["transaction"]["message"]["accountKeys"][0] if isinstance(t["transaction"]["message"]["accountKeys"][0], str) else None))
    failed = [dict(sig=s["signature"], slot=s["slot"]) for s, t in mt if s.get("err") is not None]
    cslot = cslot if cslot is not None else min(x["slot"] for x in rows)
    for r in rows + failed:
        bs = block_sigs(r["slot"])
        r["pos"] = bs.index(r["sig"]) if r["sig"] in bs else -1
        r["blk_n"] = len(bs)
    for f in failed:
        t = next((t for s, t in mt if s["signature"] == f["sig"]), None)
        if t: f["signer"] = t["transaction"]["message"]["accountKeys"][0]; f["logs_err"] = next((l for l in (t["meta"].get("logMessages") or []) if "Error" in l or "error" in l), "")[:90]
    rows.sort(key=lambda r: (r["slot"], r["pos"], r["j"]))
    failed.sort(key=lambda r: (r["slot"], r["pos"]))
    res.append(dict(mint=m, create_slot=cslot, ours=ours, rows=rows, failed=failed))
    # 3) print the tape
    kb = next(i for i, r in enumerate(rows) if r["user"] == W and r["buy"])
    ks = max(i for i, r in enumerate(rows) if r["user"] == W and not r["buy"])
    p_buy = rows[kb]["vsol"] / rows[kb]["vtok"]
    print(f"\n=== {m}  create slot {cslot}  our buy {rows[kb]['sol']/1e9:.3f} SOL at slot S+{rows[kb]['slot']-cslot} pos {rows[kb]['pos']}/{rows[kb]['blk_n']}")
    for i, r in enumerate(rows):
        if r["slot"] > rows[ks]["slot"] + 2: break
        tag = "  <== OUR BUY" if i == kb else ("  <== OUR SELL" if r["user"] == W and not r["buy"] else "")
        win = " *" if kb < i < ks and r["user"] != W else "  "
        print(f"  {win}S+{r['slot']-cslot} pos {r['pos']:4d}  {'BUY ' if r['buy'] else 'SELL'} {r['sol']/1e9:8.4f} SOL  {r['user'][:8]}  price x{(r['vsol']/r['vtok'])/p_buy:6.3f} vs our buy{tag}")
    btw = [r for r in rows[kb + 1:ks] if r["user"] != W]
    fbtw = [f for f in failed if (rows[kb]["slot"], rows[kb]["pos"]) < (f["slot"], f["pos"]) < (rows[ks]["slot"], rows[ks]["pos"])]
    print(f"  between our buy and our last sell: {sum(1 for r in btw if r['buy'])} outside buys ({sum(r['sol'] for r in btw if r['buy'])/1e9:.3f} SOL), "
          f"{sum(1 for r in btw if not r['buy'])} outside sells ({sum(r['sol'] for r in btw if not r['buy'])/1e9:.3f} SOL), {len(fbtw)} failed txs on the mint; "
          f"slots S+{rows[kb]['slot']-cslot}..S+{rows[ks]['slot']-cslot}")
if OUT: json.dump(res, open(OUT, "w"))
