import json, os, time, urllib.request, statistics, sys, collections
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p):
    for i in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(), headers={"content-type":"application/json"}), timeout=90))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(1.5 * (i + 1))
BC = {}
def blk(s):
    if s not in BC:
        b = rpc("getBlock", [s, {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 1, "rewards": False}]); BC[s] = b["signatures"] if b else None
    return BC[s]
med = lambda v: statistics.median(v) if v else float("nan")
def analyze(fn):
    fire = {}; tim = {}; close = {}
    for l in open(fn):
        try: r = json.loads(l)
        except Exception: continue
        e = r.get("ev")
        if e == "fire": fire[r["buy_sig"]] = r
        elif e == "timing" and r.get("kind") == "fire": tim[r["buy_sig"]] = r
        elif e == "close": close[r["dump_sig"] + r["mint"]] = r
    out = []
    for s, f in fire.items():
        t = tim.get(s, {}); c = close.get(f["dump_sig"] + f["mint"], {})
        landed = t.get("buy_sig_seen") or c.get("buy_sig") or s
        td = rpc("getTransaction", [f["dump_sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1}]); to = rpc("getTransaction", [landed, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
        if not td or not to: continue
        bd = blk(td["slot"]); bo = blk(to["slot"])
        if not bd or not bo or f["dump_sig"] not in bd or landed not in bo: continue
        path = next((p["path"] for p in (f.get("nonce") or {}).get("per_path", []) if p["sig"] == landed), "?")
        out.append(dict(reaction=(f["t_fire"] - f["t_dump_rx"]) / 1e6, fts=t.get("fire_to_seen_ms"), spill=to["slot"] > td["slot"], client=f.get("client"),
                        block_ms=(to["slot"] - td["slot"]) * 212 + (bo.index(landed) / len(bo) - bd.index(f["dump_sig"]) / len(bd)) * 212,
                        exec_lag=t.get("exec_lag_ms"), path=path, result=c.get("result")))
    return out
for fn, reg in [(a, b) for a, b in (("dip_r13.jsonl", "FRA r13"), ("dip_ams_r12.jsonl", "AMS r12"))]:
    o = analyze(fn)
    if not o: print(reg, "no fires resolved"); continue
    print(f"{reg}: fires {len(o)} | reaction median {med([x['reaction'] for x in o]):.2f} ms | fire->seen median {med([x['fts'] for x in o if x['fts']]):.1f} ms | "
          f"BLOCK-TIME landing median {med([x['block_ms'] for x in o]):.1f} ms | next-slot {sum(x['spill'] for x in o)}/{len(o)} | landed via {collections.Counter(x['path'] for x in o).most_common()}")
    for x in o: print(f"    {x['client']:18s} block {x['block_ms']:6.1f} ms | fire->seen {x['fts'] or 0:6.1f} | {'NEXT slot' if x['spill'] else 'same slot'} | via {x['path']:12s} | {x['result']}")
