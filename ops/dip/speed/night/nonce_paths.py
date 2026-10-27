#!/usr/bin/env python3
# Nonce-era live fires (runs 11-14, FRA + AMS): each path got its OWN signed variant, so the variant seen on chain names the path
# that delivered the buy. Per leader client: which path won, PoH landing ms (leader clock: our tx position - dump position),
# fire -> seen back ms, same slot as the dump. READ-ONLY (logs copied from the servers).
import json, glob, collections, statistics
med = lambda v: round(statistics.median(v), 1) if v else None
rows = []
for fn in sorted(glob.glob("dip_*.jsonl")):
    fires, tim = {}, {}
    for l in open(fn):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("ev") == "fire": fires[r["buy_sig"]] = r
        elif r.get("ev") == "timing" and r.get("kind") == "fire": tim[r["buy_sig"]] = r
    for bs, f in fires.items():
        t = tim.get(bs, {}); n = f.get("nonce")
        if isinstance(n, str): n = eval(n)
        seen = t.get("buy_sig_seen") or (bs if t.get("buy_poh") else None)
        win = None
        if n and seen:
            for v in n.get("variants", []):
                if v["sig"] == seen: win = "+".join(v["paths"]) + (f" (tip {v['tip']/1e9:g})" if v.get("tip") else " (no tip)")
        same = (t["dump_poh"][0] == t["buy_poh"][0]) if t.get("dump_poh") and t.get("buy_poh") else None
        rows.append(dict(fn=fn, client=f.get("client"), route=f.get("route"), nonce=bool(n), win=win, poh=t.get("land_ms_poh"), fts=t.get("fire_to_seen_ms"),
                         react=t.get("reaction_ms"), lag=t.get("exec_lag_ms"), same=same, nvar=len(n.get("variants", [])) if n else 0,
                         writes=[w["path"] if isinstance(w, dict) else w for w in (f["writes"] if isinstance(f["writes"], list) else eval(f["writes"]))]))
print(f"fires {len(rows)} | nonce {sum(r['nonce'] for r in rows)} | seen on chain {sum(1 for r in rows if r['poh'] is not None)}")
for cl in sorted({r["client"] for r in rows}, key=str):
    v = [r for r in rows if r["client"] == cl and r["poh"] is not None]
    if not v: continue
    s = [r for r in v if r["same"]]
    print(f"\n{cl}: n={len(v)} | PoH land median {med([r['poh'] for r in v])} ms | same slot {len(s)}/{len(v)} (PoH median when same slot {med([r['poh'] for r in s])}) | fire->seen med {med([r['fts'] for r in v if r['fts']])}")
    c = collections.defaultdict(list)
    for r in v: c[r["win"]].append(r)
    for w, x in sorted(c.items(), key=lambda kv: -len(kv[1])):
        print(f"   landed via {str(w):45s} n={len(x):2d} | PoH {med([r['poh'] for r in x])} | same slot {sum(1 for r in x if r['same'])}/{len(x)} | routes {collections.Counter(r['route'] for r in x).most_common(2)}")
json.dump(rows, open("nonce_paths.json", "w"))
