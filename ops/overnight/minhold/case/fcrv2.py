#!/usr/bin/env python3
# CASE STUDY v2 (read-only): FCRvz2Tj… is a pump curve quoted in another token (BuyV3 / BuyExactQuoteInV3; the group swaps SOL→quote first).
# Event fields used: token amount @48, is_buy @56, user @57, virtual token reserves AFTER the trade @105. Constant product: quote reserves
# = u / vtok, with u (in SOL·tokens) calibrated from the group's own buys (each paid 1.5 SOL into the swap; pump fee 1.25% assumed).
# Our buy B SOL lands 50 ms (block position) after the group's first buy; everything after is replayed (buyers keep their quote input,
# sellers their token amount). Exits: fixed holds, take-profits, and the group's own sells.
import json, gzip, glob, base64, os, time, urllib.request
M = "FCRvz2TjKMph3GpMrtoFwxf4EuNCM2KcbkY7n3Kppump"
G = {"BNnN2MqfWLvgThYBsv6v8JQaYZXYKYahC5YCy27Ct1cX": "GRP-BNnN", "2pLugeBDKkFxaD2JKxSifNXoegYQyVpVoFikc6SEdqdv": "GRP-2pLu",
     "3GzBLpxTWWTPWwBYQ8Jgrz5XLUCg9aY6HiB3GEBUBAv6": "GRP-3GzB", "7PteyyyR4pvnCUr48bqQN7mxMAuQV4amBkYFNWjohoms": "GRP-7Pte"}
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p):
    for i in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(1.5 * (i + 1))
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238]); B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
U8 = lambda raw, a: int.from_bytes(raw[a:a + 8], "little")
L = next(json.loads(l) for l in open("/home/moiz/sniper-data/collect/run_20261024_1425/launches.jsonl") if M in l)
tr = []; sdmap = {}
for f in sorted(glob.glob("/home/moiz/sniper-data/collect/run_20261024_1425/txs/*.jsonl.gz")):
    try:
        for line in gzip.open(f, "rt"):
            if M not in line: continue
            r = json.loads(line)
            if r.get("err") not in (None, "None", "null"): continue
            for j, e in enumerate(r.get("ev") or []):
                try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
                except Exception: continue
                if raw[:8] == TD and len(raw) >= 129 and b58(raw[8:40]) == M:
                    tr.append(dict(s=int(r["s"]), i=int(r["i"]), j=j, sig=r["sig"], user=b58(raw[57:89]), buy=raw[56] == 1, tok=U8(raw, 48), vtok=U8(raw, 105)))
                    sdmap[r["sig"]] = r.get("sd")
    except (EOFError, OSError): pass
tr.sort(key=lambda t: (t["s"], t["i"], t["j"]))
for k, t in enumerate(tr): t["vtok_b"] = tr[k - 1]["vtok"] if k else (t["vtok"] + t["tok"] if t["buy"] else t["vtok"] - t["tok"])
FEE = 0.0125; TX = 0.0015
# calibrate u from the group's buys: SOL into the swap pools = - (signer SOL delta) - priority fee ~0.015 (pools receive the rest)
cal = []
for t in tr:
    if t["user"] in G and t["buy"]:
        sd = dict((a, d) for a, d in sdmap[t["sig"]]); paid = -sd.get(t["user"], 0) / 1e9 - 0.0155
        cal.append(paid / (1 + FEE) / (1 / t["vtok"] - 1 / t["vtok_b"]))
u = sorted(cal)[len(cal) // 2]
print(f"trades on the curve: {len(tr)} | group buys used to calibrate: {len(cal)} | price unit u = {u:.4g}")
SZ = {}
def size(s):
    if s not in SZ:
        b = rpc("getBlock", [s, {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 1, "rewards": False}]); SZ[s] = len(b["signatures"]) if b else 450
    return SZ[s]
k0 = next(k for k, t in enumerate(tr) if t["user"] in G and t["buy"])
for t in tr:
    if 0 <= t["s"] - tr[k0]["s"] <= 300 or t is tr[k0]: size(t["s"])
def ms(t): return t["s"] * 212.0 + t["i"] / max(SZ.get(t["s"], 450), t["i"] + 1) * 212.0
t0 = ms(tr[k0]); S0 = L["slot"]
px = lambda vt: u / vt / vt                       # SOL per token (marginal)
p0 = px(tr[k0]["vtok"])
mc = lambda vt: px(vt) * 1e15 / 1e6               # rough market cap in SOL (1e9 tokens supply x 1e6 decimals)
qin = lambda t: u * (1 / t["vtok"] - 1 / t["vtok_b"])   # quote in (SOL equivalent) for buys, out for sells
print(f"group's first buy: {G[tr[k0]['user']]} at token age {(tr[k0]['s'] - S0) * 0.212:.0f} s, market cap ≈ {mc(tr[k0]['vtok']):.0f} SOL")
print("\ntimeline (ms after the group's first buy | who | side | SOL equiv | price vs group fill):")
for t in tr[max(0, k0 - 4):k0 + 45]:
    who = G.get(t["user"], "dev" if t["user"] == L.get("creator") else t["user"][:6])
    print(f"  {ms(t) - t0:+9.0f} ms  slot+{t['s'] - tr[k0]['s']:<3d} {who:9s} {'BUY ' if t['buy'] else 'SELL'} {abs(qin(t)):7.3f}  px {px(t['vtok']) / p0:5.2f}x")
def replay(Tms, B, drop2=False):
    kf = k0
    while kf + 1 < len(tr) and ms(tr[kf + 1]) - t0 <= Tms: kf += 1
    vt = tr[kf]["vtok"]; vq = u / vt; X = B / (1 + FEE); vq2 = vq + X; vt2 = u / vq2; q = vt - vt2; vt = vt2
    entry_px = X / q; fill = max(ms(tr[kf]), t0 + Tms); fs = tr[kf]["s"]
    val = lambda vt: (u / vt - u / (vt + q)) * (1 - FEE)
    path = [(fill, val(vt))]
    for t in tr[kf + 1:]:
        if drop2 and t["buy"] and t["s"] - fs <= 2: continue
        if t["buy"]: vq = u / vt + qin(t); vt = u / vq
        else: vt = vt + t["tok"]
        path.append((ms(t), val(vt)))
    ahead = [t for t in tr[k0 + 1:kf + 1] if t["buy"]]
    return entry_px, path, fill, ahead
for B in (1.0, 1.5):
    for d2 in (False, True):
        e, path, fill, ahead = replay(50, B, d2)
        at = lambda sec: [v for m_, v in path if m_ - fill <= sec * 1000][-1]
        pk = max(path, key=lambda x: x[1])
        print(f"\nWE BUY {B} SOL at +50 ms ({'followers in the 2 slots after us dropped' if d2 else 'followers kept'}): we pay {e / p0 - 1:+.0%} vs the group | buys ahead of us after the group: {len(ahead)} ({sum(qin(t) for t in ahead):.2f} SOL)")
        print("   PnL if we sell after: " + " | ".join(f"{s}s {at(s) - B - 2 * TX:+.3f}" for s in (0.5, 1, 2, 3, 5, 10, 20, 30, 60, 120, 300)))
        print(f"   best possible: {pk[1] - B - 2 * TX:+.3f} SOL at {(pk[0] - fill) / 1000:.1f} s after our buy")
        for tp in (0.10, 0.20, 0.30, 0.50, 1.0):
            hit = next(((m_, v) for m_, v in path if v >= B * (1 + tp)), None)
            print(f"   take-profit +{int(tp * 100)}%: " + (f"hit {(hit[0] - fill) / 1000:.1f} s after our buy → {hit[1] - B - 2 * TX:+.3f} SOL" if hit else "never hit"))
        gs = [t for t in tr[k0:] if t["user"] in G and not t["buy"]]
        if gs:
            gm = ms(gs[0]); v = [x for m_, x in path if m_ <= gm + 75][-1]
            print(f"   sell 75 ms after the group's first sell ({(gm - t0) / 1000:.1f} s after its buy): {v - B - 2 * TX:+.3f} SOL")
gs = [t for t in tr[k0:] if t["user"] in G and not t["buy"]]
if gs: print(f"\ngroup sells: first at {(ms(gs[0]) - t0) / 1000:.1f} s, last at {(ms(gs[-1]) - t0) / 1000:.1f} s; price at its first sell {px(gs[0]['vtok_b']) / p0:.2f}x its fill")
