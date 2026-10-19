#!/usr/bin/env python3
"""READ-ONLY scorer for the LAT multi-path landing test.
usage: lat_measure.py /root/lat/live_land_<tag>.log /root/lat/sends_<tag>.jsonl
1. runs /root/bsplit/measure_land.py on the log (position after the create, same slot, outsiders ahead, fill gap)
2. joins each buy with the engine's per-path send log (route, leader class, every path's ack, Jito bundle result)
3. scores by leader class: in-S rate, d<=25 rate, FIRST outsider behind the creator bundle, vs the Helius-only baseline
   (our 42 Oct-18 live fires: in S 16/42 = 38%, d<=25 0/42, median d 104)."""
import sys, json, runpy, collections, statistics as st

log, sends = sys.argv[1], sys.argv[2]
sys.argv = ["measure_land.py", log]
g = runpy.run_path("/root/bsplit/measure_land.py")
rows = g["rows"]

acks = collections.defaultdict(list); jres = {}
for l in open(sends):
    try: r = json.loads(l)
    except Exception: continue
    if r.get("ev") == "ack": acks[r["sig"]].append(r)
    elif r.get("ev") == "jito_result": jres[r["sig"]] = r.get("results", "")

def cls(c):
    c = c or ""
    if c in ("AgaveBam", "FireBAM"): return "bam"
    if c.startswith("Harmonic"): return "harmonic"
    if c == "JitoLabs": return "jito"
    if c in ("Firedancer", "Frankendancer"): return "fd"
    return "agave/other"

print("\n== PER BUY: route, every path's ack, Jito bundle result, landing ==")
by = collections.defaultdict(list)
for f in rows:
    if "err" in f: print(f"  {f['mint'][:8]} {f['err']}"); continue
    a = acks.get(f["sig"], [])
    route = a[0]["route"] if a else "?"
    paths = " ".join(f"{x['path']}:{x['ack_ms']:.1f}{'' if x['ok'] else '!REFUSED'}" for x in sorted(a, key=lambda x: x["t_off_us"]))
    k = cls(f.get("client"))
    pos = f["pos"] if f["same_slot"] else None
    rec = {"inS": f["same_slot"], "d25": pos is not None and pos <= 25, "first": f["same_slot"] and f["outsiders_ahead"] == 0, "pos": pos, "gap": f.get("gap")}
    by[k].append(rec); by["ALL"].append(rec)
    print(f"  {f['mint'][:8]} {f['client']:14} {route:22} {'S' if f['same_slot'] else '+' + str(f['land'] - f['cslot']):>3} pos={str(pos):>4} "
          f"out_ahead={str(f['outsiders_ahead']):>6} gap={('%+.1f%%' % ((f['gap'] - 1) * 100)) if f.get('gap') else '?':>7} | {paths} | jito={jres.get(f['sig'], '-')}")

print("\n== BY LEADER CLASS (pass: d<=25 share and FIRST-outsider share well above the Helius-only baseline) ==")
print(f"  {'class':12} {'n':>3} {'in S':>8} {'d<=25':>8} {'first':>8} {'med pos':>8} {'med gap':>8}")
for k in ["bam", "harmonic", "jito", "fd", "agave/other", "ALL"]:
    v = by.get(k)
    if not v: continue
    n = len(v); ps = [r["pos"] for r in v if r["pos"] is not None]; gs = [r["gap"] for r in v if r["gap"]]
    print(f"  {k:12} {n:3} {sum(r['inS'] for r in v):3} {sum(r['inS'] for r in v)/n:4.0%} {sum(r['d25'] for r in v):3} {sum(r['d25'] for r in v)/n:4.0%} "
          f"{sum(r['first'] for r in v):3} {sum(r['first'] for r in v)/n:4.0%} {st.median(ps) if ps else '-':>8} {('%+.1f%%' % ((st.median(gs) - 1) * 100)) if gs else '-':>8}")
print("  BASELINE Helius-only live (Oct 18, n=42): in S 38%, d<=25 0%, median pos 104; races in S 2/10")
