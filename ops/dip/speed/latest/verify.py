#!/usr/bin/env python3
# INDEPENDENT RE-CHECK from chain (RPC): for every live fire -> dump tx slot + index (getBlock signatures), true block size, our buy slot,
# leader of the dump slot and of the slot before (= first slot of a leader's turn?), leader client. Recompute: spill rate, spill by true
# dump position in its block, by client, by turn-start; delay share from spills; and does the engine fire on the executed feed?
import json, os, time, urllib.request, collections, statistics, glob, concurrent.futures as cf
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p):
    for i in range(7):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(), headers={"content-type":"application/json"}), timeout=90))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(1.2 * (i + 1))
T = json.load(open("latest/timeline.json"))
FILES = [f"dip_r{i}.jsonl" for i in range(1, 10)] + ["latest/dip_r10.jsonl", "dip_ams_r9.jsonl", "latest/dip_ams_r10.jsonl"]
fire = {}; tim = {}
for fn in FILES:
    for l in open(fn):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("ev") == "fire": fire[r["buy_sig"]] = r
        elif r.get("ev") == "timing" and r.get("kind") == "fire": tim[r["buy_sig"]] = r
BLK = {}
def block(s):
    if s not in BLK:
        b = rpc("getBlock", [s, {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 1, "rewards": False}]); BLK[s] = b["signatures"] if b else None
    return BLK[s]
def one(r):
    f = fire[r["sig"]]; ds = f["dump_sig"]
    td = rpc("getTransaction", [ds, {"encoding": "json", "maxSupportedTransactionVersion": 1}]); to = rpc("getTransaction", [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not td or not to: return None
    S = td["slot"]; sig_d = block(S)
    if not sig_d or ds not in sig_d: return None
    return dict(sig=r["sig"], region=r["region"], fts=r["fire_to_seen"], dump_slot=S, dump_pos=sig_d.index(ds) / len(sig_d), block_n=len(sig_d), our_slot=to["slot"], our_err=to["meta"]["err"] is not None)
with cf.ThreadPoolExecutor(6) as ex: V = [x for x in ex.map(one, [r for r in T if r["fire_to_seen"] is not None and r["sig"] in fire]) if x]
es = rpc("getEpochSchedule", []); LS = {}
for s in sorted({v["dump_slot"] for v in V})[::5000] + [max(v["dump_slot"] for v in V)]:
    ep = (s - es["firstNormalSlot"]) // es["slotsPerEpoch"]; first = es["firstNormalSlot"] + ep * es["slotsPerEpoch"]
    if first not in LS: LS[first] = {first + i: k for k, v in (rpc("getLeaderSchedule", [s]) or {}).items() for i in v}
lead = {}
for d in LS.values(): lead.update(d)
nodes = {n["pubkey"]: (n.get("clientId") or "?") for n in rpc("getClusterNodes", [])}
for v in V:
    L0 = lead.get(v["dump_slot"]); v["client"] = nodes.get(L0, "?"); v["turn_start"] = lead.get(v["dump_slot"] - 1) != L0
    v["spill"] = v["our_slot"] > v["dump_slot"]; v["next_leader_differs"] = lead.get(v["dump_slot"] + 1) != L0
    t = tim.get(v["sig"], {}); f = fire[v["sig"]]
    v["fires_on_exec"] = t.get("dump_exec_rx") == f.get("t_dump_rx") if t else None
    v["exec_lag"] = t.get("exec_lag_ms")
json.dump(V, open("latest/verify.json", "w"))
med = lambda x: statistics.median(x) if x else float("nan")
sp = [v for v in V if v["spill"]]
print(f"verified fires: {len(V)} | spilled to a later slot: {len(sp)} ({len(sp)/len(V):.0%}) | fire->seen median same-slot {med([v['fts'] for v in V if not v['spill']]):.1f} ms vs spilled {med([v['fts'] for v in sp]):.1f} ms | mean all {sum(v['fts'] for v in V)/len(V):.1f}")
extra = sum(max(0, v["fts"] - 20) for v in V); print(f"share of delay above 20 ms caused by spills: {sum(max(0, v['fts'] - 20) for v in sp)/extra:.0%}")
print("spill by TRUE position of the dump in its block (from getBlock):")
for a, b in ((0, .25), (.25, .5), (.5, .75), (.75, 1.01)):
    w = [v for v in V if a <= v["dump_pos"] < b]; print(f"   {a:.0%}-{min(b,1):.0%}: n={len(w):3d} spill {sum(v['spill'] for v in w)/max(len(w),1):4.0%}")
print("spill by leader client (real schedule + gossip):")
for cl in sorted({v["client"] for v in V}):
    w = [v for v in V if v["client"] == cl]; ts = [v for v in w if v["turn_start"]]
    print(f"   {cl:18s} n={len(w):3d} spill {sum(v['spill'] for v in w)/len(w):4.0%} | first slot of the leader's turn: {sum(v['spill'] for v in ts)}/{len(ts)} | other slots: {sum(v['spill'] for v in w if not v['turn_start'])}/{len(w)-len(ts)}")
print(f"spills where the next slot belongs to ANOTHER leader: {sum(1 for v in sp if v['next_leader_differs'])}/{len(sp)}")
ex = [v for v in V if v["fires_on_exec"] is not None]
print(f"engine fired on the executed-feed time: {sum(1 for v in ex if v['fires_on_exec'])}/{len(ex)} | exec lag median {med([v['exec_lag'] for v in V if v['exec_lag'] is not None]):.2f} ms, p90 {sorted(v['exec_lag'] for v in V if v['exec_lag'] is not None)[int(len(V)*.9)]:.2f}")
