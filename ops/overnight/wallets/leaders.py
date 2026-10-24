#!/usr/bin/env python3
# A wallet's last N landed pump trades (READ-ONLY RPC, endpoint never printed): slot, slot leader (identity + client),
# position in the block, tip service used -> where its trades land. usage: python3 -I leaders.py WALLET N
import sys, os, json, time, base64, collections, concurrent.futures as cf, urllib.request
sys.path.insert(0, "/home/moiz/sniper/ops/speedcheck")
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
W, N = sys.argv[1], int(sys.argv[2])
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238]); SYS = "11111111111111111111111111111111"
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def rpc(m, p, tries=6):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.6 * (i + 1))
def tx(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
    if not t or t["meta"]["err"] is not None: return None
    ev = None
    for l in t["meta"].get("logMessages") or []:
        if l.startswith("Program data: "):
            x = l[14:].split()[0]; x += "=" * (-len(x) % 4)
            try: raw = base64.b64decode(x)
            except Exception: continue
            if raw[:8] == TD and len(raw) >= 113: ev = raw[56] == 1; break
    if ev is None: return None
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}; keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    tips = []
    for ix in msg["instructions"]:
        if keys[ix["programIdIndex"]] == SYS:
            d = b58dec(ix["data"])
            if len(d) >= 12 and int.from_bytes(d[:4], "little") == 2 and keys[ix["accounts"][1]] in TIP: tips.append(TIP[keys[ix["accounts"][1]]])
    return dict(sig=sig, slot=t["slot"], bt=t.get("blockTime"), buy=ev, tips=tips)
sigs = []; before = None
while len(sigs) < 3 * N:
    page = rpc("getSignaturesForAddress", [W, {"limit": 1000, **({"before": before} if before else {})}]) or []
    if not page: break
    sigs += [p["signature"] for p in page if p.get("err") is None]; before = page[-1]["signature"]
trades = []
with cf.ThreadPoolExecutor(16) as ex:
    for r in ex.map(tx, sigs[:3 * N]):
        if r: trades.append(r)
trades = sorted(trades, key=lambda r: -r["slot"])[:N]
def pos(slot, sig):
    b = rpc("getBlock", [slot, {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 0, "rewards": False}])
    if not b: return None
    s = b["signatures"]; return (s.index(sig), len(s)) if sig in s else None
with cf.ThreadPoolExecutor(12) as ex:
    P = list(ex.map(lambda r: pos(r["slot"], r["sig"]), trades))
nodes = {n["pubkey"]: (n.get("clientId") or "", n.get("version") or "") for n in (rpc("getClusterNodes", []) or [])}
LEAD = {}
def leader(slot):
    ep_first = rpc("getEpochSchedule", []) if "sched" not in LEAD else LEAD["sched"]; LEAD["sched"] = ep_first
    spe = ep_first["slotsPerEpoch"]; fn = ep_first["firstNormalSlot"]; ep = (slot - fn) // spe; first = fn + ep * spe
    if ep not in LEAD:
        s = rpc("getLeaderSchedule", [slot]) or {}; LEAD[ep] = {first + i: ident for ident, idxs in s.items() for i in idxs}
    return LEAD[ep].get(slot)
def client(c, ver):
    if "Bam" in c or "BAM" in c: return "BAM (Jito)"
    if "Harmonic" in c: return "Harmonic"
    if c == "JitoLabs": return "Jito-Agave"
    if "dancer" in c.lower(): return "Firedancer"
    if c == "Agave": return "Agave"
    return c or "unknown"
rows = []
for r, p in zip(trades, P):
    ident = leader(r["slot"]); c, v = nodes.get(ident, ("", ""))
    rows.append(dict(r, leader=ident, client=client(c, v), idx=p[0] if p else None, size=p[1] if p else None))
json.dump(rows, open(f"/home/moiz/sniper/ops/overnight/wallets/leaders_{W[:8]}.json", "w"))
n = len(rows); t0 = time.strftime('%m-%d %H:%M', time.gmtime(rows[-1]['bt'] + 18000)); t1 = time.strftime('%m-%d %H:%M', time.gmtime(rows[0]['bt'] + 18000))
print(f"{W[:8]}: last {n} landed pump trades ({sum(r['buy'] for r in rows)} buys / {n - sum(r['buy'] for r in rows)} sells), {t0} -> {t1} PKT")
cc = collections.Counter(r["client"] for r in rows); print("by leader client:", ", ".join(f"{k} {v} ({v / n:.0%})" for k, v in cc.most_common()))
lc = collections.Counter(r["leader"] for r in rows); print("top leaders (validator identity):")
for k, v in lc.most_common(10): print(f"   {k}  {v} trades ({v / n:.0%})  client {client(*nodes.get(k, ('', '')))}")
fr = [r["idx"] / r["size"] for r in rows if r["idx"] is not None]
b = collections.Counter(min(4, int(x * 5)) for x in fr); print("position in block (0 = top):", ", ".join(f"{i * 20}-{i * 20 + 20}% {b[i]} ({b[i] / len(fr):.0%})" for i in range(5)))
for cl in cc:
    v = [r["idx"] / r["size"] for r in rows if r["client"] == cl and r["idx"] is not None]
    if v: print(f"   {cl}: median position {sorted(v)[len(v) // 2]:.0%} of the block (n {len(v)})")
tc = collections.Counter("+".join(sorted(set(r["tips"]))) or "no tip" for r in rows); print("tip / landing service:", ", ".join(f"{k} {v}" for k, v in tc.most_common(6)))
for cl in cc:
    t2 = collections.Counter("+".join(sorted(set(r["tips"]))) or "no tip" for r in rows if r["client"] == cl); print(f"   on {cl}: " + ", ".join(f"{k} {v}" for k, v in t2.most_common(3)))
