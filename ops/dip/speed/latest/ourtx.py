# Our 240 fired buy txs from chain: number of tip transfers (hot write-locked accounts), writable accounts, CU limit/price, size -> vs fire->seen
import json, os, urllib.request, time, collections, statistics, concurrent.futures as cf, base64
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip(); TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
def rpc(m, p):
    for i in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(), headers={"content-type":"application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(1.5 * (i + 1))
R = json.load(open("latest/rootcause.json")); T = {r["sig"]: r for r in json.load(open("latest/timeline.json"))}
sig_of = {}
for r in json.load(open("latest/timeline.json")): sig_of[(r["mint"], r["t0"])] = r["sig"]
def one(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: return sig, None
    m = t["transaction"]["message"]; k = m["accountKeys"]; h = m["header"]
    nw = len(k) - h["numReadonlySignedAccounts"] - h["numReadonlyUnsignedAccounts"]
    tips = [TIP[k[i["accounts"][1]]] for i in m["instructions"] if k[i["programIdIndex"]] == "11111111111111111111111111111111" and len(i["accounts"]) > 1 and k[i["accounts"][1]] in TIP]
    return sig, dict(tips=tips, n_writable=nw, n_keys=len(k), cu=t["meta"].get("computeUnitsConsumed"), slot=t["slot"], err=t["meta"]["err"] is not None)
sigs = [r["sig"] for r in T.values() if r["fire_to_seen"] is not None]
with cf.ThreadPoolExecutor(6) as ex: D = dict(ex.map(one, sigs))
json.dump(D, open("latest/ourtx.json", "w"))
med = lambda v: statistics.median(v) if v else float("nan")
rows = []
for sig, d in D.items():
    if not d: continue
    r = T[sig]; same = r["ours_slot"] == 0 if r["ours_slot"] is not None else None
    rows.append((r, d))
print("our buys read:", len(rows), "| tips per tx:", collections.Counter(len(d["tips"]) for r, d in rows).most_common(), "| tip sets:", collections.Counter("+".join(sorted(d["tips"])) for r, d in rows).most_common(6))
print("\nfire->seen by number of tips in OUR tx, per leader client (all our buys incl. reverted):")
for cl in sorted({r["client"] for r, d in rows}):
    cells = []
    for k in sorted({len(d["tips"]) for r, d in rows}):
        v = [r["fire_to_seen"] for r, d in rows if r["client"] == cl and len(d["tips"]) == k]
        if v: cells.append(f"{k} tips: n={len(v):3d} med {med(v):5.1f}")
    print(f"   {cl:18s} | " + " | ".join(cells))
