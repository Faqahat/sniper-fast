#!/usr/bin/env python3
# Live runs now (read-only copies): for every fire, every OTHER wallet's buy on the token from the dump to the next slot -> how many
# ms after the dump it was seen vs our buy (same feed, same clock: executed-feed rx), and who landed first in chain order.
import json, collections, statistics, glob, sys
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
G = collections.defaultdict(list); P = []
for fn in sys.argv[1:]:
    fires, tim, tape = {}, {}, collections.defaultdict(list)
    for l in open(fn):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("ev") == "fire": fires[r["buy_sig"]] = r
        elif r.get("ev") == "timing" and r.get("kind") == "fire": tim[r["buy_sig"]] = r
        elif r.get("ev") == "tape": tape[r["mint"]].append(r)
    for sig, f in fires.items():
        t = tim.get(sig, {})
        if not t.get("fire_to_seen_ms"): continue
        t0 = f["t_dump_rx"]; S = f["slot"]; ours = (f["t_fire"] - t0) / 1e6 + t["fire_to_seen_ms"]
        mine = next((x for x in tape[f["mint"]] if x["user"] in OURS and x["buy"] and S <= x["slot"] <= S + 1), None)
        seen = set()
        for x in sorted(tape[f["mint"]], key=lambda x: (x["slot"], x["idx"])):
            if not x["buy"] or x["user"] in OURS or x["user"] in seen or not (S <= x["slot"] <= S + 1) or x["t"] < t0: continue
            seen.add(x["user"]); ms = (x["t"] - t0) / 1e6
            first = mine is None or (x["slot"], x["idx"]) < (mine["slot"], mine["idx"])
            G[x["user"][:8]].append((ours - ms, first, f.get("client")))
        P.append((fn.split("_")[-1], f.get("client"), ours, len(seen)))
print(f"live fires {len(P)} | our buy seen after the dump: median {statistics.median([p[2] for p in P]):.1f} ms")
print("\nbots that bought the same dumps (>= 3 times): how much earlier than us they were seen (ms; + = they beat us)")
for w, v in sorted(G.items(), key=lambda kv: -len(kv[1])):
    if len(v) < 3: continue
    beat = [d for d, f, _ in v if f]
    print(f"  {w}: n={len(v):3d} | median {statistics.median([d for d,_,_ in v]):+6.1f} ms | landed before us {len(beat)}/{len(v)} (by median {statistics.median(beat) if beat else 0:+.1f} ms) | leaders {dict(collections.Counter(c for *_, c in v).most_common(3))}")
allv = [d for v in G.values() for d, f, _ in v if f]
print(f"\nALL bots that landed before us: n={len(allv)} | ahead by median {statistics.median(allv):.1f} ms | <=2 ms {sum(1 for d in allv if d<=2)/len(allv):.0%} | <=5 ms {sum(1 for d in allv if d<=5)/len(allv):.0%} | <=10 ms {sum(1 for d in allv if d<=10)/len(allv):.0%}")
