#!/usr/bin/env python3
# Per leader client: our same-block rate and ms vs the pros on the SAME dumps (dump in the first 75% of its block, where pros mostly get in).
import json, collections, os, statistics
D = os.path.dirname(os.path.abspath(__file__)) + "/.."
V = {v["sig"]: v for v in json.load(open(f"{D}/latest/verify.json"))}
PROS = {"HkQ7hMjy", "G9G3dCBG", "5w8xtjc6", "6n2cCJrr", "8PgC4ngp", "9k78QZyw", "haqqiUUX"}
FILES = [f"dip_r{i}.jsonl" for i in range(1, 11)] + ["dip_ams_r9.jsonl", "dip_ams_r10.jsonl"]
C = collections.defaultdict(lambda: dict(n=0, sp=0, ours_ms=[], pd=0, ps=0, pro_ms=[], paths=collections.Counter()))
for fn in FILES:
    fires = {}; tape = collections.defaultdict(list); tim = {}
    for l in open(f"{D}/{fn}"):
        try: r = json.loads(l)
        except Exception: continue
        e = r.get("ev")
        if e == "fire": fires[r["buy_sig"]] = r
        elif e == "tape": tape[r["mint"]].append(r)
        elif e == "timing" and r.get("kind") == "fire": tim[r["buy_sig"]] = r
    for sig, f in fires.items():
        v = V.get(sig)
        if not v or v.get("dump_pos") is None or v["dump_pos"] >= 0.75: continue
        S = f["slot"]; t0 = f["t_dump_rx"]; c = C[v["client"]]; tm = tim.get(sig, {})
        c["n"] += 1; c["sp"] += bool(v["spill"]); c["paths"][f.get("route")] += 1
        if not v["spill"] and tm.get("fire_to_seen_ms"): c["ours_ms"].append((f["t_fire"] - t0) / 1e6 + tm["fire_to_seen_ms"])
        pro = [x for x in tape[f["mint"]] if x["buy"] and x["user"][:8] in PROS and S <= x["slot"] <= S + 1 and x["t"] >= t0]
        if pro:
            first = min(pro, key=lambda x: (x["slot"], x["idx"])); c["pd"] += 1
            if first["slot"] == S: c["ps"] += 1; c["pro_ms"].append((first["t"] - t0) / 1e6)
med = lambda v: f"{statistics.median(v):5.1f}" if v else "  -  "
print("leader client (dump in first 75% of block) | fires | WE same block | our ms (same block) | PRO same block | pro ms | our routes")
for k, c in sorted(C.items(), key=lambda kv: -kv[1]["n"]):
    print(f"  {k:18s} {c['n']:4d} | {1 - c['sp']/c['n']:4.0%} | {med(c['ours_ms'])} | {c['ps']}/{c['pd']} | {med(c['pro_ms'])} | {dict(c['paths'].most_common(3))}")
