import json, collections, sys
d = sys.argv[1]
L = lambda f: [json.loads(l) for l in open(f"{d}/{f}") if l.strip()]
q = lambda v, p: sorted(v)[int((len(v) - 1) * p)] if v else float('nan')
T, O, P = L("triggers.jsonl"), L("opportunities.jsonl"), L("predictions.jsonl")
S = L("status.jsonl")[-1]
print(f"triggers {len(T)} | by venue {dict(collections.Counter(t['venue'] for t in T))} | by source {dict(collections.Counter(t['source'] for t in T))}")
c = collections.Counter(t['feed'] for t in T)
print("first feed on triggers:", ", ".join(f"{k} {v} ({v*100/len(T):.0f}%)" for k, v in c.most_common()))
lat = S["latency"]; print("our latency us (p50/p90/p99):", {k: (v['p50_us'], v['p90_us'], v['p99_us']) for k, v in lat.items()})
# predictions
by = collections.defaultdict(list)
for p in P:
    if "err1_bps" in p: by[p["venue"]].append(max(abs(p["err0_bps"]), abs(p["err1_bps"])))
    else: by[p["venue"] + " active-bin"].append(0 if p["match"] else 1)
for v, e in by.items(): print(f"prediction {v}: {len(e)} checks, exact {sum(1 for x in e if x == 0)}, median {q(e,.5):.3f} p90 {q(e,.9):.3f}")
# opportunities
real = [o for o in O if o["trigger_landed_slot"] and o["net_lamports"] / max(o["size_lamports"], 1) <= 0.10]
landed = [o for o in O if o["trigger_landed_slot"]]
print(f"opportunities {len(O)} | trigger landed {len(landed)} | landed and plausible (return <= 10%) {len(real)} | taken by someone {sum(1 for o in real if o.get('taker'))}")
for o in sorted(real, key=lambda o: -o["net_lamports"])[:15]:
    t = o.get("taker") or {}
    print(f"  net {o['net_lamports']/1e9:.6f} SOL size {o['size_lamports']/1e9:.3f} {o['buy_source']}/{o['sell_source']} trig-feed {o['trigger_feed']} landed {o['trigger_landed_slot']-o['slot'] if o['trigger_landed_slot'] else '-'} slots later taker {(t.get('sig') or '-')[:8]} {('taker seen %.1f ms after trigger' % t['window_ms']) if t.get('window_ms') is not None else ''}")
print("real opps by pair source:", dict(collections.Counter(f"{o['buy_source']}/{o['sell_source']}" for o in real)),
      "| total net", round(sum(o["net_lamports"] for o in real) / 1e9, 6), "SOL")
pairs = collections.Counter(o["mint"][:8] for o in real)
print("real opps by token:", pairs.most_common(8))
# feeds on opportunity triggers
lead = collections.defaultdict(list); first = collections.Counter()
for o in O:
    a = o["arrivals"]
    if len(a) < 2: continue
    t0 = min(a.values()); first[min(a, key=a.get)] += 1
    for f, t in a.items(): lead[f].append((t - t0) / 1e6)
print("feeds on all opportunity triggers:")
for f, v in sorted(lead.items(), key=lambda x: q(x[1], .5)):
    print(f"  {f:18s} seen {len(v):4d} first {first[f]:4d}  behind first p50 {q(v,.5):6.2f} ms p90 {q(v,.9):6.2f} ms")
