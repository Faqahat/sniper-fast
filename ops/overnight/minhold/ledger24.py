#!/usr/bin/env python3
# HkQ7hMjy ground truth, last N hours (READ-ONLY RPC, owner's endpoint never printed): every tx it signed, failed ones too.
# Net SOL = the wallet's own balance change per tx (includes pump fees, priority fees, tips, rent). Plus counts of buys, sells,
# failed attempts and what they cost, round trips (FIFO per token), holds, returns, and SOL per hour of the day (PKT).
# usage: python3 -I ledger24.py HOURS [WALLET]
import sys, os, json, time, base64, collections, statistics, urllib.request, concurrent.futures as cf
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
W = sys.argv[2] if len(sys.argv) > 2 else "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ"; TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def rpc(m, p, tries=6):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.6 * (i + 1))
HOURS = float(sys.argv[1]); t_end = time.time(); t_start = t_end - HOURS * 3600
sigs = []; before = None
while True:
    page = rpc("getSignaturesForAddress", [W, {"limit": 1000, **({"before": before} if before else {})}]) or []
    if not page: break
    sigs += [p for p in page if (p.get("blockTime") or 0) >= t_start]
    before = page[-1]["signature"]
    if (page[-1].get("blockTime") or 0) < t_start or len(page) < 1000: break
print(f"txs in the last {HOURS:.0f} h: {len(sigs)}", flush=True)
def one(p):
    t = rpc("getTransaction", [p["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: return None
    keys = t["transaction"]["message"]["accountKeys"]
    i = keys.index(W) if W in keys else None
    dsol = (t["meta"]["postBalances"][i] - t["meta"]["preBalances"][i]) if i is not None else 0
    evs = []
    for l in t["meta"].get("logMessages") or []:
        if l.startswith("Program data: "):
            x = l[14:].split()[0]; x += "=" * (-len(x) % 4)
            try: raw = base64.b64decode(x)
            except Exception: continue
            if raw[:8] == TD and len(raw) >= 113 and b58enc(raw[57:89]) == W:
                evs.append(dict(mint=b58enc(raw[8:40]), sol=int.from_bytes(raw[40:48], "little"), tok=int.from_bytes(raw[48:56], "little"), buy=raw[56] == 1,
                                vsol=int.from_bytes(raw[97:105], "little"), vtok=int.from_bytes(raw[105:113], "little")))
    return dict(sig=p["signature"], slot=t["slot"], bt=t.get("blockTime"), ok=t["meta"]["err"] is None, fee=t["meta"]["fee"], dsol=dsol, evs=evs, signer=keys[0] == W)
rows = []
with cf.ThreadPoolExecutor(16) as ex:
    for r in ex.map(one, sigs):
        if r: rows.append(r)
json.dump(rows, open(f"/home/moiz/sniper/ops/overnight/hkq7/ledger24{'' if W.startswith('HkQ7') else '_' + W[:8]}.json", "w"))
rows.sort(key=lambda r: (r["slot"]))
span_h = (max(r["bt"] for r in rows) - min(r["bt"] for r in rows)) / 3600
ok = [r for r in rows if r["ok"]]; bad = [r for r in rows if not r["ok"] and r["signer"]]
buys = [(r, e) for r in ok for e in r["evs"] if e["buy"]]; sells = [(r, e) for r in ok for e in r["evs"] if not e["buy"]]
net = sum(r["dsol"] for r in rows) / 1e9
print(f"span {span_h:.1f} h | landed buys {len(buys)} ({len(buys) / span_h:.1f}/h) | sells {len(sells)} | failed attempts it paid for {len(bad)} ({len(bad) / span_h:.1f}/h), their fees {sum(r['fee'] for r in bad) / 1e9:.3f} SOL")
print(f"NET SOL change of the wallet over the span: {net:+.3f} SOL  ≈ {net / span_h * 24:+.1f} SOL/day (open positions at the edges not valued)")
# round trips FIFO per mint
open_ = collections.defaultdict(list); trips = []
for r in ok:
    for e in r["evs"]:
        if e["buy"]: open_[e["mint"]].append((r, e))
        elif open_[e["mint"]]:
            br, be = open_[e["mint"]].pop(0)
            trips.append(dict(hold=r["slot"] - br["slot"], gross=(e["sol"] - be["sol"]) / 1e9, ret=e["sol"] / be["sol"], buy_sol=be["sol"] / 1e9, net=(br["dsol"] + r["dsol"]) / 1e9))
if trips:
    h = [t["hold"] for t in trips]
    print(f"round trips {len(trips)} | hold slots p25 {statistics.quantiles(h, n=4)[0]:.0f} median {statistics.median(h):.0f} p75 {statistics.quantiles(h, n=4)[2]:.0f} | "
          f"win {sum(1 for t in trips if t['net'] > 0) / len(trips):.0%} | net per trip median {statistics.median(t['net'] for t in trips):+.4f} mean {statistics.mean(t['net'] for t in trips):+.4f} SOL | buy size median {statistics.median(t['buy_sol'] for t in trips):.3f}")
hrs = collections.defaultdict(float)
for r in rows: hrs[time.gmtime(r["bt"] + 18000).tm_hour] += r["dsol"] / 1e9
print("net SOL by PKT hour:", {h: round(v, 2) for h, v in sorted(hrs.items())})
