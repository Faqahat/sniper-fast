#!/usr/bin/env python3
# Our dip fires from the live run logs (FRA dip_r*.jsonl, AMS dip_ams_r*.jsonl): dump sig, mint, leader, client, paths,
# per-path sigs, result, landed sig/path, engine timing. Output: our_fires.json
import json, glob, os, collections
D = "/home/moiz/sniper-data/landing2"
F = {}
fs = sorted(glob.glob("/home/moiz/sniper-data/runs/fra/runs/dip_r*.jsonl")) + sorted(glob.glob("/home/moiz/sniper-data/runs/ams/runs/dip_ams_r*.jsonl"))
for f in fs:
    srv = "AMS" if "/ams/" in f else "FRA"; run = os.path.basename(f).split(".")[0]
    for line in open(f):
        if '"fire"' not in line and '"close"' not in line and '"timing"' not in line and '"buy_land"' not in line: continue
        try: r = json.loads(line)
        except Exception: continue
        ev = r.get("ev")
        if ev == "fire":
            k = (run, r["buy_sig"])
            nonce = r.get("nonce") or {}
            F[k] = dict(srv=srv, run=run, mint=r["mint"], dump_sig=r["dump_sig"], leader=r.get("leader"), client=r.get("client"), route=r.get("route"),
                        slot=r.get("slot"), t_fire=r.get("t_fire"), t_dump_rx=r.get("t_dump_rx"), tips=r.get("tips"),
                        variants=[(v.get("paths"), v.get("sig"), v.get("tip"), v.get("tip_acct")) for v in (nonce.get("variants") or [])],
                        nonce=nonce.get("acct"), writes=r.get("writes"), lat_us=r.get("lat_us"), decision_us=r.get("decision_us"))
        elif ev == "close":
            for k, v in F.items():
                if k[0] == run and v["dump_sig"] == r.get("dump_sig") and v["mint"] == r.get("mint") and "result" not in v:
                    v["result"] = r.get("result"); v["land_sig"] = (r.get("variant") or {}).get("sig") or r.get("buy_sig"); v["land_paths"] = (r.get("variant") or {}).get("paths")
                    v["err"] = r.get("err"); break
        elif ev == "timing" and r.get("kind") == "fire":
            for k, v in F.items():
                if k[0] == run and v["mint"] == r.get("mint") and "timing" not in v:
                    v["timing"] = dict(reaction_ms=r.get("reaction_ms"), fire_to_seen_ms=r.get("fire_to_seen_ms"), exec_lag_ms=r.get("exec_lag_ms"),
                                       clock2=r.get("clock2")); break
out = list(F.values())
json.dump(out, open(f"{D}/our_fires.json", "w"))
c = collections.Counter((x["srv"], x["run"]) for x in out)
print(len(out)); print(sorted(c.items()))
print(collections.Counter(x.get("result") for x in out))
