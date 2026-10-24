#!/usr/bin/env python3
# READ-ONLY: DGmspi's recent transactions (owner's Constant-K RPC, URL read from file, never printed) -> decoded pump trades
import os, json, time, base64, urllib.request, concurrent.futures as cf, sys
W = "DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3"; SINCE = float(sys.argv[1]) if len(sys.argv) > 1 else time.time() - 4 * 3600
CK = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def rpc(m, p, tries=6):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(CK, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=30))
            if "error" in r: raise RuntimeError(str(r["error"])[:200])
            return r["result"]
        except Exception as e: err = e; time.sleep(0.5 * 2 ** i)
    raise RuntimeError(f"{m}: {err}")
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
sigs, before = [], None
while True:
    p = {"limit": 1000}
    if before: p["before"] = before
    r = rpc("getSignaturesForAddress", [W, p]) or []
    sigs += [s for s in r if (s.get("blockTime") or 0) >= SINCE]
    if not r or (r[-1].get("blockTime") or 0) < SINCE or len(r) < 1000: break
    before = r[-1]["signature"]
print("sigs since", time.strftime("%H:%M", time.gmtime(SINCE)), ":", len(sigs), "(failed:", sum(1 for s in sigs if s.get("err")), ")", flush=True)
os.makedirs("txc", exist_ok=True)
def one(s):
    p = os.path.join("txc", s["signature"] + ".json")
    if os.path.exists(p): return json.load(open(p))
    t = rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if t: json.dump(t, open(p, "w"))
    return t
rows = []
with cf.ThreadPoolExecutor(8) as ex:
    for s, t in zip(sigs, ex.map(one, sigs)):
        if not t or t["meta"].get("err"): continue
        for l in t["meta"].get("logMessages") or []:
            if not l.startswith("Program data: "): continue
            d = l[14:].strip(); d += "=" * (-len(d) % 4)
            try: raw = base64.b64decode(d)
            except Exception: continue
            if raw[:8] != TD or len(raw) < 225: continue
            if b58(raw[57:89]) != W: continue
            u = lambda o: int.from_bytes(raw[o:o + 8], "little")
            rows.append(dict(sig=s["signature"], slot=t["slot"], bt=t.get("blockTime"), mint=b58(raw[8:40]), buy=raw[56] == 1, sol=u(40), tok=u(48), vsol=u(97), vtok=u(105)))
json.dump(rows, open("dg_trades.json", "w"))
import collections
c = collections.defaultdict(lambda: [0, 0])
for r in rows: c[r["mint"]][0 if r["buy"] else 1] += 1
print("pump trades:", len(rows), "tokens:", len(c))
for m, (b, s_) in sorted(c.items(), key=lambda kv: -kv[1][1])[:15]: print(f"   {m}  buys {b}  sells {s_}")
