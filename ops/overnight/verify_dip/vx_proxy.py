#!/usr/bin/env python3
"""verify_dip / vx_proxy: validate the arrival proxy (slot x 212 + idx / blocksize x 212 ms) against REAL arrival times our
shadow engine logged (scores_v3.jsonl "obs": outs = ms after the create was seen : sol : isbuy : fee-payer prefix).
Anchors: each outs entry matched to a tx (successful trade tx or failed tx) of that fee payer in slots S..S+8 of the launch
(own matching, own extraction in work/R2). Compares absolute and pairwise (B after A) arrival gaps, and the
"is this trade ahead of a buy sent L ms after A" classification for L = 20/35/50/75.
usage: python3 -I -B vx_proxy.py [SIZE=mine|claim]"""
import sys, os, json, gzip, zlib, collections, statistics, random
HERE = os.path.dirname(os.path.abspath(__file__)); WORK = os.path.join(HERE, "work")
SMS = 212.0
SRC = sys.argv[1] if len(sys.argv) > 1 else "mine"
if SRC == "claim":
    SS = {int(k): v for k, v in json.load(open(os.path.join(HERE, "snap", "slotsize2.json"))).items()}
else:
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
anchors = []        # (mint, s, i, real_ms, proxy_rel_ms, slot offset)
for b, ms_ in sorted(byb.items()):
    data = json.load(gzip.open(os.path.join(WORK, "R2", f"b{b:03d}.json.gz"), "rt"))
    for m in ms_:
        d = data.get(m)
        if not d: continue
        c = L[m]; S = c["slot"]; ci = c["idx"]
        units = {}                                      # (s, i) -> dict(payer, ok, buysol)
        for r in d["t"]:
            if r[0] - S > 8: continue
            u = units.setdefault((r[0], r[1]), dict(payer=r[5], ok=not r[4], buysol=0, nbuy=0))
            if r[9] == 1 and not r[4]: u["buysol"] += r[7]; u["nbuy"] += 1
        for f in d["f"]:
            if f[0] - S > 8: continue
            units.setdefault((f[0], f[1]), dict(payer=f[2], ok=False, buysol=0, nbuy=0))
        # skip the create tx and anything before it in its slot
        cand = sorted(k for k in units if (k[0], k[1]) > (S, ci))
        used = set()
        for ms, sol, isbuy, w6 in sorted(OBS[m]):
            pay = [k for k in cand if k not in used and (units[k]["payer"] or "").startswith(w6)]
            hit = None
            if isbuy and sol > 0:
                hit = next((k for k in pay if units[k]["nbuy"] and abs(units[k]["buysol"] / 1e9 - sol) <= max(0.02, 0.15 * sol)), None)
                if hit is None: hit = next((k for k in pay if not units[k]["ok"]), None)
            elif pay: hit = pay[0]
            if hit is None: continue
            used.add(hit)
            anchors.append((m, hit[0], hit[1], ms, arr(hit[0], hit[1]) - arr(S, ci), hit[0] - S))
print(f"[{SRC} block sizes] launches with >=2 obs entries: {len(OBS)}; anchors matched: {len(anchors)} in {len({a[0] for a in anchors})} launches")
real = [a[3] for a in anchors]; prox = [a[4] for a in anchors]
mr, mp = statistics.mean(real), statistics.mean(prox)
cov = sum((x - mr) * (y - mp) for x, y in zip(real, prox)) / len(real)
print(f"absolute (vs the create): corr {cov / (statistics.pstdev(real) * statistics.pstdev(prox)):.3f}; proxy - real median {statistics.median(y - x for x, y in zip(real, prox)):+.1f} ms")
for lo, hi in ((0, 25), (25, 50), (50, 100), (100, 200), (200, 400), (400, 1000)):
    dd = sorted(y - x for x, y in zip(real, prox) if lo <= x < hi)
    if len(dd) > 30: n = len(dd); print(f"  real [{lo},{hi}) ms: n {n:6d} proxy-real p10 {dd[n // 10]:+6.0f} p25 {dd[n // 4]:+6.0f} median {dd[n // 2]:+6.0f} p75 {dd[3 * n // 4]:+6.0f} p90 {dd[9 * n // 10]:+6.0f}")
# pairwise within a launch: A then B (by real arrival), gap in real vs proxy
by = collections.defaultdict(list)
for a in anchors: by[a[0]].append(a)
pairs = []
for m, v in by.items():
    v.sort(key=lambda a: a[3])
    for x in range(len(v)):
        for y in range(x + 1, len(v)):
            dr = v[y][3] - v[x][3]
            if dr > 250: break
            pairs.append((dr, v[y][4] - v[x][4], v[x][5], v[y][5], v[y][1] == v[x][1]))
print(f"pairs (B seen 0-250 ms after A, same launch): {len(pairs)}")
for lo, hi in ((0, 1), (1, 20), (20, 35), (35, 50), (50, 75), (75, 100), (100, 150), (150, 250)):
    dd = sorted(p[1] - p[0] for p in pairs if lo <= p[0] < hi)
    if len(dd) > 30: n = len(dd); print(f"  real gap [{lo},{hi}) ms: n {n:6d} proxy gap - real gap: p10 {dd[n // 10]:+6.0f} p25 {dd[n // 4]:+6.0f} median {dd[n // 2]:+6.0f} p75 {dd[3 * n // 4]:+6.0f} p90 {dd[9 * n // 10]:+6.0f}")
print("classification 'B is ahead of a buy sent L ms after A' (B after A in real time):")
for Lm in (20, 35, 50, 75):
    tp = sum(1 for p in pairs if p[0] < Lm and p[1] < Lm); fn = sum(1 for p in pairs if p[0] < Lm and p[1] >= Lm)
    fp = sum(1 for p in pairs if p[0] >= Lm and p[1] < Lm); tn = sum(1 for p in pairs if p[0] >= Lm and p[1] >= Lm)
    print(f"  L={Lm:3d}: really ahead {tp + fn:6d} -> proxy says ahead {tp / max(1, tp + fn):.1%}; really behind {fp + tn:6d} -> proxy says ahead {fp / max(1, fp + tn):.1%}")
# same slot only: does in-slot position scale like 212 ms per block?
ss = [(p[0], p[1]) for p in pairs if p[4] and p[0] > 0]
if ss:
    num = sum(x * y for x, y in ss); den = sum(x * x for x, y in ss)
    print(f"same-slot pairs with real gap > 0: {len(ss)}; least-squares slope proxy/real {num / den:.2f}; median ratio {statistics.median(y / x for x, y in ss if x >= 5):.2f}")
json.dump(dict(anchors=anchors[:200000]), open(os.path.join(HERE, "out", f"proxy_anchors_{SRC}.json"), "w"))
