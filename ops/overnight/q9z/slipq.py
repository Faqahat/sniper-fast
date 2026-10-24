#!/usr/bin/env python3
# READ-ONLY: 9qz7cW's slippage limit on its pump.fun buys. Decodes the args of its direct pump.fun buy instruction
# (buy_exact_quote_in: a1 = SOL/quote spent, a2 = min tokens out) and compares a2 with the tokens it received
# (tolerance = received / min_out - 1). Sources: already fetched txs (txc/) + its snipe buys in the replay window
# (fetched now, owner's RPC, paced). -> slip_q9z.json {sig: {kind, a1, a2, tok, tol}} and slip_q9z.jsonl in the
# format rp.sim(slip=...) expects (kind "sol": spend a1, needs >= a2 tokens).
import sys, os, json, gzip, glob, base64, collections, statistics
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
os.environ.setdefault("Q9Z_RATE", "0.7")
from rpcq import rpc
W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"; PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def b58d(s):
    n = 0
    for ch in s: n = n * 58 + B58.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw
def decode(tx):
    m = tx["transaction"]["message"]; meta = tx["meta"]
    if meta.get("err") is not None: return None
    ev = None
    for l in meta.get("logMessages") or []:
        if not l.startswith("Program data: "): continue
        s = l[14:].strip(); s += "=" * (-len(s) % 4)
        try: raw = base64.b64decode(s)
        except Exception: continue
        if raw[:8] == TD and len(raw) >= 129 and b58(raw[57:89]) == W and raw[56] == 1:
            ev = dict(mint=b58(raw[8:40]), sol=int.from_bytes(raw[40:48], "little"), tok=int.from_bytes(raw[48:56], "little"))
    if not ev: return None
    for ix in m["instructions"]:
        if ix.get("programId") != PUMP or not ix.get("data"): continue
        d = b58d(ix["data"])
        if len(d) < 24: continue
        a1 = int.from_bytes(d[8:16], "little"); a2 = int.from_bytes(d[16:24], "little")
        return dict(disc=d[:8].hex(), a1=a1, a2=a2, tok=ev["tok"], sol=ev["sol"], mint=ev["mint"], tol=round(ev["tok"] / a2 - 1, 5) if a2 else None)
    return dict(disc="router-or-cpi", tok=ev["tok"], sol=ev["sol"], mint=ev["mint"])
out = {}
for f in glob.glob(os.path.join(HERE, "txc", "*.json.gz")):
    try: tx = json.load(gzip.open(f, "rt"))
    except Exception: continue
    d = decode(tx)
    if d: out[os.path.basename(f)[:-8]] = d
print("decoded from txc:", len(out), flush=True)
PL = json.load(open(os.path.join(HERE, "perlaunch_q9z.json")))
want = [r["buy_sig"] for r in PL.values() if r.get("buy_sig") and r["run"] == "R2" and r["beh"] == "snipe" and r["buy_sig"] not in out]
print("fetching its R2 snipe buys:", len(want), flush=True)
for s in want:
    tx = rpc("getTransaction", [s, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
    if tx:
        d = decode(tx)
        if d: out[s] = d
json.dump(out, open(os.path.join(HERE, "slip_q9z.json"), "w"))
with open(os.path.join(HERE, "slip_q9z.jsonl"), "w") as fo:
    for s, d in out.items():
        if d.get("a2"): fo.write(json.dumps(dict(sig=s, mint=d["mint"], kind="sol", a1=d["a1"], a2=d["a2"], sol=d["sol"], tok=d["tok"])) + "\n")
tol = [d["tol"] for d in out.values() if d.get("tol") is not None]
print("discriminators", collections.Counter(d["disc"] for d in out.values()).most_common(4))
xs = sorted(tol); qs = [xs[int(p * (len(xs) - 1))] for p in (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)] if xs else None
print("tolerance (tokens received / min tokens - 1), n", len(tol), "quantiles 5/10/25/50/75/90/95%:", qs)
