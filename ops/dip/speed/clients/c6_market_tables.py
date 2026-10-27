#!/usr/bin/env python3
"""CLIENTS study: tables from market.json (c3_market.py). MEASURED, market-wide (every >= 1 SOL sell, all bots).
A. first reacting buy (index gap > 3) after a dump: same-slot share by client x turn position (dump in first 75% of its block)
B. reacting buys by tip path per client: index gap / B-clock ms, first-place lift
C. block order vs CU price (share of descending adjacent pairs among pump txs that set a CU price)
D. Jito leaders: relayer-fronted (TPU :11228 or other host) vs own TPU
usage: c6_market_tables.py market.json"""
import json, sys, collections, statistics as st
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/truth")
import tl

M = json.load(open(sys.argv[1]))
D, B = M["dumps"], M["blocks"]
SMS = 212.0


def cls(c):
    if not c: return "?"
    if c == "HarmonicAgave": return "harmonic"
    if c in ("HarmonicFiredancer", "HarmonicFrankendancer"): return "harmonicFD"
    return {"JitoLabs": "jito", "AgaveBam": "bam", "FireBAM": "firebam", "Firedancer": "fd", "Frankendancer": "fd",
            "Rakurai": "rakurai", "Agave": "agave"}.get(c, "other")


def med(v):
    v = [x for x in v if x is not None]
    return round(st.median(v), 1) if v else None


def bms(gap, n):
    return gap / max(400, n) * SMS


ORDER = ["bam", "jito", "harmonic", "harmonicFD", "fd", "firebam", "agave", "rakurai", "other", "?"]
print(f"files {M['files']}  dumps {len(D)}  blocks {len(B)}")

# dumps: [s, di, n, sol, reacts[[0,i,path,cup,cul,err,signer]...], nxt_first, nxt_avail, client, turnpos]
print("\n== A. first reacting buy after a >=1 SOL sell (gap > 3 txs): same slot / next slot / none seen; dumps in the first 75% of the block, next slot recorded")
print("client      turn  n     same   next   none   first-react B-ms p50   gap p50")
agg = collections.defaultdict(list)
for d in D:
    s, di, n, sol, reacts, nf, navail, c, tp = d
    if not navail or tp is None or di / n > 0.75: continue
    agg[(cls(c), min(tp, 3))].append(d)
for k in ORDER:
    for tp in range(4):
        v = agg.get((k, tp))
        if not v or len(v) < 30: continue
        same = [d for d in v if d[4]]
        nxt = [d for d in v if not d[4] and d[5]]
        print(f"{k:11s} {tp+1:4d}  {len(v):5d} {len(same)/len(v):6.0%} {len(nxt)/len(v):6.0%} {(len(v)-len(same)-len(nxt))/len(v):6.0%}   "
              f"{med([bms(d[4][0][1]-d[1], d[2]) for d in same]):>8}            {med([d[4][0][1]-d[1] for d in same])}")

print("\n== A2. same, by dump position in its block (all turn positions)")
agg2 = collections.defaultdict(list)
for d in D:
    s, di, n, sol, reacts, nf, navail, c, tp = d
    if not navail: continue
    q = min(3, int(4 * di / n))
    agg2[(cls(c), q)].append(d)
for k in ORDER:
    row = []
    for q in range(4):
        v = agg2.get((k, q), [])
        if len(v) >= 30:
            row.append(f"Q{q+1}: {sum(1 for d in v if d[4])/len(v):.0%} of {len(v)}")
    if row: print(f"{k:11s} " + "  ".join(row))

print("\n== B. reacting buys (first 6 after each dump, same slot) by tip path: n, gap p50, B-ms p25/p50, share of first places / share of reacting buys (lift)")
for k in ORDER:
    rows = collections.defaultdict(list); first = collections.Counter(); tot = 0
    for d in D:
        if cls(d[7]) != k or not d[4]: continue
        tot += 1
        first[d[4][0][2]] += 1
        for r in d[4]:
            rows[r[2]].append(bms(r[1] - d[1], d[2]))
    if not rows: continue
    nall = sum(len(v) for v in rows.values())
    print(f"-- {k} (dumps with a reaction: {tot})")
    for p, v in sorted(rows.items(), key=lambda kv: -len(kv[1]))[:9]:
        if len(v) < 20: continue
        vs = sorted(v)
        lift = (first[p] / tot) / (len(v) / nall)
        print(f"   {p:13s} n={len(v):5d}  B-ms p25/p50 {vs[len(vs)//4]:5.1f}/{vs[len(vs)//2]:5.1f}   first {first[p]:4d}  lift {lift:4.2f}")

print("\n== C. block order vs CU price: descending adjacent pairs / (desc + asc) among pump txs with a CU price (0.5 = unrelated; 1 = sorted by price)")
cb = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
for b in B:
    s, n, npump, nf, desc, asc, c, tp = b
    x = cb[cls(c)]
    x[0] += 1; x[1] += desc; x[2] += asc; x[3] += npump; x[4] += nf
for k in ORDER:
    x = cb.get(k)
    if not x or x[0] < 30: continue
    print(f"{k:11s} blocks={x[0]:6d}  desc share={x[1]/max(1, x[1]+x[2]):.3f}  pump txs/block={x[3]/x[0]:.0f}  failed share={x[4]/max(1, x[3]):.0%}")

print("\n== D. Jito leaders by TPU front (gossip snapshot): first reacting buy after a dump (dump in first 75% of block)")
L = {}
for bk in ["/home/moiz/sniper/ops/dip/speed/leaders/leader_rtt_new.json", "/home/moiz/sniper/ops/region/leader_rtt_ams.json"]:
    for pk, r in json.load(open(bk))["leaders"].items(): L.setdefault(pk, r)
def kind(pk):
    r = L.get(pk)
    if not r or not r.get("tpu"): return "?"
    ip, port = r["tpu"].rsplit(":", 1)
    if port == "11228": return "relayer-colo"
    if len(r.get("ips") or []) > 1: return "relayer-remote"
    return "own-tpu"
jd = collections.defaultdict(list)
for d in D:
    if cls(d[7]) != "jito" or not d[6] or d[1] / d[2] > 0.75: continue
    jd[(kind(tl.leader(d[0])), min(d[8], 3))].append(d)
for (kd, tp), v in sorted(jd.items()):
    if len(v) < 20: continue
    same = [d for d in v if d[4]]
    print(f"  {kd:15s} turn {tp+1}: n={len(v):5d} same-slot {len(same)/len(v):4.0%}  first-react B-ms p50 {med([bms(d[4][0][1]-d[1], d[2]) for d in same])}")

print("\n== E. block size proxy (max pump-tx index + 1) and pump txs per block, by client x turn position (p25/p50/p75)")
bs = collections.defaultdict(list)
for b in B:
    s, n, npump, nf, desc, asc, c, tp = b
    if tp is None: continue
    bs[(cls(c), min(tp, 3))].append((n, npump))
for k in ORDER:
    row = []
    for tp in range(4):
        v = bs.get((k, tp), [])
        if len(v) < 30: continue
        ns = sorted(x[0] for x in v); ps = sorted(x[1] for x in v)
        row.append(f"T{tp+1}: n {ns[len(ns)//4]}/{ns[len(ns)//2]}/{ns[3*len(ns)//4]} pump {ps[len(ps)//2]} (blocks {len(v)})")
    if row: print(f"{k:11s} " + " | ".join(row))
