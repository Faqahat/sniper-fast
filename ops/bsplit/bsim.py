# Offline: buy RIGHT BEHIND the creator bundle (entry = post-bundle price x slip), simple exits, OOS by time half.
import json, statistics as st, itertools
B = {json.loads(l)["mint"]: json.loads(l) for l in open("/root/bsplit/out.jsonl")}
P = {}
for l in open("/root/arbx-fast/paths_blnight.jsonl"):
    d = json.loads(l)
    P[d["mint"]] = d["path"]
L = [dict(B[m], path=P[m]) for m in P if m in B and "glued" in B[m]]
L.sort(key=lambda r: r["slot"])
tmax = [r["path"][-1][0] for r in L]
print(f"n={len(L)} path length s: median {st.median(tmax)/1000:.0f}  min {min(tmax)/1000:.0f}")
FEE = 0.0125


def sim(path, E, tp, tr, sl, T):
    peak = 0
    for t, p in path:
        r = p / E
        peak = max(peak, r)
        if t >= T or (tp and r >= tp) or (sl and r <= sl) or (tr and peak >= 1.08 and r <= peak * tr):
            break
    return r * (1 - FEE) / (1 + FEE) - 1 - 0.003


grid = list(itertools.product([None, 1.15, 1.25, 1.4, 1.6, 2.0, 3.0], [None, 0.92, 0.85, 0.75], [None, 0.9, 0.8], [3000, 6000, 10000, 20000, 40000, 10**9]))


def best(g, ent):
    res = []
    for tp, tr, sl, T in grid:
        v = [sim(r["path"], ent(r), tp, tr, sl, T) for r in g]
        res.append((st.mean(v), (tp, tr, sl, T)))
    res.sort(key=lambda x: -x[0])
    return res


def report(name, g, ent):
    if len(g) < 20:
        return
    h = len(g) // 2
    a, b = g[:h], g[h:]
    ba = best(a, ent)[0]
    p = ba[1]
    vb = [sim(r["path"], ent(r), *p) for r in b]
    ex = sorted(vb)[:-5]
    allb = best(g, ent)[0]
    print(f"{name:36} n={len(g):3} | best on 1st half {ba[0]:+.3f} params tp={p[0]} trail={p[1]} sl={p[2]} T={p[3]//1000 if p[3]<10**9 else 'max'}s"
          f" -> 2nd half (OOS) {st.mean(vb):+.3f} (ex-top5 {st.mean(ex):+.3f}, win {sum(x>0 for x in vb)/len(vb):.0%}) | in-sample best all {allb[0]:+.3f}")


bun = [r for r in L if r["glued"] >= 1]
nob = [r for r in L if r["glued"] == 0]
for slip in (1.00, 1.04, 1.10):
    print(f"\n=== entry = post-bundle price x {slip:.2f} ===")
    report("ALL bundled", bun, lambda r: max(1, r["bmult"]) * slip)
    report("bundle 1-10 SOL", [r for r in bun if 1 <= r["gsol"] < 10], lambda r: max(1, r["bmult"]) * slip)
    report("bundle >=3 SOL", [r for r in bun if r["gsol"] >= 3], lambda r: max(1, r["bmult"]) * slip)
    report("NO bundle (entry 1.00 x slip)", nob, lambda r: slip)
