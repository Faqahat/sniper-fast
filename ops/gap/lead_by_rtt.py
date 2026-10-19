#!/usr/bin/env python3
"""Lead of a reference feed (default dz-leader: leader-published shreds) over every other feed, on creates the
reference delivered, by leader RTT bucket and by leader class; plus slot first-shred leads by RTT bucket.
Usage: lead_by_rtt.py LOG [ref=dz-leader]"""
import sys, json, collections
def pct(v, q):
    if not v: return float("nan")
    v = sorted(v); i = (len(v) - 1) * q; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)
log = sys.argv[1]; REF = sys.argv[2] if len(sys.argv) > 2 else "dz-leader"
L = json.load(open("/root/gap/leaders.json"))
def node(s):
    i = L["leaders"].get(str(s)); return L["nodes"].get(i, {}) if i else {}
def b(r): return "?" if r is None else ("<3" if r < 3 else ("3-20" if r < 20 else ("20-100" if r < 100 else ">100")))
tx = {}; first = collections.defaultdict(dict)
for line in open(log, errors="replace"):
    p = line.rstrip("\n").split("\t")
    if p[0] == "X":
        d = tx.setdefault(p[4], {"slot": int(p[3]), "cr": False, "f": {}})
        d["cr"] |= p[5] == "1"; t = int(p[2])
        if p[1] not in d["f"] or t < d["f"][p[1]]: d["f"][p[1]] = t
    elif p[0] == "S": first[int(p[3])].setdefault(p[1], int(p[2]))
    elif p[0] == "U" and p[4] == "3": first[int(p[3])].setdefault(p[1], int(p[2]))
feeds = sorted({f for d in tx.values() for f in d["f"]} - {REF})
cr = [d for d in tx.values() if d["cr"] and REF in d["f"]]
allcr = [d for d in tx.values() if d["cr"]]
print(f"creates: {len(allcr)}, delivered by {REF}: {len(cr)} ({len(cr)*100/max(1,len(allcr)):.0f}%: slots of leaders that publish to it)")
for title, key in (("leader RTT from us (ms)", lambda d: b(node(d["slot"]).get("rtt_ms"))), ("leader class", lambda d: node(d["slot"]).get("class", "?"))):
    g = collections.defaultdict(list)
    for d in cr: g[key(d)].append(d)
    print(f"\n-- {REF} lead on creates by {title}: median / p90 ms (n)   [+ = {REF} earlier]")
    print("  " + f"{'group':8s} " + " ".join(f"{f:>22s}" for f in feeds))
    for k in sorted(g, key=lambda k: -len(g[k])):
        row = f"  {k:8s} "
        for f in feeds:
            v = [(d["f"][f] - d["f"][REF]) / 1e6 for d in g[k] if f in d["f"]]
            row += f"{pct(v,.5):7.2f} /{pct(v,.9):7.2f} ({len(v):4d})" if v else f"{'-':>22s}"
        print(row)
g = collections.defaultdict(list)
for s, v in first.items():
    if REF in v: g[b(node(s).get("rtt_ms"))].append(v)
print(f"\n-- slot FIRST shred: {REF} lead by leader RTT, median / p90 ms (n)")
print("  " + f"{'group':8s} " + " ".join(f"{f:>22s}" for f in feeds))
for k in sorted(g, key=lambda k: -len(g[k])):
    row = f"  {k:8s} "
    for f in feeds:
        v = [(x[f] - x[REF]) / 1e6 for x in g[k] if f in x]
        row += f"{pct(v,.5):7.2f} /{pct(v,.9):7.2f} ({len(v):4d})" if v else f"{'-':>22s}"
    print(row)
