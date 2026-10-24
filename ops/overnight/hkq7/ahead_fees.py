#!/usr/bin/env python3
# READ-ONLY: for our Frankfurt-area dip fires, compare what the buyers who landed BETWEEN the dump and us paid (priority fee, tips,
# landing service) with what we paid, and where they sat in the block. Ordering inside the leader's block is set by these.
import os, sys, json, time, urllib.request, collections, statistics, concurrent.futures as cf
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json")); SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; BI = {c: i for i, c in enumerate(B58)}
def dec(s):
    n = 0
    for c in s: n = n * 58 + BI[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def rpc(m, p):
    for i in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=90))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.6 * (i + 1))
def fees(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
    if not t: return None
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}; keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    cup = cul = None; tips = []
    for ix in msg["instructions"]:
        p = keys[ix["programIdIndex"]]; d = dec(ix["data"])
        if p == CB and d:
            if d[0] == 3: cup = int.from_bytes(d[1:9], "little")
            elif d[0] == 2: cul = int.from_bytes(d[1:5], "little")
        elif p == SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2 and keys[ix["accounts"][1]] in TIP: tips.append((TIP[keys[ix["accounts"][1]]], int.from_bytes(d[4:12], "little")))
    prio = (cup or 0) * (cul or 200000) / 1e15
    return dict(prio=prio, tip=sum(x for _, x in tips) / 1e9, svc="+".join(sorted({s for s, _ in tips})) or "none", signer=keys[0])
S = [x for x in json.load(open("/home/moiz/sniper/ops/overnight/hkq7/frankfurt_study.json")) if x["buy_city"] == "Frankfurt area"]
R = {r["sig"]: r for r in json.load(open("/home/moiz/sniper/ops/overnight/hkq7/replay_reverted.json"))}
L = rp.load_launches(); byb = collections.defaultdict(set)
for x in S:
    m = R[x["sig"]]["mint"]
    if m in L: byb[(L[m]["run"], rp.bucket(m))].add(m)
tapes = {}
for k, ms in byb.items(): tapes.update(rp.read_bucket(k[0], k[1], ms))
T = json.load(open("/home/moiz/sniper/ops/overnight/hkq7/2g_timing.json"))
jobs = []
for x in S:
    r = R[x["sig"]]; tr = tapes.get(r["mint"], []); dsig = T.get("_fire_" + x["sig"], {}).get("dump_sig")
    d = next(((t["s"], t["i"]) for t in tr if t["sig"] == dsig), None); b = (r["slot"], r["idx"])
    if not d: continue
    ahead = [t["sig"] for t in tr if d < (t["s"], t["i"]) < b and t["buy"]]
    jobs.append((x, x["sig"], ahead))
allsig = sorted({s for _, me, a in jobs for s in [me] + a})
with cf.ThreadPoolExecutor(10) as ex: F = dict(zip(allsig, ex.map(fees, allsig)))
med = lambda v: statistics.median(v) if v else float("nan")
for rv in (True, False):
    v = [j for j in jobs if j[0]["reverted"] == rv]
    mine = [F[me] for _, me, _ in v if F.get(me)]; theirs = [F[s] for _, _, a in v for s in a if F.get(s)]
    print(f"\nFrankfurt-area {'REVERTED' if rv else 'FILLED'} ({len(v)} fires): buyers ahead of us {len(theirs)}")
    print(f"   OUR tx:       priority med {med([m['prio'] for m in mine]):.5f} SOL | tip med {med([m['tip'] for m in mine]):.4f} SOL | services {collections.Counter(m['svc'] for m in mine).most_common(3)}")
    if theirs:
        print(f"   AHEAD of us:  priority med {med([m['prio'] for m in theirs]):.5f} SOL | tip med {med([m['tip'] for m in theirs]):.4f} SOL | services {collections.Counter(m['svc'] for m in theirs).most_common(5)}")
        print(f"   paid more than us (priority + tip): {sum(1 for _, me, a in v for s in a if F.get(s) and F.get(me) and F[s]['prio'] + F[s]['tip'] > F[me]['prio'] + F[me]['tip'])} of {len(theirs)}")
