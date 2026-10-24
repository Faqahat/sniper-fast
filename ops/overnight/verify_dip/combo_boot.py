#!/usr/bin/env python3
"""verify_dip / combo_boot: per-pick expected PnL at a REAL delay (combo.py pricing, proxy error averaged), then per-block totals,
best-10-launch removal and a launch-clustered bootstrap. usage: python3 -I -B combo_boot.py <combo json> <picks json> <LAT> <real L> <txc>"""
import sys, os, json, collections, random
HERE = os.path.dirname(os.path.abspath(__file__))
res = json.load(open(sys.argv[1])); sel = json.load(open(sys.argv[2]))[sys.argv[3]]["sel"]; Lr = int(sys.argv[4]); txc = float(sys.argv[5])
an = json.load(open(os.path.join(HERE, "out", "proxy_anchors_mine.json")))["anchors"]
byl = collections.defaultdict(list)
for a in an: byl[a[0]].append(a)
ds = []
for m, v in byl.items():
    v.sort(key=lambda a: a[3])
    for x in range(len(v)):
        for y in range(x + 1, len(v)):
            dr = v[y][3] - v[x][3]
            if dr > Lr + 8: break
            if abs(dr - Lr) <= 7.5: ds.append((v[y][4] - v[x][4]) - dr)
if os.environ.get("DSTRICT") == "1": ds = json.load(open(os.path.join(HERE, "out", "proxy_d_strict.json")))[str(Lr)]
w = collections.Counter(min(300, max(0, int(round((Lr + d) / 5.0)) * 5)) for d in ds); n = len(ds)
RT = -float(os.environ.get('DIPB', '0.5')) * 0.0125 * 2
def ep(v): return sum(c * (v.get(str(L), RT) - 2 * txc) for L, c in w.items()) / n
P = [(s["b"], s["m"], ep(res[f"{s['m']}|{s['age']}"])) for s in sel]
byb = collections.defaultdict(float)
for b, m, p in P: byb[b] += p
print(f"[d from {'unambiguous' if os.environ.get('DSTRICT') == '1' else 'all'} anchors, n {n}] picks {len(P)}, real delay {Lr} ms, {txc} SOL/tx: total {sum(p for _, _, p in P):+.2f}; per block " + " ".join(f"b{b} {v:+.2f}" for b, v in sorted(byb.items())))
pm = collections.defaultdict(float)
for b, m, p in P: pm[m] += p
best = sorted(pm.values(), reverse=True)[:10]
print(f"  without the best 10 launches: {sum(pm.values()) - sum(best):+.2f}")
rng = random.Random(11); bym = collections.defaultdict(lambda: collections.defaultdict(float))
for b, m, p in P: bym[b][m] += p
tots = []; pos = collections.Counter()
for _ in range(2000):
    t = 0.0
    for b, mm in bym.items():
        vals = list(mm.values()); bt = sum(rng.choice(vals) for _ in vals); t += bt; pos[b] += bt > 0
    tots.append(t)
tots.sort()
print(f"  bootstrap: p2.5 {tots[50]:+.2f} p50 {tots[1000]:+.2f} p97.5 {tots[1950]:+.2f}; P(total <= 0) {sum(1 for x in tots if x <= 0) / 2000:.1%}; P(block > 0) " + " ".join(f"b{b} {pos[b] / 2000:.0%}" for b in sorted(bym)))
