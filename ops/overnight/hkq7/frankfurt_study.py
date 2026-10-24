#!/usr/bin/env python3
# WHY did buys revert on nearby (Frankfurt) leaders? READ-ONLY study of the 102 PROD dip fires (runs 1-7, 2g wallet):
#   dump tx and our tx: slot + index in block; leader of each slot (identity, client, city, host); same slot or not
#   engine timing: feed lag, reaction, fire -> seen back, landing delay on the leader's PoH clock (dump -> our tx)
#   collector tape between the dump and our tx: buys ahead of us (count, SOL, who), price move vs the post-dump price (guard 1.05)
import os, sys, json, time, urllib.request, collections, statistics, concurrent.futures as cf
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p):
    for i in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=90))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.6 * (i + 1))
D = "/home/moiz/sniper/ops/overnight/hkq7"
R = json.load(open(f"{D}/replay_reverted.json")); T = json.load(open(f"{D}/2g_timing.json"))
NAMES = {"HkQ7hMjy": "HkQ7", "haqqiUUX": "haqq", "DYXDDrZC": "DYX"}
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
BLK = {}
def block(slot):
    if slot not in BLK:
        b = rpc("getBlock", [slot, {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 0, "rewards": False}])
        BLK[slot] = b["signatures"] if b else []
    return BLK[slot]
def where(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
    if not t: return None
    s = block(t["slot"]); return (t["slot"], s.index(sig) if sig in s else None, len(s))
for r in R:
    f = T.get("_fire_" + r["sig"], {}); r["dump_sig"] = f.get("dump_sig"); r["tim"] = T.get(r["sig"]); r["paths"] = f.get("paths")
with cf.ThreadPoolExecutor(8) as ex:
    DW = list(ex.map(lambda r: where(r["dump_sig"]) if r["dump_sig"] else None, R))
    BW = list(ex.map(lambda r: where(r["sig"]), R))
sched_cache = {}
es = rpc("getEpochSchedule", [])
def leader_of(slot):
    ep = (slot - es["firstNormalSlot"]) // es["slotsPerEpoch"]; first = es["firstNormalSlot"] + ep * es["slotsPerEpoch"]
    if ep not in sched_cache:
        s = rpc("getLeaderSchedule", [slot]) or {}; sched_cache[ep] = {first + i: k for k, v in s.items() for i in v}
    return sched_cache[ep].get(slot)
nodes = {n["pubkey"]: n for n in rpc("getClusterNodes", [])}
def client(c):
    c = c or ""
    return "BAM" if "Bam" in c or "BAM" in c else ("Harmonic" if "Harmonic" in c else ("Jito" if c == "JitoLabs" else ("Firedancer" if "dancer" in c.lower() else (c or "?"))))
ips = {}
for r, dw, bw in zip(R, DW, BW):
    r["dump_w"], r["buy_w"] = dw, bw
    r["dump_leader"] = leader_of(dw[0]) if dw else None; r["buy_leader"] = leader_of(bw[0]) if bw else None
    for k in ("dump_leader", "buy_leader"):
        n = nodes.get(r[k] or "") or {}; a = n.get("tpu") or n.get("gossip") or ""
        if a: ips[r[k]] = a.rsplit(":", 1)[0]
geo = {}; u = sorted(set(ips.values()))
for i in range(0, len(u), 100):
    for g in json.load(urllib.request.urlopen(urllib.request.Request("http://ip-api.com/batch?fields=query,city,org", data=json.dumps(u[i:i + 100]).encode(), headers={"content-type": "application/json"}), timeout=60)): geo[g["query"]] = g
def place(ident):
    g = geo.get(ips.get(ident), {}); c = (g.get("city") or "?")
    if c.startswith("Frankfurt") and c != "Frankfurt (Oder)" or c in ("Fechenheim", "Rödelheim"): c = "Frankfurt area"
    return c, (g.get("org") or "?")[:24], client((nodes.get(ident or "") or {}).get("clientId") or (nodes.get(ident or "") or {}).get("version"))
L = rp.load_launches(); byb = collections.defaultdict(set)
for r in R:
    if r["mint"] in L: byb[(L[r["mint"]]["run"], rp.bucket(r["mint"]))].add(r["mint"])
tapes = {}
for k, ms in byb.items(): tapes.update(rp.read_bucket(k[0], k[1], ms))
rows = []
for r in R:
    dw, bw = r["dump_w"], r["buy_w"]
    if not dw or not bw or dw[1] is None or bw[1] is None: continue
    tr = tapes.get(r["mint"], [])
    kd = next((k for k, t in enumerate(tr) if t["s"] == dw[0] and t["i"] == dw[1] and not t["buy"]), None)
    ahead = [t for t in tr if (t["s"], t["i"]) > (dw[0], dw[1]) and (t["s"], t["i"]) < (bw[0], bw[1])]
    p0 = (tr[kd]["vsol"] / tr[kd]["vtok"]) if kd is not None else None
    pb = None
    if ahead: pb = ahead[-1]["vsol"] / ahead[-1]["vtok"]
    move = (pb / p0) if (p0 and pb) else (1.0 if p0 else None)
    tm = r["tim"] or {}
    dc, do, dcl = place(r["dump_leader"]); bc, bo, bcl = place(r["buy_leader"])
    who = collections.Counter(NAMES.get(t["user"][:8], "cohort" if t["user"] in COH else "other") for t in ahead if t["buy"])
    rows.append(dict(sig=r["sig"], run=r["run"], reverted=r["result"] == "buy_failed", slots_late=bw[0] - dw[0], dump_pos=dw[1] / dw[2], buy_pos=bw[1] / bw[2],
                     same_leader=r["dump_leader"] == r["buy_leader"], dump_city=dc, dump_org=do, dump_client=dcl, buy_city=bc, buy_org=bo, buy_client=bcl,
                     n_ahead_buys=sum(1 for t in ahead if t["buy"]), sol_ahead=sum(t["sol"] for t in ahead if t["buy"]) / 1e9,
                     sells_ahead=sum(1 for t in ahead if not t["buy"]), move=move, who=dict(who), land_ms=tm.get("land_ms_poh"), reaction=tm.get("reaction_ms"),
                     feed_lag=tm.get("exec_lag_ms"), seen_ms=tm.get("fire_to_seen_ms"), dump_ms=(tm.get("dump_poh") or [None, None])[1], paths=r["paths"], route=r.get("route")))
json.dump(rows, open(f"{D}/frankfurt_study.json", "w"), default=str)
med = lambda v: statistics.median(v) if v else float("nan")
def summ(nm, v):
    if not v: return
    lm = [x["land_ms"] for x in v if x["land_ms"] is not None]
    print(f"  {nm:34s} n {len(v):3d} | reverted {sum(x['reverted'] for x in v) / len(v):4.0%} | same slot as dump {sum(1 for x in v if x['slots_late'] == 0) / len(v):4.0%} | "
          f"land delay (leader clock) med {med(lm):6.1f} ms | dump at {med([x['dump_ms'] for x in v if x['dump_ms'] is not None]):5.0f} ms into its slot | "
          f"buys ahead med {med([x['n_ahead_buys'] for x in v]):.0f} ({med([x['sol_ahead'] for x in v]):.2f} SOL) | price move med {med([x['move'] for x in v if x['move']]):.3f}")
print("ALL fires"); summ("reverted", [x for x in rows if x["reverted"]]); summ("filled", [x for x in rows if not x["reverted"]])
print("\nby where OUR tx landed (leader of our slot):")
for c in ("Frankfurt area", "Amsterdam", "London"):
    for rv in (True, False): summ(f"{c} {'reverted' if rv else 'filled'}", [x for x in rows if x["buy_city"] == c and x["reverted"] == rv])
fr = [x for x in rows if x["buy_city"] == "Frankfurt area"]
print("\nFrankfurt-area landings by host / client (reverted / total):")
for k, v in collections.Counter((x["buy_org"], x["buy_client"]) for x in fr).most_common():
    print(f"   {k[0]:24s} {k[1]:10s} {sum(1 for x in fr if (x['buy_org'], x['buy_client']) == k and x['reverted'])} / {v}")
print("\nwho bought between the dump and us (Frankfurt-area, reverted):", sum((collections.Counter(x["who"]) for x in fr if x["reverted"]), collections.Counter()))
print("who bought between the dump and us (Frankfurt-area, filled):  ", sum((collections.Counter(x["who"]) for x in fr if not x["reverted"]), collections.Counter()))
print("\nFrankfurt-area: dump leader vs our leader same validator:", f"{sum(x['same_leader'] for x in fr)}/{len(fr)}; dump leader city:", collections.Counter(x["dump_city"] for x in fr).most_common(4))
print("reaction / feed lag / fire->seen (Frankfurt, all):", f"{med([x['reaction'] for x in fr if x['reaction']]):.1f} / {med([x['feed_lag'] for x in fr if x['feed_lag']]):.1f} / {med([x['seen_ms'] for x in fr if x['seen_ms']]):.1f} ms")
