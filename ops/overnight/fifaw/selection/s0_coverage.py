#!/usr/bin/env python3
# coverage check (read-only): launches files vs feature table vs FiFawH attempts
import sys, json, gzip, collections, datetime
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core"); import rp
L = rp.load_launches()
A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts_fifaw.json"))
T = {}
for l in gzip.open("/home/moiz/sniper-data/collect/paper/table_dump.jsonl.gz", "rt"):
    r = json.loads(l); T[r["mint"]] = (r.get("bt"), r.get("S"))
f = lambda t: datetime.datetime.utcfromtimestamp(t).strftime("%m-%d %H:%M:%S") if t else None
for tag in ("R1", "R2"):
    bts = [c["bt"] for c in L.values() if c["run"] == tag and c.get("bt")]
    print(tag, "launches", len(bts), f(min(bts)), f(max(bts)), "err", sum(1 for c in L.values() if c["run"] == tag and c.get("err")))
tb = [v[0] for v in T.values() if v[0]]
print("table rows", len(T), f(min(tb)), f(max(tb)), "in launches", sum(1 for m in T if m in L))
ab = [L[m]["bt"] for m in A if m in L]
print("attempts", len(A), "in launches", sum(1 for m in A if m in L), "in table", sum(1 for m in A if m in T), f(min(ab)), f(max(ab)))
lo, hi = min(ab), max(ab)
win = [m for m, c in L.items() if c.get("bt") and lo <= c["bt"] <= hi]
print("launches in attempt window", len(win), "in table", sum(1 for m in win if m in T), "err", sum(1 for m in win if L[m].get("err")))
# gaps in launches (collector downtime) within window: minutes with zero launches
mins = collections.Counter(int(L[m]["bt"] // 60) for m in win)
allm = range(int(lo // 60), int(hi // 60) + 1)
gaps = [m for m in allm if mins[m] == 0]
print("minutes in window", len(allm), "zero-launch minutes", len(gaps))
# contiguous gaps
runs = []; s = None; p = None
for m in gaps:
    if s is None: s = p = m
    elif m == p + 1: p = m
    else: runs.append((s, p)); s = p = m
if s is not None: runs.append((s, p))
for s, p in runs:
    if p - s + 1 >= 5: print("  gap", f(s * 60), "->", f(p * 60 + 59), p - s + 1, "min")
# table-missing launches in window: by hour
miss = [m for m in win if m not in T]
print("missing from table by hour", sorted(collections.Counter(f(L[m]["bt"])[:8] for m in miss).items())[:60])
# attempts by offset
print(collections.Counter(tuple(v["FiFawH"]) for v in A.values()))
