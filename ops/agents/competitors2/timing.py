#!/usr/bin/env python3
# competitors2/timing.py -- READ-ONLY. Milliseconds after the dump, on OUR OWN feed clock, for every rival buy recorded in
# the engine's tape (all trades on a token from our fire until we close; executed feed, same clock as t_dump_rx) vs our own
# buy (first sighting, buy_first_rx). Per wallet, per leader kind, per region (FRA / AMS engine). Positions vs ms.
import json, collections, statistics
F = json.load(open("/home/moiz/sniper-data/competitors2/fires.json"))
US = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
def q(x, p): x = sorted(x); return x[min(len(x) - 1, int(p * len(x)))] if x else None
def fmt(x): return f"{q(x, .25):5.1f} {statistics.median(x):5.1f} {q(x, .75):5.1f}" if x else "    -     -     -"
W = collections.defaultdict(lambda: collections.defaultdict(list)); OUR = collections.defaultdict(list); FIRST = collections.defaultdict(list)
pairs = collections.defaultdict(list)   # kind -> (di, dt) for rate estimation
for f in F:
    td = f["t_dump_rx"]; k = f["kind"]; reg = f["region"]
    if f["buy_first_rx"]: OUR[(k, reg)].append((f["buy_first_rx"] - td) / 1e6); OUR[("all", reg)].append((f["buy_first_rx"] - td) / 1e6)
    rows = sorted([x for x in f["tape"] if x[4] == f["S"] and x[5] is not None and x[5] > f["dump_i"] and x[3] and x[2] not in US], key=lambda x: x[5])
    if rows: FIRST[(k, reg)].append((rows[0][1] - td) / 1e6); FIRST[("all", reg)].append((rows[0][1] - td) / 1e6)
    seen = set()
    for x in rows:
        if x[2] in seen: continue
        seen.add(x[2]); dt = (x[1] - td) / 1e6
        W[x[2]]["all"].append(dt); W[x[2]][k].append(dt); W[x[2]][reg].append(dt); pairs[k].append((x[5] - f["dump_i"], dt))
print("ms after the dump on our feed (p25 / median / p75); rivals = same-slot buys in our fired tokens' tapes")
print("\nUS (first sighting of our buy) vs the FIRST rival buy in the dump slot, by leader kind and engine region")
for key in sorted(OUR, key=lambda k: (k[0] != "all", k)):
    print(f"  {key[0]:9s} {key[1]}: us n={len(OUR[key]):3d} {fmt(OUR[key])} | first rival n={len(FIRST.get(key, [])):3d} {fmt(FIRST.get(key, []))}")
print("\nper rival wallet (same-slot buys, first per fire): n, ms p25/med/p75 overall; median by kind")
kinds = ("bam", "harmonic", "jito", "fd")
print(f"{'wallet':10s} {'n':>3s} {'p25':>5s} {'med':>5s} {'p75':>5s}  " + "  ".join(f"{k:>9s}" for k in kinds) + "    FRA   AMS")
for w, d in sorted(W.items(), key=lambda x: -len(x[1]["all"]))[:30]:
    a = d["all"]
    print(f"{w[:9]:10s} {len(a):3d} {fmt(a)}  " + "  ".join(f"{statistics.median(d[k]):5.1f}({len(d[k]):2d})" if d[k] else "        -" for k in kinds) +
          f"  {statistics.median(d['FRA']) if d['FRA'] else float('nan'):5.1f} {statistics.median(d['AMS']) if d['AMS'] else float('nan'):5.1f}")
print("\nblock positions per ms after the dump (same slot), by leader kind: median of di/dt for dt > 3 ms")
for k, P in pairs.items():
    r = [di / dt for di, dt in P if dt > 3]
    if r: print(f"  {k:9s} n={len(r):4d} positions/ms median {statistics.median(r):.2f} (p25 {q(r, .25):.2f}, p75 {q(r, .75):.2f})")
json.dump({w: {k: v for k, v in d.items()} for w, d in W.items()}, open("/home/moiz/sniper-data/competitors2/timing_wallets.json", "w"))
