# Bundle check (R3 raw txs) + followers after the group's buy + who funds / receives SOL from the 4 wallets (RPC, read-only).
import json, gzip, glob, os, collections, statistics, urllib.request, time
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p):
    for i in range(5):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60)).get("result")
        except Exception: time.sleep(1 + i)
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
P = json.load(open("grp4/grp4_tokens.json")); G = ["BNnN2MqfWLvgThYBsv6v8JQaYZXYKYahC5YCy27Ct1cX", "2pLugeBDKkFxaD2JKxSifNXoegYQyVpVoFikc6SEdqdv", "3GzBLpxTWWTPWwBYQ8Jgrz5XLUCg9aY6HiB3GEBUBAv6", "7PteyyyR4pvnCUr48bqQN7mxMAuQV4amBkYFNWjohoms"]
want = {b["sig"]: (u, x["m"]) for x in P if x["run"] == "R3" for u, b in x["buys"].items()}
RAW = {}
for f in sorted(glob.glob("/home/moiz/sniper-data/collect/run_20261023_1426/txs/*.jsonl.gz")):
    for line in gzip.open(f, "rt"):
        if any(g[:12] in line for g in G):
            r = json.loads(line)
            if r["sig"] in want: RAW[r["sig"]] = r
print(f"R3 group buys found in raw txs: {len(RAW)} of {len(want)}")
pat = collections.Counter()
for x in P:
    if x["run"] != "R3" or len(x["buys"]) < 4: continue
    row = []
    for u in G:
        r = RAW.get(x["buys"].get(u, {}).get("sig"))
        if not r: row.append("?"); continue
        tips = [(TIP.get(a, "other"), v) for a, v in (r.get("tips") or [])]
        row.append(f"{u[:4]}:{'+'.join(f'{s}{v/1e9:.4f}' for s, v in tips) or 'notip'}/cup{r.get('cup')}")
    pat[" | ".join(row)] += 1
print("per-token tip / CU price pattern across the 4 members (in slot order):")
for k, n in pat.most_common(8): print(f"  {n:2d}x  {k}")
progs = collections.Counter(tuple(sorted(set(r.get("progs") or []) - {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111"})) for r in RAW.values())
print("programs:", progs.most_common(3))
fees = [int(r.get("fee") or 0) for r in RAW.values()]; culs = [int(r.get("cul") or 0) for r in RAW.values()]; cus = [int(r.get("cu") or 0) for r in RAW.values()]
print(f"tx fee paid per buy: median {statistics.median(fees)/1e9:.5f} SOL (max {max(fees)/1e9:.5f}) | CU limit median {statistics.median(culs)} | CU used median {statistics.median(cus)}")
print("sample buy sigs:", list(RAW)[:2])
# followers: buyers in the 5 s / 30 s after the group's buy
import os as _o, sys
_o.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); _o.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); _o.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core"); import rp
L = rp.load_launches(); byb = collections.defaultdict(set)
for x in P: byb[(x["run"], rp.bucket(x["m"]))].add(x["m"])
f5 = []; f30 = []; s5 = []
for k, ms in byb.items():
    for m, tr in rp.read_bucket(k[0], k[1], ms).items():
        x = next(y for y in P if y["m"] == m); s0 = min(b["s"] for b in x["buys"].values())
        aft = [t for t in tr if t["s"] > s0 and t["user"] not in G]
        f5.append(sum(t["sol"] for t in aft if t["buy"] and (t["s"] - s0) * 0.212 <= 5) / 1e9); f30.append(sum(t["sol"] for t in aft if t["buy"] and (t["s"] - s0) * 0.212 <= 30) / 1e9)
        s5.append(len({t["user"] for t in aft if t["buy"] and (t["s"] - s0) * 0.212 <= 5}))
print(f"followers after the group's buy: buyers in 5 s median {statistics.median(s5)}, SOL bought by others in 5 s median {statistics.median(f5):.2f}, in 30 s {statistics.median(f30):.2f} (group puts in ~6 SOL)")
# funding: counterparties of plain SOL transfers in the last 24 h ledgers
for u in G:
    try: R = json.load(open(f"ledw_{u[:8]}.json"))
    except Exception: R = []
    oth = [r for r in R if r["ok"] and not r["evs"] and abs(r["nat"]) > 5e7]
    cps = collections.Counter()
    for r in oth[:30]:
        t = rpc("getTransaction", [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
        if not t: continue
        k = t["transaction"]["message"]["accountKeys"]; pre, post = t["meta"]["preBalances"], t["meta"]["postBalances"]
        for i, a in enumerate(k):
            if a != u and abs(post[i] - pre[i]) > 4e7: cps[(a, "in from" if r["nat"] > 0 else "out to")] += (post[i] - pre[i]) / 1e9
    print(f"{u[:8]} transfers: " + ", ".join(f"{d} {a[:8]} {v:+.2f}" for (a, d), v in sorted(cps.items(), key=lambda kv: -abs(kv[1]))[:5]))
