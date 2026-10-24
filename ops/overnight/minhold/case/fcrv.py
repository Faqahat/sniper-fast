#!/usr/bin/env python3
# CASE STUDY (read-only): token FCRvz2Tj… (bought by the 1.5 SOL group incl. 3GzBLpxT). Tape from the live raw recording (run_20261024_1425),
# block sizes from RPC getBlock. We buy X SOL 50 ms (block position) after the group's first buy; curve replay with our trade inserted
# (followers kept as they were = optimistic; also a variant dropping buys in the 2 slots after us). Shows the timeline and our PnL per exit.
import json, gzip, glob, base64, os, sys, time, urllib.request, collections
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
L = next(json.loads(l) for f in glob.glob("/home/moiz/sniper-data/collect/run_20261024_1425/launches.jsonl") for l in open(f) if M in l)
tr = []
for f in sorted(glob.glob("/home/moiz/sniper-data/collect/run_20261024_1425/txs/*.jsonl.gz")):
    try:
        for line in gzip.open(f, "rt"):
            if M not in line: continue
            r = json.loads(line)
            if r.get("err") not in (None, "None", "null"): continue
            for j, e in enumerate(r.get("ev") or []):
                try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
                except Exception: continue
                if raw[:8] == TD and len(raw) >= 113 and b58(raw[8:40]) == M:
                    tr.append(dict(s=int(r["s"]), i=int(r["i"]), j=j, sig=r["sig"], user=b58(raw[57:89]), buy=raw[56] == 1, sol=int.from_bytes(raw[40:48], "little"),
                                   tok=int.from_bytes(raw[48:56], "little"), vsol=int.from_bytes(raw[97:105], "little"), vtok=int.from_bytes(raw[105:113], "little"), bt=int(r.get("bt") or 0)))
    except (EOFError, OSError): pass
tr.sort(key=lambda t: (t["s"], t["i"], t["j"])); print(f"trades on the curve: {len(tr)} | launch slot {L['slot']} | creator {L.get('creator')}")
SZ = {}
def size(s):
    if s not in SZ:
        b = rpc("getBlock", [s, {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 1, "rewards": False}]); SZ[s] = len(b["signatures"]) if b else 450
    return SZ[s]
k0 = next(k for k, t in enumerate(tr) if t["user"] in G and t["buy"])
for t in tr[:k0 + 400]:
    if abs(t["s"] - tr[k0]["s"]) <= 400: size(t["s"])
def ms(t): return t["s"] * 212.0 + t["i"] / max(SZ.get(t["s"], 450), t["i"] + 1) * 212.0
t0 = ms(tr[k0]); S0 = L["slot"]
px = lambda t: t["vsol"] / t["vtok"]
FEE = 0.0125; TX = 0.0015
print(f"group first buy: {G[tr[k0]['user']]} at token age {(tr[k0]['s'] - S0) * 0.212:.1f} s, curve {tr[k0]['vsol'] / 1e9:.1f} SOL")
print("\ntimeline around the group's buy (ms after the group's first buy, who, side, SOL, curve SOL, price vs group fill):")
p0 = px(tr[k0])
for t in tr[max(0, k0 - 5):k0 + 60]:
    who = G.get(t["user"], "dev" if t["user"] == L.get("creator") else t["user"][:6])
    print(f"  {ms(t) - t0:+8.0f} ms  slot+{t['s'] - tr[k0]['s']:<3d} idx {t['i']:4d} {who:9s} {'BUY ' if t['buy'] else 'SELL'} {t['sol'] / 1e9:7.3f}  curve {t['vsol'] / 1e9:6.1f}  px {px(t) / p0:5.2f}x")
def replay(Tms, B, drop2=False):
    kf = k0
    while kf + 1 < len(tr) and ms(tr[kf + 1]) - t0 <= Tms: kf += 1
    V, Tk = tr[kf]["vsol"], tr[kf]["vtok"]; X = int(B * 1e9 / (1 + FEE)); q = Tk * X // (V + X); V += X; Tk -= q
    entry = (V - X) / (Tk + q); fill_ms = max(ms(tr[kf]), t0 + Tms); fill_s = tr[kf]["s"]
    path = [(fill_ms, (V * q / (Tk + q)) * (1 - FEE) / 1e9)]
    for t in tr[kf + 1:]:
        if drop2 and t["buy"] and t["s"] - fill_s <= 2: continue
        if t["buy"]: d = Tk * t["sol"] // (V + t["sol"]); V += t["sol"]; Tk -= d
        else: so = V * t["tok"] // (Tk + t["tok"]); V -= so; Tk += t["tok"]
        path.append((ms(t), (V * q / (Tk + q)) * (1 - FEE) / 1e9))
    return entry, path, kf, fill_ms
for B in (1.0, 1.5):
    for d2 in (False, True):
        entry, path, kf, fill = replay(50, B, d2)
        val = lambda sec: [v for m_, v in path if m_ - fill <= sec * 1000][-1]
        pk = max(path, key=lambda x: x[1])
        print(f"\nWE BUY {B} SOL at +50 ms ({'followers within 2 slots dropped' if d2 else 'followers kept'}): we pay {entry / p0 - 1:+.0%} vs the group | buys ahead of us: {sum(1 for t in tr[k0 + 1:kf + 1] if t['buy'] and t['user'] not in G)}")
        print("   PnL if we sell after: " + " | ".join(f"{s}s {val(s) - B - 2 * TX:+.3f}" for s in (0.5, 1, 2, 3, 5, 10, 20, 30, 60, 120)))
        print(f"   best possible: {pk[1] - B - 2 * TX:+.3f} SOL at {(pk[0] - fill) / 1000:.1f} s after our fill")
        for tp in (0.10, 0.20, 0.30, 0.50):
            hit = next(((m_, v) for m_, v in path if v >= B * (1 + tp)), None)
            print(f"   take-profit +{int(tp * 100)}%: " + (f"hit at {(hit[0] - fill) / 1000:.1f} s → {hit[1] - B - 2 * TX:+.3f} SOL" if hit else "never hit"))
gs = [t for t in tr[k0:] if t["user"] in G and not t["buy"]]
if gs: print(f"\ngroup's first sell at {(ms(gs[0]) - t0) / 1000:.1f} s after its buy, price {px(gs[0]) / p0:.2f}x their fill; last group sell at {(ms(gs[-1]) - t0) / 1000:.1f} s")
