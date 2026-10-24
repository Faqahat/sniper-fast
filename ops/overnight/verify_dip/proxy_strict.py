#!/usr/bin/env python3
"""verify_dip / proxy_strict: the proxy check again with UNAMBIGUOUS anchors only (the wallet has exactly one tx in slots
S..S+8 of the launch and exactly one outs entry), to make sure matching errors do not inflate the proxy's error."""
import os, json, gzip, zlib, collections, statistics
HERE = os.path.dirname(os.path.abspath(__file__)); WORK = os.path.join(HERE, "work"); SMS = 212.0
SS = {}
for tag in ("R1", "R2"):
    for k, v in json.load(gzip.open(os.path.join(WORK, tag, "smax.json.gz"), "rt")).items():
        if v + 1 > SS.get(int(k), 0): SS[int(k)] = v + 1
def arr(s, i): return s * SMS + i / max(SS.get(s, 400), i + 1) * SMS
L = {}
for l in open("/home/moiz/sniper-data/collect/run_20261022_1543/launches.jsonl"):
    try: c = json.loads(l)
    except Exception: continue
    L.setdefault(c["mint"], c)
OBS = {}
for l in open("/home/moiz/sniper-data/collect/shadow/scores_v3.jsonl"):
    try: r = json.loads(l)
    except Exception: continue
    if r.get("type") != "obs" or r.get("mint") not in L: continue
    outs = []
    for x in (r.get("outs") or "").split(","):
        p = x.split(":")
        if len(p) >= 4:
            try: outs.append((float(p[0]), float(p[1]), p[2] == "1", p[3]))
            except ValueError: pass
    if len(outs) >= 2: OBS.setdefault(r["mint"], outs)
byb = collections.defaultdict(list)
for m in OBS: byb[zlib.crc32(m.encode()) % 256].append(m)
anchors = []
for b, ms_ in sorted(byb.items()):
    data = json.load(gzip.open(os.path.join(WORK, "R2", f"b{b:03d}.json.gz"), "rt"))
    for m in ms_:
        d = data.get(m)
        if not d: continue
        c = L[m]; S = c["slot"]; ci = c["idx"]
        units = {}
        for r in d["t"]:
            if r[0] - S <= 8 and (r[0], r[1]) > (S, ci): units.setdefault((r[0], r[1]), r[5])
        for f in d["f"]:
            if f[0] - S <= 8 and (f[0], f[1]) > (S, ci): units.setdefault((f[0], f[1]), f[2])
        byp = collections.defaultdict(list)
        for k, p in units.items(): byp[(p or "")[:6]].append(k)
        cnt = collections.Counter(w6 for _, _, _, w6 in OBS[m])
        for ms, sol, isbuy, w6 in OBS[m]:
            if cnt[w6] != 1 or len(byp.get(w6, [])) != 1: continue
            k = byp[w6][0]; anchors.append((m, k[0], k[1], ms, arr(k[0], k[1]) - arr(S, ci)))
by = collections.defaultdict(list)
for a in anchors: by[a[0]].append(a)
pairs = []
for m, v in by.items():
    v.sort(key=lambda a: a[3])
    for x in range(len(v)):
        for y in range(x + 1, len(v)):
            dr = v[y][3] - v[x][3]
            if dr > 250: break
            pairs.append((dr, v[y][4] - v[x][4]))
print(f"unambiguous anchors {len(anchors)} in {len(by)} launches; pairs {len(pairs)}")
for lo, hi in ((0, 1), (1, 20), (20, 35), (35, 50), (50, 75), (75, 100), (100, 150), (150, 250)):
    dd = sorted(p[1] - p[0] for p in pairs if lo <= p[0] < hi)
    if len(dd) > 30: n = len(dd); print(f"  real gap [{lo},{hi}) n {n:6d}: proxy-real p10 {dd[n // 10]:+5.0f} p25 {dd[n // 4]:+5.0f} median {dd[n // 2]:+5.0f} p75 {dd[3 * n // 4]:+5.0f} p90 {dd[9 * n // 10]:+5.0f} mean {statistics.mean(dd):+5.1f}")
for Lm in (20, 35, 50, 75):
    tp = sum(1 for p in pairs if p[0] < Lm and p[1] < Lm); fn = sum(1 for p in pairs if p[0] < Lm and p[1] >= Lm)
    fp = sum(1 for p in pairs if p[0] >= Lm and p[1] < Lm); tn = sum(1 for p in pairs if p[0] >= Lm and p[1] >= Lm)
    print(f"  L={Lm}: really ahead -> proxy ahead {tp / max(1, tp + fn):.0%}; really behind -> proxy ahead {fp / max(1, fp + tn):.0%}")

ds = {str(Lr): [p[1] - p[0] for p in pairs if abs(p[0] - Lr) <= 7.5] for Lr in (20, 35, 50, 75)}
json.dump(ds, open(os.path.join(HERE, "out", "proxy_d_strict.json"), "w"))
print("saved d samples:", {k: len(v) for k, v in ds.items()})
